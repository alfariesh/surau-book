#!/usr/bin/env python3
"""Build draft semantic annotations for a Surau manuscript.

The output is intentionally reviewable JSONL. It should guide layout/API/RAG,
but it must not mutate the canonical Arabic text.
"""

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

from build_typst_edition import detect_passage_role, parse_manuscript


QURAN_SIGNAL_RE = re.compile(
    r"(?:قال تعالى|قوله تعالى|فقال تعالى|لقوله تعالى|قال اللّٰه|قال الله|[}][^{}\n]{5,220}[{])"
)
HADITH_OPENERS = (
    "قال رسول اللّٰه",
    "قال رسول الله",
    "وقال رسول اللّٰه",
    "وقال رسول الله",
    "قال النبي",
    "وقال النبي",
    "وكان صلى اللّٰه عليه وسلم يقول",
    "وكان صلى الله عليه وسلم يقول",
    "وقال صلى اللّٰه عليه وسلم",
    "وقال صلى الله عليه وسلم",
)
MATN_OPENERS = (
    "اللَّهُمَّ",
    "اللهم",
    "إِ نَّ اللّٰه",
    "إِنَّ اللّٰه",
    "إن اللّٰه",
    "إن الله",
    "صَلِّ",
)


def load_yaml(path: Path) -> dict[str, Any]:
    if yaml is None or not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{line_no}: {exc}") from exc
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def truncate(text: str, limit: int = 180) -> str:
    text = normalize(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def role_to_layout(role: str) -> str:
    return {
        "ayat": "ayah_text_block",
        "body": "body",
        "matn": "matn_block",
        "poem": "poem_block",
        "quote": "quote_block",
    }.get(role, "body")


def role_to_kind(role: str) -> str:
    return "ayah" if role == "ayat" else role


def infer_annotation(
    element: dict[str, Any],
    sequence_by_id: dict[str, int],
    work_id: str,
) -> dict[str, Any]:
    original_text = str(element["text"] or "").strip()
    text = normalize(original_text)
    section_path = element.get("section_path") or []
    role = detect_passage_role(text, section_path)
    signals = []
    confidence = 0.52

    if role == "matn":
        signals.append("matn_opening_or_shalawat_section")
        confidence = 0.78

    if QURAN_SIGNAL_RE.search(text):
        signals.append("contains_quran_signal")
        if len(text) <= 420 and text.startswith(("قال تعالى", "قوله تعالى", "فقال تعالى")):
            role = "ayat"
            confidence = max(confidence, 0.68)

    if text.startswith(HADITH_OPENERS) and len(text) <= 900:
        role = "quote"
        signals.append("short_hadith_or_report_opening")
        confidence = max(confidence, 0.72)

    original_lines = [line.strip() for line in original_text.splitlines() if line.strip()]
    looks_like_verse_lines = (
        len(original_lines) >= 2
        and max(len(line) for line in original_lines) <= 90
        and sum(1 for line in original_lines if " " in line) >= 2
    )
    if "قصيدة" in " / ".join(section_path) and looks_like_verse_lines and len(text) <= 1200:
        role = "poem"
        signals.append("poetry_section")
        confidence = max(confidence, 0.64)

    if text.startswith(MATN_OPENERS) and len(text) <= 1400:
        role = "matn"
        signals.append("short_devotional_opening")
        confidence = max(confidence, 0.8)

    if not signals:
        signals.append("default_body")

    return {
        "id": element["id"],
        "work_id": work_id,
        "sequence": sequence_by_id.get(element["id"]),
        "kind": role_to_kind(role),
        "role": role,
        "layout": role_to_layout(role),
        "status": "machine_draft",
        "confidence": round(confidence, 2),
        "section_path": section_path,
        "signals": signals,
        "text_preview": truncate(text),
        "generated_by": "scripts/build_semantic_annotations.py",
    }


def build_annotations(book_dir: Path, manuscript: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    book = load_yaml(book_dir / "book.yml")
    work_id = book.get("id") or book_dir.name
    passage_rows = read_jsonl(book_dir / "passages.jsonl")
    sequence_by_id = {
        row["id"]: row.get("sequence")
        for row in passage_rows
        if isinstance(row, dict) and row.get("id")
    }
    elements = parse_manuscript(manuscript)
    annotations = [
        infer_annotation(element, sequence_by_id, work_id)
        for element in elements
        if element["type"] == "passage"
    ]
    kind_counts = Counter(row["kind"] for row in annotations)
    role_counts = Counter(row["role"] for row in annotations)
    low_confidence = [row for row in annotations if row["confidence"] < 0.65]
    summary = {
        "schema_version": "0.1",
        "work_id": work_id,
        "source": str(manuscript),
        "count": len(annotations),
        "kind_counts": dict(sorted(kind_counts.items())),
        "role_counts": dict(sorted(role_counts.items())),
        "low_confidence_count": len(low_confidence),
        "low_confidence_sample": low_confidence[:25],
    }
    return annotations, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-dir", required=True, type=Path)
    parser.add_argument(
        "--manuscript",
        default="clean/manuscript.md",
        help="Manuscript path relative to --book-dir.",
    )
    parser.add_argument(
        "--out",
        default="annotations/semantic-draft.jsonl",
        help="Output JSONL path relative to --book-dir.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    book_dir = args.book_dir.resolve()
    manuscript = (book_dir / args.manuscript).resolve()
    out_path = book_dir / args.out
    annotations, summary = build_annotations(book_dir, manuscript)
    write_jsonl(out_path, annotations)
    summary_path = out_path.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"ok: wrote {out_path} ({len(annotations)} annotations)")
    print(json.dumps(summary["kind_counts"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
