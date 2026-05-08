#!/usr/bin/env python3
"""Extract a PDF book into raw data and an editable structured manuscript."""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import json
import re
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover - older PyMuPDF exposes fitz directly.
    import fitz  # type: ignore


BIDI_CONTROL_RE = re.compile(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
ARABIC_DIACRITICS_RE = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]")
ARABIC_LETTER_RE = r"\u0621-\u064a\u066e-\u06d3"
SECTION_INDEX_SUFFIX_RE = re.compile(r"\s+[0-9٠-٩]+(?:\.[0-9٠-٩]+)+\s*$")
ARABIC_INDIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
WESTERN_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def clean_pdf_text(text: str) -> str:
    """Normalize extraction artifacts while preserving Arabic text."""
    text = BIDI_CONTROL_RE.sub("", text)
    text = text.replace("\u00a0", " ")
    text = text.replace("\u19e6", "")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(rf"([{ARABIC_LETTER_RE}])\s+([\u064b-\u065f\u0670])", r"\1\2", text)
    text = re.sub(r"([\u064b-\u065f\u0670])\s+([\u064b-\u065f\u0670])", r"\1\2", text)
    text = re.sub(r"\s+([،؛:؟.!])", r"\1", text)
    return text.strip()


def match_key(text: str) -> str:
    text = clean_pdf_text(text)
    text = ARABIC_DIACRITICS_RE.sub("", text)
    text = text.translate(ARABIC_INDIC_DIGITS)
    text = re.sub(r"[^\w\u0621-\u064a]+", "", text, flags=re.UNICODE)
    return text


def arabic_page_number(value: int) -> str:
    return str(value).translate(WESTERN_DIGITS)


def project_relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.name


def block_id(work_id: str, pdf_page: int, block_number: int) -> str:
    return f"{work_id}.p{pdf_page:04d}.b{block_number:03d}"


def passage_id(prefix: str, sequence: int) -> str:
    return f"{prefix}-{sequence:05d}"


def round_bbox(bbox: tuple[float, float, float, float]) -> list[float]:
    return [round(value, 2) for value in bbox]


def is_footer_or_header(block: dict[str, Any], page_height: float) -> bool:
    text = block["clean_text"]
    y0 = block["bbox"][1]
    y1 = block["bbox"][3]
    if not text:
        return True
    if y0 < 38:
        return True
    if y1 > page_height - 36:
        return True
    compact = text.replace(" ", "")
    if "Shamela.org" in compact:
        return True
    if re.fullmatch(r"[0-9٠-٩]+", compact):
        return True
    if re.fullmatch(r"[0-9٠-٩]+Shamela\.org", compact):
        return True
    return False


def should_skip_front_page(pdf_page: int, first_toc_page: int, page_text: str) -> bool:
    """Skip cover and TOC pages, but keep the author page if present."""
    if pdf_page >= first_toc_page:
        return False
    if "عن المؤلف" in page_text:
        return False
    return True


def get_toc_entries(doc: fitz.Document) -> list[dict[str, Any]]:
    entries = []
    for index, item in enumerate(doc.get_toc(), start=1):
        level, title, page = item[:3]
        entries.append(
            {
                "index": index,
                "level": int(level),
                "title": clean_pdf_text(title),
                "page": int(page),
                "key": match_key(title),
            }
        )
    return entries


def load_heading_profile(profiles_path: Path, profile_name: str | None) -> dict[str, Any] | None:
    if not profile_name:
        return None
    if yaml is None:
        raise SystemExit("PyYAML is required when --heading-profile is used.")
    if not profiles_path.exists():
        raise SystemExit(f"Heading profiles file not found: {profiles_path}")

    data = yaml.safe_load(profiles_path.read_text(encoding="utf-8")) or {}
    profiles = data.get("profiles", {})
    profile = profiles.get(profile_name)
    if profile is None:
        available = ", ".join(sorted(profiles)) or "<none>"
        raise SystemExit(
            f"Heading profile '{profile_name}' was not found in {profiles_path}. "
            f"Available profiles: {available}"
        )
    return dict(profile)


def rule_matches_heading(rule: dict[str, Any], entry: dict[str, Any]) -> bool:
    source_level = rule.get("source_level")
    if source_level is not None and int(source_level) != int(entry.get("source_level", 0)):
        return False

    pattern = rule.get("pattern")
    if pattern and re.search(str(pattern), entry["title"]) is None:
        return False

    return True


def apply_heading_profile(
    raw: dict[str, Any],
    profile_name: str | None,
    profile: dict[str, Any] | None,
) -> None:
    if not profile_name or not profile:
        return

    mode = profile.get("mode", "toc")
    rules = profile.get("rules", [])
    start_pattern = profile.get("start_pattern")
    biography_body_started = False

    for entry in raw["toc"]:
        source_level = int(entry.get("source_level") or entry["level"])
        entry["source_level"] = source_level
        level = source_level

        if mode == "biography":
            if start_pattern and re.search(str(start_pattern), entry["title"]):
                biography_body_started = True
            default_key = (
                "default_after_start_level"
                if biography_body_started
                else "default_before_start_level"
            )
            level = int(profile.get(default_key, source_level))

        for rule in rules:
            if rule_matches_heading(rule, entry):
                level = int(rule["level"])
                break

        entry["level"] = min(max(level, 1), 6)
        entry["level_source"] = f"profile:{profile_name}"

    deduped_toc = []
    seen_heading_keys: set[tuple[int, str]] = set()
    for entry in raw["toc"]:
        key = (entry["page"], match_key(entry["title"]))
        if key in seen_heading_keys:
            continue
        seen_heading_keys.add(key)
        deduped_toc.append(entry)
    raw["toc"] = deduped_toc
    raw["heading_profile"] = profile_name


def extract_raw(doc: fitz.Document, pdf_path: Path, work_id: str) -> dict[str, Any]:
    pages = []
    for page_index, page in enumerate(doc, start=1):
        page_blocks = []
        raw_blocks = page.get_text("blocks", sort=True)
        for block_number, raw in enumerate(raw_blocks, start=1):
            x0, y0, x1, y1, text, *_ = raw
            clean_text = clean_pdf_text(text)
            page_blocks.append(
                {
                    "id": block_id(work_id, page_index, block_number),
                    "number": block_number,
                    "bbox": round_bbox((x0, y0, x1, y1)),
                    "text": text.strip(),
                    "clean_text": clean_text,
                }
            )
        pages.append(
            {
                "pdf_page": page_index,
                "width": round(page.rect.width, 2),
                "height": round(page.rect.height, 2),
                "text": page.get_text("text").strip(),
                "blocks": page_blocks,
            }
        )

    toc = get_toc_entries(doc)
    return {
        "work_id": work_id,
        "source_pdf": str(pdf_path),
        "extracted_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "metadata": doc.metadata,
        "page_count": doc.page_count,
        "toc": [{k: v for k, v in item.items() if k != "key"} for item in toc],
        "pages": pages,
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def write_raw_markdown(path: Path, raw: dict[str, Any]) -> None:
    lines = [
        "---",
        f"work_id: {raw['work_id']}",
        f"source_pdf: {Path(raw['source_pdf']).name}",
        f"page_count: {raw['page_count']}",
        "status: raw_extraction",
    ]
    if raw.get("heading_profile"):
        lines.append(f"heading_profile: {raw['heading_profile']}")
    lines.extend(
        [
            "---",
            "",
            f"# Raw Extraction: {raw['metadata'].get('title') or raw['work_id']}",
            "",
        ]
    )
    for page in raw["pages"]:
        lines.append(f"## PDF Page {page['pdf_page']}")
        lines.append("")
        for block in page["blocks"]:
            if not block["clean_text"]:
                continue
            bbox = ",".join(str(value) for value in block["bbox"])
            lines.append(f"<!-- block_id={block['id']} bbox={bbox} -->")
            lines.append(block["clean_text"])
            lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def match_heading(
    text: str,
    toc_entries_for_page: list[dict[str, Any]],
    used_toc_indexes: set[int],
) -> dict[str, Any] | None:
    key = match_key(text)
    if not key:
        return None

    best: tuple[float, dict[str, Any] | None] = (0.0, None)
    for entry in toc_entries_for_page:
        if entry["index"] in used_toc_indexes:
            continue
        title_key = entry["key"]
        if not title_key:
            continue
        score = 0.0
        if title_key in key:
            if len(title_key) <= 14 and len(key) > len(title_key) + 6:
                continue
            score = 1.0
        elif key in title_key and len(key) >= 8:
            score = 0.92
        else:
            score = difflib.SequenceMatcher(None, title_key, key).ratio()
        if score > best[0]:
            best = (score, entry)

    if best[1] is not None and best[0] >= 0.62:
        return best[1]
    return None


def heading_candidate_score(entry: dict[str, Any], text: str) -> float:
    key = match_key(text)
    title_key = entry["key"]
    if not key or not title_key:
        return 0.0
    stripped = text.strip()
    title = entry["title"].strip()

    # Prayer headings are often numerically adjacent and very similar in Arabic.
    # Avoid fuzzy matching them; inline occurrences are handled separately below.
    if title.startswith("الصلاة "):
        if stripped == title:
            return 1.0
        if stripped.startswith(title) and not SECTION_INDEX_SUFFIX_RE.search(stripped):
            return 0.99
        return 0.0

    if len(title_key) <= 14 and title_key in key and len(key) > len(title_key) + 6:
        return 0.0

    if title_key in key:
        extra = max(0, len(key) - len(title_key))
        score = 1.0 - min(0.35, extra / max(len(title_key), 1) * 0.12)
    elif key in title_key and len(key) >= 8:
        score = 0.88
    else:
        score = difflib.SequenceMatcher(None, title_key, key).ratio()

    if stripped == title:
        score = 1.0
    elif stripped.startswith(title) and not SECTION_INDEX_SUFFIX_RE.search(stripped):
        score = max(score, 0.99)
    if stripped.startswith("."):
        score -= 0.35
    if SECTION_INDEX_SUFFIX_RE.search(stripped):
        score -= 0.55
    if len(key) <= len(title_key) + 8:
        score += 0.08

    return max(0.0, min(score, 1.0))


def select_heading_blocks(
    blocks: list[dict[str, Any]],
    page_entries: list[dict[str, Any]],
    used_toc_indexes: set[int],
) -> dict[str, dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    used_block_ids: set[str] = set()
    for entry in page_entries:
        if entry["index"] in used_toc_indexes:
            continue
        best_score = 0.0
        best_block: dict[str, Any] | None = None
        for block in blocks:
            if block["id"] in used_block_ids:
                continue
            score = heading_candidate_score(entry, block["clean_text"])
            if score > best_score:
                best_score = score
                best_block = block
        if best_block is not None and best_score >= 0.62:
            selected[best_block["id"]] = entry
            used_block_ids.add(best_block["id"])
    return selected


def is_section_index_line(text: str, page_entries: list[dict[str, Any]]) -> bool:
    stripped = text.strip()
    if not SECTION_INDEX_SUFFIX_RE.search(stripped):
        return False
    text_key = match_key(stripped)
    for entry in page_entries:
        title_key = entry["key"]
        if title_key and title_key in text_key:
            return True
    return False


def is_noise_body_text(text: str) -> bool:
    compact = clean_pdf_text(text).replace(" ", "")
    if not compact:
        return True
    normalized = compact.translate(ARABIC_INDIC_DIGITS)
    if re.fullmatch(r"[0-9.()،؛:؟!\-ـ]+", normalized):
        return True
    return False


def find_inline_heading(
    text: str,
    page_entries: list[dict[str, Any]],
    used_toc_indexes: set[int],
) -> tuple[dict[str, Any], int, int] | None:
    candidates = []
    for entry in page_entries:
        if entry["index"] in used_toc_indexes:
            continue
        title = entry["title"].strip()
        if not title:
            continue
        pos = text.find(title)
        if pos < 0:
            continue
        if pos > 0 and not title.startswith("الصلاة "):
            continue
        candidates.append((len(title), entry, pos, len(title)))
    if not candidates:
        return None
    _, entry, pos, length = max(candidates, key=lambda item: item[0])
    return entry, pos, length


def looks_like_new_passage(text: str, previous_block: dict[str, Any] | None) -> bool:
    if previous_block is None:
        return True
    current_y = previous_block.get("next_y")
    if isinstance(current_y, tuple):
        prev_y1, y0 = current_y
        if y0 - prev_y1 > 18:
            return True
    previous_x0 = previous_block["bbox"][0]
    if previous_x0 > 150:
        return True
    starts = (
        "(فائدة",
        ")فائدة",
        "فائدة",
        "(أما بعد",
        ")أما بعد",
        "قال ",
        "وفي ",
    )
    return text.startswith(starts)


def make_manuscript(
    raw: dict[str, Any],
    prefix: str,
    language: str,
    review_status: str,
) -> tuple[str, list[dict[str, Any]]]:
    toc_entries = []
    for item in raw["toc"]:
        entry = dict(item)
        entry["key"] = match_key(entry["title"])
        toc_entries.append(entry)

    toc_by_page: dict[int, list[dict[str, Any]]] = {}
    for entry in toc_entries:
        toc_by_page.setdefault(entry["page"], []).append(entry)

    first_toc_page = min((entry["page"] for entry in toc_entries), default=1)
    used_toc_indexes: set[int] = set()
    section_stack: list[str] = []
    passages: list[dict[str, Any]] = []
    manuscript_lines = [
        "---",
        f"work_id: {raw['work_id']}",
        f"title_ar: {raw['metadata'].get('title') or ''}",
        "schema_version: 0.1",
        "edition_status: draft_extraction",
        "source_policy: source_pdf_used_as_raw_material_only",
    ]
    if raw.get("heading_profile"):
        manuscript_lines.append(f"heading_profile: {raw['heading_profile']}")
    manuscript_lines.extend(["---", ""])

    buffer: list[str] = []
    buffer_sources: list[dict[str, Any]] = []
    previous_body_block: dict[str, Any] | None = None
    sequence = 1

    def flush() -> None:
        nonlocal sequence, buffer, buffer_sources, previous_body_block
        text = clean_pdf_text(" ".join(buffer))
        if not text:
            buffer = []
            buffer_sources = []
            previous_body_block = None
            return
        pid = passage_id(prefix, sequence)
        manuscript_lines.append(f'::passage{{id="{pid}"}}')
        manuscript_lines.append(text)
        manuscript_lines.append("")
        passages.append(
            {
                "id": pid,
                "work_id": raw["work_id"],
                "sequence": sequence,
                "lang": language,
                "section_path": list(section_stack),
                "text": text,
                "review_status": review_status,
                "source_blocks": buffer_sources,
                "edition_refs": {},
            }
        )
        sequence += 1
        buffer = []
        buffer_sources = []
        previous_body_block = None

    def emit_heading(title: str, level: int) -> None:
        nonlocal section_stack
        flush()
        md_level = min(max(level, 1), 6)
        section_stack = section_stack[: md_level - 1]
        section_stack.append(title)
        manuscript_lines.append(f"{'#' * md_level} {title}")
        manuscript_lines.append("")

    def add_body_text(text: str, block: dict[str, Any]) -> None:
        nonlocal previous_body_block
        text = clean_pdf_text(text)
        if is_noise_body_text(text):
            return

        previous_for_heuristic = previous_body_block
        if previous_for_heuristic is not None:
            previous_for_heuristic = dict(previous_for_heuristic)
            previous_for_heuristic["next_y"] = (
                previous_body_block["bbox"][3],
                block["bbox"][1],
            )
        if looks_like_new_passage(text, previous_for_heuristic):
            flush()
        buffer.append(text)
        buffer_sources.append(
            {
                "pdf_page": block["pdf_page"],
                "block_id": block["id"],
                "bbox": block["bbox"],
            }
        )
        previous_body_block = block

    for page in raw["pages"]:
        pdf_page = page["pdf_page"]
        page_text = clean_pdf_text(page["text"])
        if should_skip_front_page(pdf_page, first_toc_page, page_text):
            continue

        if pdf_page == first_toc_page - 1 and "عن المؤلف" in page_text:
            emit_heading("عن المؤلف", 1)

        page_entries = toc_by_page.get(pdf_page, [])
        clean_blocks = []
        for block in page["blocks"]:
            candidate = dict(block)
            candidate["clean_text"] = clean_pdf_text(candidate["clean_text"])
            if is_footer_or_header(candidate, page["height"]):
                continue
            clean_blocks.append(candidate)

        heading_blocks = select_heading_blocks(clean_blocks, page_entries, used_toc_indexes)
        for index, block in enumerate(clean_blocks):
            text = block["clean_text"]
            if not text:
                continue
            block["pdf_page"] = pdf_page
            heading = heading_blocks.get(block["id"])
            if heading is not None:
                used_toc_indexes.add(heading["index"])
                emit_heading(heading["title"], heading["level"])
                heading_title = heading["title"].strip()
                if text.strip().startswith(heading_title):
                    after = text.strip()[len(heading_title) :].strip(" .:-؛،")
                    add_body_text(after, block)
                continue
            if is_section_index_line(text, page_entries):
                continue
            if text == "عن المؤلف":
                continue

            inline_heading = find_inline_heading(text, page_entries, used_toc_indexes)
            if inline_heading is not None:
                entry, pos, length = inline_heading
                before = text[:pos].strip()
                after = text[pos + length :].strip(" .:-؛،")
                if pos == 0:
                    emit_heading(entry["title"], entry["level"])
                    used_toc_indexes.add(entry["index"])
                    add_body_text(after, block)
                    continue
                if before:
                    add_body_text(before, block)
                emit_heading(entry["title"], entry["level"])
                used_toc_indexes.add(entry["index"])
                add_body_text(after, block)
                continue

            add_body_text(text, block)

    flush()
    return "\n".join(manuscript_lines).rstrip() + "\n", passages


def write_book_yaml(
    path: Path,
    raw: dict[str, Any],
    work_id: str,
    source_pdf: Path,
    title_id: str,
    author: str,
    language: str,
    heading_profile: str | None = None,
) -> None:
    title = raw["metadata"].get("title") or work_id
    lines = [
        "schema_version: 0.1",
        f"id: {work_id}",
        f"title_ar: {title}",
        f"title_id: {title_id}",
        f"author: {author}",
        f"language: {language}",
        "status: draft_extraction",
    ]
    if heading_profile:
        lines.append(f"heading_profile: {heading_profile}")
    lines.extend(
        [
            "source:",
            f"  pdf: {project_relative_path(source_pdf)}",
            f"  pages: {raw['page_count']}",
            "outputs:",
            "  raw_json: raw/raw.json",
            "  raw_markdown: raw/raw.md",
            "  manuscript: manuscript.md",
            "  passages: passages.jsonl",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--work-id", default="afdhalush-shalawat")
    parser.add_argument("--passage-prefix", default="ASH")
    parser.add_argument("--title-id", default="")
    parser.add_argument("--author", default="")
    parser.add_argument("--language", default="ar")
    parser.add_argument("--review-status", default="draft_extraction")
    parser.add_argument("--heading-profile")
    parser.add_argument(
        "--heading-profiles",
        default=Path("config/heading_profiles.yml"),
        type=Path,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pdf_path = args.pdf.resolve()
    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    raw = extract_raw(doc, pdf_path, args.work_id)
    profile = load_heading_profile(args.heading_profiles, args.heading_profile)
    apply_heading_profile(raw, args.heading_profile, profile)
    manuscript, passages = make_manuscript(
        raw,
        args.passage_prefix,
        args.language,
        args.review_status,
    )
    title_id = args.title_id or args.work_id.replace("-", " ").title()
    author = args.author or raw["metadata"].get("author") or ""

    write_json(out_dir / "raw" / "raw.json", raw)
    write_raw_markdown(out_dir / "raw" / "raw.md", raw)
    (out_dir / "manuscript.md").write_text(manuscript, encoding="utf-8")
    write_jsonl(out_dir / "passages.jsonl", passages)
    write_book_yaml(
        out_dir / "book.yml",
        raw,
        args.work_id,
        pdf_path,
        title_id,
        author,
        args.language,
        args.heading_profile,
    )

    print(f"Wrote {out_dir / 'raw' / 'raw.json'}")
    print(f"Wrote {out_dir / 'raw' / 'raw.md'}")
    print(f"Wrote {out_dir / 'manuscript.md'}")
    print(f"Wrote {out_dir / 'passages.jsonl'} ({len(passages)} passages)")
    print(f"Wrote {out_dir / 'book.yml'}")


if __name__ == "__main__":
    main()
