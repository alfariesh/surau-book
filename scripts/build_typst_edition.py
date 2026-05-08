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
    "matn": "matn",
    "poem": "poem",
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
    return elements


def render_typst_elements(
    elements: list[dict[str, Any]],
    source_name: str,
    components_import: str,
) -> str:
    lines = [
        f"// Generated from {source_name}. Edit manuscript.md, then regenerate this file.",
        f'#import "{typst_escape_string(components_import)}": passage',
        "",
    ]
    for element in elements:
        if element["type"] == "heading":
            level = min(max(int(element["level"]), 1), 6)
            lines.append(f"{'=' * level} {typst_escape_text(element['text'])}")
            lines.append("")
            continue

        pid = typst_escape_string(element["id"])
        text = typst_escape_text(element["text"])
        role = typst_escape_string(element.get("role") or "body")
        lines.append(f'#passage("{pid}", role: "{role}")[')
        lines.append(text)
        lines.append("]")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


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
    annotated_count = 0
    for element in elements:
        if element["type"] == "passage":
            role = element.get("role") or "body"
            role_counts[role] = role_counts.get(role, 0) + 1
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
