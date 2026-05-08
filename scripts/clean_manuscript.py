#!/usr/bin/env python3
"""Create a non-destructive cleaned manuscript draft from extracted markdown."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


BIDI_CONTROL_RE = re.compile(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
ARABIC_LETTER_RE = r"\u0621-\u064a\u066e-\u06d3"
ARABIC_DIACRITIC_RE = r"\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed"
PASSAGE_RE = re.compile(r'^::passage\{id="([^"]+)"\}\s*$')
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILES_PATH = PROJECT_ROOT / "config" / "cleaning_profiles.yml"
RUNTIME_ERROR_RE = re.compile(
    r"runtime\s+(?:VBScript|Script)|Microsoft.*error|Subscript.*out\s+of\s+range|/Tafseer/",
    re.IGNORECASE,
)

SUSPICIOUS_PATTERNS = [
    ("star_leftover", re.compile(r"\*")),
    ("legacy_print_marker", re.compile(r"(?:^|[\s،.؛:])-?ط\([،.]?\)?-?")),
    ("runtime_error", RUNTIME_ERROR_RE),
    ("latin_word", re.compile(r"[A-Za-z]{3,}")),
    ("brace_marker", re.compile(r"[{}]")),
    ("bidi_control", BIDI_CONTROL_RE),
    ("broken_initial_alef", re.compile(r"ا[أإآ]ل")),
]


def load_book_id(book_dir: Path) -> str:
    book_path = book_dir / "book.yml"
    if yaml is None or not book_path.exists():
        return book_dir.name
    data = yaml.safe_load(book_path.read_text(encoding="utf-8")) or {}
    return str(data.get("id") or book_dir.name)


def load_cleaning_profile(
    profiles_path: Path,
    profile_name: str,
) -> dict[str, Any]:
    if yaml is None or not profiles_path.exists():
        return {"name": "default", "rules": []}

    data = yaml.safe_load(profiles_path.read_text(encoding="utf-8")) or {}
    profiles = data.get("profiles", {})
    selected = profiles.get(profile_name) or profiles.get("default") or {}
    default = profiles.get("default") or {}
    rules = list(default.get("rules", []))
    for rule in selected.get("rules", []):
        if rule not in rules:
            rules.append(rule)
    return {
        "name": profile_name if profile_name in profiles else "default",
        "rules": rules,
        "description": selected.get("description") or default.get("description") or "",
    }


def replace_stars(text: str) -> tuple[str, int]:
    count = len(re.findall(r"\*+", text))
    if count == 0:
        return text, 0
    if re.fullmatch(r"\s*\*+\s*", text):
        return "", count
    text = re.sub(r"\s*\*+\s*", "، ", text)
    text = re.sub(r"(،\s*){2,}", "، ", text)
    text = re.sub(r"\s+،", "،", text)
    return text.strip(), count


def fix_legacy_print_markers(text: str) -> tuple[str, int]:
    original = text
    replacements = [
        (r"ط\([،.]-", "، "),
        (r"ط\([،.]\)", "، "),
        (r"ط\([،.]", "، "),
        (r"-ط\([،.]\)", "، "),
        (r"-ط\([،.]", "، "),
        (r"-\)", "، "),
        (r":\)", ": "),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    text = re.sub(r"\s*-\s*،\s*", "، ", text)
    text = re.sub(r"\s*،\s*", "، ", text)
    text = re.sub(r"^(?:،\s*)+", "", text)
    text = re.sub(r"(?:\s*،)+$", "", text)
    text = re.sub(r"(،\s*){2,}", "، ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text, int(text != original)


def apply_profile_rules(text: str, rules: list[str]) -> tuple[str, Counter[str]]:
    counts: Counter[str] = Counter()

    for rule in rules:
        if rule == "fix_legacy_print_markers":
            text, changed = fix_legacy_print_markers(text)
            counts[rule] += changed
        elif rule == "drop_runtime_error_lines":
            if RUNTIME_ERROR_RE.search(text):
                counts[rule] += 1
                return "", counts

    return text, counts


def clean_text(text: str, rules: list[str]) -> tuple[str, Counter[str]]:
    counts: Counter[str] = Counter()

    new = BIDI_CONTROL_RE.sub("", text)
    if new != text:
        counts["bidi_controls_removed"] += 1
    text = new

    if "\u00a0" in text:
        counts["nbsp_replaced"] += text.count("\u00a0")
        text = text.replace("\u00a0", " ")

    if "\u19e6" in text:
        counts["bad_glyph_removed"] += text.count("\u19e6")
        text = text.replace("\u19e6", "")

    if "ـ" in text:
        counts["tatweel_removed"] += text.count("ـ")
        text = text.replace("ـ", "")

    text, star_count = replace_stars(text)
    counts["stars_replaced"] += star_count

    replacements = [
        (r"إِ\s+نَّ", "إِنَّ", "common_particle_joined"),
        (r"إِ\s+لا", "إِلا", "common_particle_joined"),
        (r"إِ\s+لى", "إِلى", "common_particle_joined"),
        (r"إِ\s+ذا", "إِذا", "common_particle_joined"),
        (r"إِ\s+ذْ", "إِذْ", "common_particle_joined"),
        (rf"([{ARABIC_LETTER_RE}])\s+([{ARABIC_DIACRITIC_RE}])", r"\1\2", "diacritic_joined"),
        (rf"([{ARABIC_DIACRITIC_RE}])\s+([{ARABIC_DIACRITIC_RE}])", r"\1\2", "diacritic_joined"),
        (r"\s+([،؛:؟.!])", r"\1", "punctuation_spacing_fixed"),
        (r"([\(（])\s+", r"\1", "paren_spacing_fixed"),
        (r"\s+([\)）])", r"\1", "paren_spacing_fixed"),
        (r"\s{2,}", " ", "spaces_collapsed"),
    ]
    for pattern, replacement, key in replacements:
        text, changed = re.subn(pattern, replacement, text)
        counts[key] += changed

    text, profile_counts = apply_profile_rules(text, rules)
    counts.update(profile_counts)

    return text.strip(), counts


def clean_line(line: str, rules: list[str]) -> tuple[str, Counter[str]]:
    heading = HEADING_RE.match(line)
    if heading:
        cleaned, counts = clean_text(heading.group(2), rules)
        return f"{heading.group(1)} {cleaned}".rstrip(), counts
    return clean_text(line, rules)


def add_suspicious(
    suspicious: list[dict[str, Any]],
    line_number: int,
    passage_id: str | None,
    text: str,
) -> None:
    if len(suspicious) >= 250:
        return
    for name, pattern in SUSPICIOUS_PATTERNS:
        if pattern.search(text):
            suspicious.append(
                {
                    "line": line_number,
                    "passage_id": passage_id,
                    "pattern": name,
                    "text": text[:220],
                }
            )


def clean_manuscript(source: Path, profile: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    output_lines: list[str] = []
    counts: Counter[str] = Counter()
    suspicious: list[dict[str, Any]] = []
    in_frontmatter = False
    frontmatter_seen = False
    current_passage_id: str | None = None

    for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if stripped == "---" and not frontmatter_seen:
            in_frontmatter = True
            frontmatter_seen = True
            output_lines.append(line)
            continue
        if stripped == "---" and in_frontmatter:
            in_frontmatter = False
            output_lines.append(line)
            continue
        if in_frontmatter:
            output_lines.append(line)
            continue

        passage = PASSAGE_RE.match(line)
        if passage:
            current_passage_id = passage.group(1)
            output_lines.append(line)
            continue

        if not stripped:
            output_lines.append("")
            continue

        cleaned, line_counts = clean_line(line, profile.get("rules", []))
        counts.update(line_counts)
        add_suspicious(suspicious, line_number, current_passage_id, cleaned)
        output_lines.append(cleaned)

    text = "\n".join(output_lines).rstrip() + "\n"
    report = {
        "source": str(source),
        "profile": profile,
        "lines": len(output_lines),
        "changes": dict(sorted(counts.items())),
        "suspicious_samples": suspicious,
    }
    return text, report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-dir", required=True, type=Path)
    parser.add_argument("--input", default="manuscript.md")
    parser.add_argument("--output", default="clean/manuscript.md")
    parser.add_argument("--report", default="clean/cleaning-report.json")
    parser.add_argument("--profile", help="Cleaning profile name. Defaults to the book id.")
    parser.add_argument(
        "--profiles",
        default=DEFAULT_PROFILES_PATH,
        type=Path,
        help="YAML file containing cleaning profiles.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    book_dir = args.book_dir.resolve()
    source = book_dir / args.input
    output = book_dir / args.output
    report_path = book_dir / args.report

    if not source.exists():
        raise SystemExit(f"Input manuscript not found: {source}")

    book_id = load_book_id(book_dir)
    profile = load_cleaning_profile(args.profiles, args.profile or book_id)
    cleaned, report = clean_manuscript(source, profile)
    report["book_id"] = book_id
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(cleaned, encoding="utf-8")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {output}")
    print(f"Wrote {report_path}")


if __name__ == "__main__":
    main()
