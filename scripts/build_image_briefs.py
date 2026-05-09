#!/usr/bin/env python3
"""Draft parked English image brief notes for possible future chapter separators."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
PASSAGE_RE = re.compile(r'^::passage\{id="([^"]+)"\}\s*$')

GLOBAL_NEGATIVE_PROMPT = (
    "No depiction of Prophet Muhammad, companions, angels, Jibril/Gabriel, divine beings, "
    "heaven, hell, resurrection scenes, or unseen realities. No photorealistic people, no faces, "
    "no fake historical reenactment, no pseudo-Arabic calligraphy, no readable sacred text, "
    "no stock-photo look, no neon cyberpunk style, no cluttered collage, no sectarian symbols."
)

BASE_STYLE = (
    "Modern Islamic editorial illustration for a printed classical Arabic book, refined and "
    "youthful but dignified, abstract Islamic geometry, manuscript paper texture, subtle ink "
    "grain, restrained warm highlights, elegant negative space, premium book-design quality, "
    "no text rendered inside the image."
)


def project_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists() or yaml is None:
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
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")


def compact(text: str, limit: int = 420) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def parse_levels(value: str) -> set[int]:
    levels = set()
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        levels.add(int(item))
    return levels


def parse_manuscript_sections(path: Path) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    heading_stack: list[str] = []
    current: dict[str, Any] | None = None
    current_passage_id: str | None = None

    def ensure_context() -> None:
        nonlocal current
        if current is not None:
            return

    for line in path.read_text(encoding="utf-8").splitlines():
        heading = HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            title = heading.group(2).strip()
            heading_stack = heading_stack[: level - 1]
            heading_stack.append(title)
            current = {
                "level": level,
                "title": title,
                "section_path": list(heading_stack),
                "passage_ids": [],
                "text_parts": [],
            }
            sections.append(current)
            current_passage_id = None
            continue

        passage = PASSAGE_RE.match(line)
        if passage:
            ensure_context()
            current_passage_id = passage.group(1)
            if current is not None:
                current["passage_ids"].append(current_passage_id)
            continue

        if current is not None and current_passage_id and line.strip():
            current["text_parts"].append(line.strip())

    return sections


def semantic_by_id(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    return {
        row["id"]: row
        for row in read_jsonl(path)
        if isinstance(row, dict) and row.get("id")
    }


def section_semantic_summary(section: dict[str, Any], annotations: dict[str, dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for pid in section.get("passage_ids", []):
        row = annotations.get(pid) or {}
        kind = row.get("kind")
        if kind:
            counts[str(kind)] = counts.get(str(kind), 0) + 1
        proposal = row.get("llm_proposal")
        proposal = proposal if isinstance(proposal, dict) else {}
        for segment in proposal.get("segments") or []:
            if isinstance(segment, dict) and segment.get("kind"):
                key = f"segment:{segment['kind']}"
                counts[key] = counts.get(key, 0) + 1
    return counts


def derive_image_prefix(work_id: str, sections: list[dict[str, Any]]) -> str:
    for section in sections:
        for pid in section.get("passage_ids") or []:
            match = re.match(r"^([A-Z]+)-\d+", str(pid))
            if match:
                return match.group(1)
    return "".join(part[:1].upper() for part in work_id.split("-") if part)[:4] or "IMG"


def theme_from_section(title: str, section_path: list[str], semantic_counts: dict[str, int]) -> tuple[str, str]:
    joined = " ".join([*section_path, title])

    if "عن المؤلف" in joined:
        return (
            "biographical_preface",
            "A respectful biographical opener using layered manuscript pages, a subtle Eastern Mediterranean map texture, archival ink, and quiet scholarly atmosphere.",
        )
    if "مقدمة" in joined:
        return (
            "opening_invocation",
            "An opening illumination suggesting gratitude, devotion, and the beginning of a classical manuscript journey through soft paper, ink, and geometric light.",
        )
    if "الجمعة" in joined:
        return (
            "friday_salawat",
            "A contemplative Friday-themed separator with soft daylight, mosque-inspired geometry, prayer-bead and ink symbolism, and a quiet devotional mood.",
        )
    if "شفاع" in joined:
        return (
            "hope_and_intercession",
            "A hopeful abstract composition with layered light, open space, and gentle geometric arcs suggesting mercy and nearness without depicting unseen realities.",
        )
    if "التحذير" in joined:
        return (
            "serious_admonition",
            "A serious editorial divider with restrained contrast, shadowed manuscript texture, precise geometry, and a reflective tone of warning and remembrance.",
        )
    if "الفوائد" in joined or "المنافع" in joined:
        return (
            "benefits_and_fruits",
            "A visual metaphor of benefits branching from a central ink mark into refined geometric leaves, warm restrained light, and manuscript paper texture.",
        )
    if "تفسير" in joined or "آية" in joined or semantic_counts.get("segment:ayah", 0):
        return (
            "quranic_reflection",
            "An abstract Qur'anic reflection scene using luminous geometric illumination, layered manuscript margins, and a calm reverent atmosphere without rendering scripture.",
        )
    if "الأحاديث" in joined or semantic_counts.get("hadith", 0) or semantic_counts.get("segment:hadith", 0):
        return (
            "hadith_transmission",
            "An abstract hadith transmission visual: fine connected nodes and lines like a sanad network, manuscript margins, ink dots, and disciplined scholarly rhythm.",
        )
    if "الصلاة" in joined:
        return (
            "salawat_formula",
            "An elegant devotional formula separator with flowing ornamental geometry, ink trails, subtle paper grain, and a calm rhythm suitable for salawat texts.",
        )
    if "القصيدة" in joined or semantic_counts.get("poem", 0):
        return (
            "poetic_closing",
            "A poetic manuscript composition with measured ink strokes, margin ornaments, soft paper texture, and visual rhythm inspired by classical qasidah.",
        )
    if "القسم" in joined:
        return (
            "book_structure",
            "A structural chapter-opening image with nested geometric frames, manuscript tabs, and a refined visual map of the book's major part.",
        )
    return (
        "modern_turath",
        "A refined turath chapter separator with abstract Islamic geometry, manuscript texture, ink accents, and spacious modern editorial composition.",
    )


def prompt_for_section(
    book: dict[str, Any],
    section: dict[str, Any],
    semantic_counts: dict[str, int],
    aspect_ratio: str,
) -> tuple[str, str, str]:
    title = section["title"]
    theme, theme_sentence = theme_from_section(title, section.get("section_path") or [], semantic_counts)
    book_title = book.get("title_id") or book.get("title_ar") or book.get("id") or "classical Islamic book"
    section_level = section.get("level")
    prompt = (
        f"{BASE_STYLE} Create a chapter separator image for '{book_title}', section level {section_level}. "
        f"Theme: {theme_sentence} The image should feel contemporary for young readers while preserving the dignity of a classical Islamic text. "
        f"Use balanced composition for a {aspect_ratio} print layout, with space where a designer can place the Arabic chapter title separately in Typst. "
        f"Do not include any readable text, letters, logos, watermarks, or human figures."
    )
    return theme, prompt, GLOBAL_NEGATIVE_PROMPT


def build_brief(
    book: dict[str, Any],
    work_id: str,
    prefix: str,
    index: int,
    section: dict[str, Any],
    semantic_counts: dict[str, int],
    aspect_ratio: str,
) -> dict[str, Any]:
    theme, prompt, negative_prompt = prompt_for_section(book, section, semantic_counts, aspect_ratio)
    passage_ids = section.get("passage_ids") or []
    return {
        "schema_version": 0.1,
        "id": f"{prefix}-IMG-{index:04d}",
        "work_id": work_id,
        "placement": "chapter_separator",
        "section_level": section.get("level"),
        "section_path": section.get("section_path") or [],
        "section_title": section.get("title"),
        "related_passage_ids": passage_ids[:12],
        "passage_count": len(passage_ids),
        "context_preview": compact(" ".join(section.get("text_parts") or []), 520),
        "semantic_counts": semantic_counts,
        "image_type": "editorial_illustration",
        "style_preset": theme,
        "aspect_ratio": aspect_ratio,
        "prompt_language": "en",
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "status": "draft",
        "pipeline_status": "parked_experimental",
        "review_required": True,
        "safety_notes": [
            "Prompt is visual planning only; it does not change canonical Arabic text or citation.",
            "This visual layer is parked; do not generate or wire image assets into active Typst builds yet.",
            "Do not generate depictions of prophets, companions, angels, divine beings, heaven, hell, or unseen realities.",
            "Do not ask the image model to render Arabic text; add reviewed typography later in Typst.",
        ],
        "asset_path": None,
        "generated_by": "scripts/build_image_briefs.py",
    }


def render_markdown(book: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = [
        f"# Image Brief Review: {book.get('title_id') or book.get('id')}",
        "",
        "These are parked English draft prompts for possible future chapter separator images. They are not active layout inputs and are not final assets.",
        "",
        "| ID | Level | Section | Theme | Passages | Status | Pipeline |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{row['id']}`",
                    str(row.get("section_level")),
                    compact(" > ".join(row.get("section_path") or []), 90),
                    f"`{row.get('style_preset')}`",
                    str(row.get("passage_count") or len(row.get("related_passage_ids") or [])),
                    f"`{row.get('status')}`",
                    f"`{row.get('pipeline_status')}`",
                ]
            )
            + " |"
        )

    lines.extend(["", "## Briefs", ""])
    for row in rows:
        lines.extend(
            [
                f"### {row['id']}",
                "",
                f"- Section: `{ ' > '.join(row.get('section_path') or []) }`",
                f"- Theme: `{row.get('style_preset')}`",
                f"- Aspect ratio: `{row.get('aspect_ratio')}`",
                f"- Related passages: `{', '.join(row.get('related_passage_ids') or [])}`",
                "",
                "**Prompt**",
                "",
                "```text",
                row.get("prompt") or "",
                "```",
                "",
                "**Negative Prompt**",
                "",
                "```text",
                row.get("negative_prompt") or "",
                "```",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-dir", required=True, type=Path)
    parser.add_argument("--manuscript", default="clean/manuscript.md")
    parser.add_argument("--annotations", default="annotations/semantic-reviewed.jsonl")
    parser.add_argument("--levels", default="1,2")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--aspect-ratio", default="16:9")
    parser.add_argument("--prefix")
    parser.add_argument("--out", help="Defaults to assets/image-briefs.jsonl")
    parser.add_argument("--review-md", help="Defaults to reports/image-briefs/{work_id}-image-briefs.md")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    book_dir = args.book_dir.resolve()
    book = load_yaml(book_dir / "book.yml")
    work_id = book.get("id") or book_dir.name
    levels = parse_levels(args.levels)
    manuscript_path = book_dir / args.manuscript
    annotations_path = book_dir / args.annotations if args.annotations else None

    sections = [
        section
        for section in parse_manuscript_sections(manuscript_path)
        if section.get("level") in levels and section.get("passage_ids")
    ]
    if args.limit is not None:
        sections = sections[: args.limit]
    prefix = args.prefix or derive_image_prefix(work_id, sections)

    annotations = semantic_by_id(annotations_path)
    rows = [
        build_brief(
            book,
            work_id,
            prefix,
            index,
            section,
            section_semantic_summary(section, annotations),
            args.aspect_ratio,
        )
        for index, section in enumerate(sections, start=1)
    ]

    out_path = book_dir / (args.out or "assets/image-briefs.jsonl")
    write_jsonl(out_path, rows)

    review_path = Path(args.review_md) if args.review_md else PROJECT_ROOT / "reports" / "image-briefs" / f"{work_id}-image-briefs.md"
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text(render_markdown(book, rows), encoding="utf-8")

    print(f"ok: wrote {project_relative(out_path)} rows={len(rows)}")
    print(f"ok: wrote {project_relative(review_path)}")


if __name__ == "__main__":
    main()
