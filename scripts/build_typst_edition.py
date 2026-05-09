#!/usr/bin/env python3
"""Build a Typst print edition from a canonical Surau manuscript."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
PASSAGE_RE = re.compile(r'^::passage\{id="([^"]+)"\}\s*$')
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LAYOUT_DIR = PROJECT_ROOT / "layouts" / "surau-arabic-book"
ANNOTATION_ROLE_MAP = {
    "ayah": "ayat",
    "ayat": "ayat",
    "body": "body",
    "biography": "body",
    "dua": "matn",
    "hadith": "quote",
    "list": "body",
    "matn": "matn",
    "poem": "poem",
    "quote": "quote",
    "source_catalog": "body",
}
SEGMENT_KIND_MAP = {
    "ayah": "ayah",
    "ayat": "ayah",
    "body": "body",
    "dua": "dua",
    "hadith": "hadith",
    "matn": "matn",
    "poem": "poem",
    "prose": "body",
    "quote": "quote",
}


def load_yaml(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise SystemExit("PyYAML is required for Typst edition generation.")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def typst_escape_text(text: str) -> str:
    replacements = {
        "\\": r"\\",
        "#": r"\#",
        "[": r"\[",
        "]": r"\]",
        "$": r"\$",
        "*": r"\*",
        "_": r"\_",
        "`": r"\`",
        "@": r"\@",
        "<": r"\<",
        ">": r"\>",
    }
    return "".join(replacements.get(char, char) for char in text)


def typst_escape_string(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def resolve_book_path(book_dir: Path, path: Path | None) -> Path | None:
    if path is None:
        return None
    if path.is_absolute():
        return path
    return book_dir / path


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
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


def load_annotations(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    if not path.exists():
        raise SystemExit(f"Annotation file not found: {path}")

    annotations: dict[str, dict[str, Any]] = {}
    duplicate_ids = []
    for row in read_jsonl(path):
        pid = row.get("id")
        if not pid:
            continue
        if pid in annotations:
            duplicate_ids.append(pid)
        annotations[pid] = row
    if duplicate_ids:
        raise SystemExit(
            f"Duplicate annotation IDs in {path}: {', '.join(sorted(set(duplicate_ids))[:10])}"
        )
    return annotations


def parse_manuscript(path: Path) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    in_frontmatter = False
    frontmatter_seen = False
    current_passage_id: str | None = None
    current_lines: list[str] = []
    heading_stack: list[str] = []

    def flush_passage() -> None:
        nonlocal current_passage_id, current_lines
        if current_passage_id is None:
            return
        text = "\n".join(current_lines).strip()
        if text:
            elements.append(
                {
                    "type": "passage",
                    "id": current_passage_id,
                    "text": text,
                    "section_path": list(heading_stack),
                }
            )
        current_passage_id = None
        current_lines = []

    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() == "---" and not frontmatter_seen:
            in_frontmatter = True
            frontmatter_seen = True
            continue
        if line.strip() == "---" and in_frontmatter:
            in_frontmatter = False
            continue
        if in_frontmatter:
            continue

        passage_match = PASSAGE_RE.match(line)
        if passage_match:
            flush_passage()
            current_passage_id = passage_match.group(1)
            continue

        heading_match = HEADING_RE.match(line)
        if heading_match:
            flush_passage()
            level = len(heading_match.group(1))
            heading_stack[:] = heading_stack[: level - 1]
            heading_stack.append(heading_match.group(2))
            elements.append(
                {
                    "type": "heading",
                    "level": level,
                    "text": heading_match.group(2),
                    "section_path": list(heading_stack),
                }
            )
            continue

        if current_passage_id is not None:
            current_lines.append(line)

    flush_passage()
    return elements


def relative_typst_path(from_dir: Path, target: Path) -> str:
    return Path(os.path.relpath(target, start=from_dir)).as_posix()


def render_layout_copy(path: Path) -> str:
    return (
        f"// Generated from {relative_typst_path(PROJECT_ROOT, path)}.\n"
        "// Edit the source layout template, then regenerate this edition.\n\n"
        + path.read_text(encoding="utf-8")
    )


def normalize_arabic_spacing(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def detect_passage_role(text: str, section_path: list[str]) -> str:
    compact = normalize_arabic_spacing(text)
    active_section = " / ".join(section_path)

    if compact.startswith(("قال تعالى", "قوله تعالى")):
        return "ayat"

    if (
        compact.startswith(("اللَّهُمَّ", "اللهم", "إِ نَّ اللّٰه", "إِنَّ اللّٰه", "إن الله"))
        and len(compact) <= 1800
    ):
        return "matn"

    if active_section.find("الصلاة ") >= 0 and len(compact) <= 1600:
        shalawat_openers = (
            "اللَّهُمَّ",
            "اللهم",
            "إِ نَّ اللّٰه",
            "إِنَّ اللّٰه",
            "إن الله",
            "صَلِّ",
            "صل",
        )
        if compact.startswith(shalawat_openers):
            return "matn"

    if compact.startswith(("بسم اللّٰه", "بسم الله")) and len(compact) <= 220:
        return "matn"

    return "body"


def annotation_role(annotation: dict[str, Any]) -> str | None:
    role = annotation.get("role")
    if isinstance(role, str) and role in ANNOTATION_ROLE_MAP.values():
        return role

    kind = annotation.get("kind")
    if isinstance(kind, str):
        return ANNOTATION_ROLE_MAP.get(kind)

    layout = annotation.get("layout")
    if isinstance(layout, str):
        if layout.endswith("_block"):
            layout = layout.removesuffix("_block")
        return ANNOTATION_ROLE_MAP.get(layout)

    return None


def is_punctuation_fragment(text: str) -> bool:
    stripped = (text or "").strip()
    return bool(stripped) and all(char in "،,؛;:.}{[]()ـ*- " for char in stripped)


def display_span_bounds(text: str, segment: dict[str, Any], start: int, end: int) -> tuple[int, int, int, int]:
    """Return source bounds plus visual wrapper bounds for segment rendering.

    The canonical segment remains start/end. display_start/display_end may consume
    old print delimiters around Quran spans so they do not hang in the new layout.
    """

    display_start = start
    display_end = end
    kind = segment.get("kind")
    if kind in {"ayah", "ayat"}:
        cursor = start - 1
        while cursor >= 0 and text[cursor].isspace():
            cursor -= 1
        if cursor >= 0 and text[cursor] == "}":
            display_start = cursor

        cursor = end
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if cursor < len(text) and text[cursor] == "{":
            display_end = cursor + 1

    return start, end, display_start, display_end


def semantic_segments_for_text(text: str, annotation: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not annotation:
        return []

    proposal = annotation.get("llm_proposal")
    if not isinstance(proposal, dict):
        return []

    raw_segments = proposal.get("segments")
    if not isinstance(raw_segments, list):
        return []

    segments: list[dict[str, Any]] = []
    for segment in raw_segments:
        if not isinstance(segment, dict):
            continue
        kind = SEGMENT_KIND_MAP.get(str(segment.get("kind") or ""))
        source_span = segment.get("source_span")
        if not kind or not isinstance(source_span, dict):
            continue
        start = source_span.get("start")
        end = source_span.get("end")
        segment_text = str(segment.get("text") or "")
        if not isinstance(start, int) or not isinstance(end, int):
            continue
        if start < 0 or end <= start or end > len(text):
            continue
        if text[start:end] != segment_text:
            continue
        source_start, source_end, display_start, display_end = display_span_bounds(
            text,
            segment,
            start,
            end,
        )
        segments.append(
            {
                "kind": kind,
                "span_id": str(segment.get("span_id") or source_span.get("span_id") or ""),
                "text": segment_text,
                "ref": str(segment.get("ref") or ""),
                "review_required": bool(segment.get("review_required")),
                "source_start": source_start,
                "source_end": source_end,
                "display_start": display_start,
                "display_end": display_end,
            }
        )

    segments.sort(key=lambda item: (item["display_start"], item["display_end"]))
    clean_segments: list[dict[str, Any]] = []
    cursor = 0
    for segment in segments:
        if segment["display_start"] < cursor:
            continue
        clean_segments.append(segment)
        cursor = segment["display_end"]
    return clean_segments


def annotate_passage_roles(
    elements: list[dict[str, Any]],
    annotations: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    annotations = annotations or {}
    for element in elements:
        if element["type"] == "passage":
            auto_role = detect_passage_role(
                element["text"],
                element.get("section_path", []),
            )
            annotation = annotations.get(element["id"])
            role = annotation_role(annotation) if annotation else None
            element["role"] = detect_passage_role(
                element["text"],
                element.get("section_path", []),
            )
            element["role"] = role or auto_role
            if annotation:
                element["annotation"] = {
                    key: annotation[key]
                    for key in ("kind", "layout", "status", "confidence", "signals")
                    if key in annotation
                }
                segments = semantic_segments_for_text(element["text"], annotation)
                if segments:
                    element["segments"] = segments
    return elements


def render_typst_elements(
    elements: list[dict[str, Any]],
    source_name: str,
    components_import: str,
) -> str:
    lines = [
        f"// Generated from {source_name}. Edit manuscript.md, then regenerate this file.",
        f'#import "{typst_escape_string(components_import)}": passage, semantic_segment',
        "",
    ]
    for element in elements:
        if element["type"] == "heading":
            level = min(max(int(element["level"]), 1), 6)
            lines.append(f"{'=' * level} {typst_escape_text(element['text'])}")
            lines.append("")
            continue

        lines.extend(render_passage_element(element))
    return "\n".join(lines).rstrip() + "\n"


def render_plain_fragment(lines: list[str], text: str) -> None:
    if not text or not text.strip() or is_punctuation_fragment(text):
        return
    lines.append(typst_escape_text(text.strip()))
    lines.append("")


def render_semantic_segment(lines: list[str], passage_id: str, segment: dict[str, Any]) -> None:
    kind = typst_escape_string(segment["kind"])
    span_id = typst_escape_string(segment.get("span_id") or "")
    full_id = typst_escape_string(f"{passage_id}:{span_id}" if span_id else passage_id)
    ref = str(segment.get("ref") or "").strip()
    source_arg = "[]" if not ref else f"[{typst_escape_text(ref)}]"
    review = "true" if segment.get("review_required") else "false"
    lines.append(
        f'#semantic_segment("{kind}", id: "{full_id}", source: {source_arg}, review: {review})['
    )
    lines.append(typst_escape_text(segment["text"]))
    lines.append("]")
    lines.append("")


def render_passage_element(element: dict[str, Any]) -> list[str]:
    pid = typst_escape_string(element["id"])
    role = typst_escape_string(element.get("role") or "body")
    segments = element.get("segments") or []
    if not segments:
        return [
            f'#passage("{pid}", role: "{role}")[',
            typst_escape_text(element["text"]),
            "]",
            "",
        ]

    lines = [f'#passage("{pid}", role: "body")[']
    cursor = 0
    text = element["text"]
    for segment in segments:
        render_plain_fragment(lines, text[cursor : segment["display_start"]])
        render_semantic_segment(lines, element["id"], segment)
        cursor = segment["display_end"]
    render_plain_fragment(lines, text[cursor:])
    lines.append("]")
    lines.append("")
    return lines


def render_entrypoint_typ(
    book: dict[str, Any],
    edition: str,
    style: str,
    content_file: str,
    theme_import: str,
    cover_title_id: str | None = None,
    cover_author: str | None = None,
    cover_edition: str | None = None,
) -> str:
    title_ar = book.get("title_ar") or book.get("id") or ""
    title_id = cover_title_id if cover_title_id is not None else book.get("title_id") or ""
    author = cover_author if cover_author is not None else book.get("author_ar") or book.get("author") or ""
    edition_label = cover_edition if cover_edition is not None else edition
    work_id = book.get("id") or ""
    document_title = typst_escape_string(title_ar)
    document_author = typst_escape_string(author)
    title_ar_text = typst_escape_text(title_ar)
    title_id_text = typst_escape_text(title_id)
    author_text = typst_escape_text(author)
    edition_text = typst_escape_text(edition_label)

    return f"""// Surau print edition generated from canonical manuscript.
// work_id: {work_id}
// edition: {edition}
// style: {style}

#set document(title: "{document_title}", author: "{document_author}")

#import "{typst_escape_string(theme_import)}": apply_theme, cover, table_of_contents

#show: apply_theme.with(style: "{style}")

#cover(
  [{title_ar_text}],
  [{title_id_text}],
  [{author_text}],
  [{edition_text}],
  style: "{style}",
)

#pagebreak()

#table_of_contents()

#pagebreak()

#include "{content_file}"
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-dir", required=True, type=Path)
    parser.add_argument("--edition", default="surau-v0")
    parser.add_argument(
        "--manuscript",
        default="manuscript.md",
        help="Manuscript path relative to --book-dir.",
    )
    parser.add_argument(
        "--style",
        default="classic-turath",
        choices=("classic-turath", "clean-modern", "ornamental-majlis", "enhanced-compact"),
        help="Layout style from the selected Typst template.",
    )
    parser.add_argument(
        "--annotations",
        type=Path,
        help="Optional semantic annotation JSONL path, relative to --book-dir.",
    )
    parser.add_argument("--cover-title-id", help="Override cover subtitle/title_id.")
    parser.add_argument("--cover-author", help="Override cover author display.")
    parser.add_argument("--cover-edition", help="Override cover edition display.")
    parser.add_argument(
        "--layout-dir",
        default=DEFAULT_LAYOUT_DIR,
        type=Path,
        help="Directory containing Surau Typst layout modules.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    book_dir = args.book_dir.resolve()
    layout_dir = args.layout_dir.resolve()
    edition_dir = book_dir / "editions" / args.edition
    edition_dir.mkdir(parents=True, exist_ok=True)
    theme_import = "theme.typ"
    components_import = "components.typ"

    book = load_yaml(book_dir / "book.yml")
    manuscript_path = (book_dir / args.manuscript).resolve()
    annotations_path = resolve_book_path(book_dir, args.annotations)
    annotations = load_annotations(annotations_path)
    elements = annotate_passage_roles(parse_manuscript(manuscript_path), annotations)

    (edition_dir / "book.typ").write_text(
        render_entrypoint_typ(
            book,
            args.edition,
            args.style,
            "content.typ",
            theme_import,
            cover_title_id=args.cover_title_id,
            cover_author=args.cover_author,
            cover_edition=args.cover_edition,
        ),
        encoding="utf-8",
    )
    (edition_dir / "theme.typ").write_text(
        render_layout_copy(layout_dir / "theme.typ"),
        encoding="utf-8",
    )
    (edition_dir / "components.typ").write_text(
        render_layout_copy(layout_dir / "components.typ"),
        encoding="utf-8",
    )
    (edition_dir / "content.typ").write_text(
        render_typst_elements(elements, args.manuscript, components_import),
        encoding="utf-8",
    )
    role_counts: dict[str, int] = {}
    annotation_kind_counts: dict[str, int] = {}
    semantic_segment_kind_counts: dict[str, int] = {}
    annotated_count = 0
    for element in elements:
        if element["type"] == "passage":
            role = element.get("role") or "body"
            role_counts[role] = role_counts.get(role, 0) + 1
            for segment in element.get("segments") or []:
                segment_kind = str(segment.get("kind") or "unknown")
                semantic_segment_kind_counts[segment_kind] = (
                    semantic_segment_kind_counts.get(segment_kind, 0) + 1
                )
            annotation = element.get("annotation")
            if isinstance(annotation, dict):
                annotated_count += 1
                kind = str(annotation.get("kind") or "unknown")
                annotation_kind_counts[kind] = annotation_kind_counts.get(kind, 0) + 1

    (edition_dir / "build-info.json").write_text(
        json.dumps(
            {
                "work_id": book.get("id"),
                "edition": args.edition,
                "style": args.style,
                "layout": str(layout_dir),
                "theme_import": theme_import,
                "components_import": components_import,
                "source": str(manuscript_path),
                "annotations": str(annotations_path) if annotations_path else None,
                "annotated_passages": annotated_count,
                "annotation_kinds": annotation_kind_counts,
                "semantic_segments": sum(semantic_segment_kind_counts.values()),
                "semantic_segment_kinds": semantic_segment_kind_counts,
                "elements": len(elements),
                "passages": sum(1 for element in elements if element["type"] == "passage"),
                "passage_roles": role_counts,
                "headings": sum(1 for element in elements if element["type"] == "heading"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Wrote {edition_dir / 'book.typ'}")
    print(f"Wrote {edition_dir / 'theme.typ'}")
    print(f"Wrote {edition_dir / 'components.typ'}")
    print(f"Wrote {edition_dir / 'content.typ'}")
    print(f"Wrote {edition_dir / 'build-info.json'}")


if __name__ == "__main__":
    main()
