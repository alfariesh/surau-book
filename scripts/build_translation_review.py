#!/usr/bin/env python3
"""Build a side-by-side review packet for multilingual passage translations."""

from __future__ import annotations

import argparse
import json
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PASSAGE_RE = re.compile(r'^::passage\{id="([^"]+)"\}\s*$')
HEADING_RE = re.compile(r"^#{1,6}\s+")
ARABIC_LETTER_RE = re.compile(r"[\u0621-\u064a]")
SALAWAT_RE = re.compile(r"(?:اللَّهُمَّ|اللهم)\s+صَل|صلى\s+الل")
HADITH_RE = re.compile(r"قال\s+رسول|روى|رواه|الحديث|الأحاديث")


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


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_id_args(values: list[str] | None) -> list[str]:
    ids: list[str] = []
    for value in values or []:
        ids.extend(item.strip() for item in value.split(",") if item.strip())
    return list(OrderedDict.fromkeys(ids))


def parse_manuscript_passages(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    passages: dict[str, str] = {}
    current_id: str | None = None
    current_lines: list[str] = []
    in_frontmatter = False
    frontmatter_seen = False

    def flush() -> None:
        nonlocal current_id, current_lines
        if current_id is not None:
            text = "\n".join(current_lines).strip()
            if text:
                passages[current_id] = text
        current_id = None
        current_lines = []

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "---" and not frontmatter_seen:
            in_frontmatter = True
            frontmatter_seen = True
            continue
        if stripped == "---" and in_frontmatter:
            in_frontmatter = False
            continue
        if in_frontmatter:
            continue

        passage_match = PASSAGE_RE.match(line)
        if passage_match:
            flush()
            current_id = passage_match.group(1)
            continue
        if current_id is not None and HEADING_RE.match(line):
            flush()
            continue
        if current_id is not None:
            current_lines.append(line)

    flush()
    return passages


def overlay_clean_text(rows: list[dict[str, Any]], manuscript_path: Path) -> list[dict[str, Any]]:
    passages = parse_manuscript_passages(manuscript_path)
    if not passages:
        return rows

    overlaid = []
    source = project_relative(manuscript_path)
    for row in rows:
        next_row = dict(row)
        pid = row.get("id")
        if pid in passages:
            next_row["text"] = passages[pid]
            next_row["_review_source_text"] = source
        overlaid.append(next_row)
    return overlaid


def load_translations(book_dir: Path, langs: list[str]) -> dict[str, dict[str, dict[str, Any]]]:
    translations: dict[str, dict[str, dict[str, Any]]] = {}
    for lang in langs:
        path = book_dir / "translations" / lang / "passages.jsonl"
        translations[lang] = {
            row.get("source_passage_id"): row
            for row in read_jsonl(path)
            if row.get("source_passage_id")
        }
    return translations


def section_text(row: dict[str, Any]) -> str:
    return " > ".join(row.get("section_path") or [])


def first_page(row: dict[str, Any]) -> int | None:
    source_blocks = row.get("source_blocks")
    if not isinstance(source_blocks, list):
        return None
    for block in source_blocks:
        if isinstance(block, dict) and isinstance(block.get("pdf_page"), int):
            return block["pdf_page"]
    return None


def add_candidate(
    candidates: OrderedDict[str, tuple[dict[str, Any], str]],
    category: str,
    row: dict[str, Any],
    reason: str,
) -> None:
    if category not in candidates:
        candidates[category] = (row, reason)


def auto_candidates(
    rows: list[dict[str, Any]],
    translations: dict[str, dict[str, dict[str, Any]]],
) -> OrderedDict[str, tuple[dict[str, Any], str]]:
    candidates: OrderedDict[str, tuple[dict[str, Any], str]] = OrderedDict()
    translated_ids = {
        source_id
        for by_source in translations.values()
        for source_id in by_source.keys()
        if source_id
    }

    for row in rows:
        pid = row.get("id")
        text = row.get("text") or ""
        section = section_text(row)
        length = len(text)

        if pid in translated_ids:
            add_candidate(candidates, "already_translated", row, "has an existing translation row")
        if "عن المؤلف" in section and length >= 80:
            add_candidate(candidates, "author_context", row, "author/context prose")
        if "بسم" in text and "الل" in text:
            add_candidate(candidates, "basmalah", row, "standard devotional opening")
        if "مقدمة" in section and length >= 450:
            add_candidate(candidates, "muqaddimah_long", row, "long opening prose")
        if length <= 180 and re.search(r"الفصل|القسم|الصلاة", text):
            add_candidate(candidates, "heading_like", row, "heading-like short passage")
        if length < 12:
            add_candidate(candidates, "short_edge", row, "very short passage edge case")
        if text.startswith(("ومنها", "ومن ذلك")) and 40 <= length <= 500:
            add_candidate(candidates, "benefit_list", row, "enumerated benefit list")
        if HADITH_RE.search(text) and 300 <= length <= 1800:
            add_candidate(candidates, "hadith_discussion", row, "report/transmission prose")
        if SALAWAT_RE.search(text) and 80 <= length <= 700:
            add_candidate(candidates, "salawat_short", row, "short salawat formula")
        if SALAWAT_RE.search(text) and length > 1800:
            add_candidate(candidates, "salawat_long", row, "long salawat/du'a formula")
        if "القصيدة" in section and 80 <= length <= 800:
            add_candidate(candidates, "poetry", row, "poetry/qasidah section")

    for index, row in enumerate(sorted(rows, key=lambda item: len(item.get("text") or ""), reverse=True)[:3], start=1):
        add_candidate(candidates, f"longest_{index}", row, "one of the longest source passages")

    return candidates


def select_rows(
    rows: list[dict[str, Any]],
    translations: dict[str, dict[str, dict[str, Any]]],
    ids: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    by_id = {row.get("id"): row for row in rows if row.get("id")}
    selected: OrderedDict[str, dict[str, Any]] = OrderedDict()

    if ids:
        missing = [pid for pid in ids if pid not in by_id]
        if missing:
            raise SystemExit(f"Unknown passage IDs: {', '.join(missing)}")
        for pid in ids:
            row = dict(by_id[pid])
            row["_review_categories"] = ["manual"]
            row["_review_reasons"] = ["selected with --id"]
            selected[pid] = row
        return list(selected.values())

    for category, (source_row, reason) in auto_candidates(rows, translations).items():
        pid = source_row.get("id")
        if not pid:
            continue
        row = selected.setdefault(pid, dict(source_row))
        row.setdefault("_review_categories", []).append(category)
        row.setdefault("_review_reasons", []).append(reason)
        if len(selected) >= limit:
            break

    if len(selected) < limit and rows:
        remaining = limit - len(selected)
        step = max(len(rows) // (remaining + 1), 1)
        for index in range(step, len(rows), step):
            row = rows[index]
            pid = row.get("id")
            if not pid or pid in selected:
                continue
            next_row = dict(row)
            next_row["_review_categories"] = ["sequence_spread"]
            next_row["_review_reasons"] = ["fills the batch across the book sequence"]
            selected[pid] = next_row
            if len(selected) >= limit:
                break

    return list(selected.values())


def compact(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def fenced(text: str) -> str:
    text = text or ""
    return text.replace("```", "` ` `")


def translation_summary(
    source_row: dict[str, Any],
    translation: dict[str, Any] | None,
) -> dict[str, Any]:
    source_text = source_row.get("text") or ""
    if not translation:
        return {"status": "missing", "target_len": 0, "ratio": None, "arabic_leak": 0}
    target_text = translation.get("text") or ""
    ratio = len(target_text) / max(len(source_text), 1)
    return {
        "status": translation.get("translation_status") or "missing_status",
        "model": translation.get("model"),
        "target_len": len(target_text),
        "ratio": round(ratio, 2),
        "arabic_leak": len(ARABIC_LETTER_RE.findall(target_text)),
        "warnings": translation.get("warnings") or [],
        "notes": translation.get("notes") or [],
    }


def build_packet(
    book_dir: Path,
    langs: list[str],
    selected: list[dict[str, Any]],
    translations: dict[str, dict[str, dict[str, Any]]],
    source_path: Path,
) -> dict[str, Any]:
    book = load_yaml(book_dir / "book.yml")
    book_id = book.get("id") or book_dir.name
    items = []
    for row in selected:
        pid = row["id"]
        item_translations = {
            lang: translation_summary(row, translations.get(lang, {}).get(pid))
            for lang in langs
        }
        items.append(
            {
                "id": pid,
                "sequence": row.get("sequence"),
                "section_path": row.get("section_path") or [],
                "source_page": first_page(row),
                "citation": (row.get("citation") or {}).get("label"),
                "source_length": len(row.get("text") or ""),
                "source_text": row.get("_review_source_text") or project_relative(source_path),
                "categories": row.get("_review_categories") or [],
                "reasons": row.get("_review_reasons") or [],
                "translations": item_translations,
            }
        )

    missing_by_lang = {
        lang: [
            item["id"]
            for item in items
            if item["translations"].get(lang, {}).get("status") == "missing"
        ]
        for lang in langs
    }
    return {
        "schema_version": 0.1,
        "book_id": book_id,
        "book_dir": project_relative(book_dir),
        "source": project_relative(source_path),
        "langs": langs,
        "count": len(items),
        "ids": [item["id"] for item in items],
        "missing_by_lang": missing_by_lang,
        "items": items,
    }


def render_markdown(
    packet: dict[str, Any],
    selected: list[dict[str, Any]],
    translations: dict[str, dict[str, dict[str, Any]]],
    source_chars: int,
    translation_chars: int,
) -> str:
    langs = packet["langs"]
    lines = [
        f"# Translation Review: {packet['book_id']}",
        "",
        "This packet is for human/editorial review before bulk translation.",
        "",
        f"- Book dir: `{packet['book_dir']}`",
        f"- Source: `{packet['source']}`",
        f"- Languages: `{', '.join(langs)}`",
        f"- Passages: `{packet['count']}`",
        "",
        "## Translate Missing",
        "",
    ]

    any_missing = False
    for lang in langs:
        missing = packet["missing_by_lang"].get(lang) or []
        if not missing:
            continue
        any_missing = True
        lines.extend(
            [
                f"`{lang}` missing `{len(missing)}` rows:",
                "",
                "```bash",
                "python3 scripts/translate_passages.py \\",
                f"  --book-dir {packet['book_dir']} \\",
                f"  --lang {lang} \\",
                f"  --id {','.join(missing)} \\",
                "  --annotations annotations/semantic-reviewed.jsonl \\",
                "  --model deepseek-v4-pro \\",
                "  --row-deadline 300 \\",
                "  --continue-on-error",
                "```",
                "",
            ]
        )
    if not any_missing:
        lines.extend(["_No missing translations in this batch._", ""])

    lines.extend(
        [
            "## Batch Index",
            "",
            "| ID | Categories | Section | Citation | Source Chars | " + " | ".join(langs) + " |",
            "| --- | --- | --- | --- | --- | " + " | ".join("---" for _ in langs) + " |",
        ]
    )
    for item in packet["items"]:
        lang_cells = []
        for lang in langs:
            summary = item["translations"].get(lang) or {}
            cell = summary.get("status", "missing")
            if summary.get("arabic_leak"):
                cell += f" / Arabic leak {summary['arabic_leak']}"
            if summary.get("ratio") is not None:
                cell += f" / ratio {summary['ratio']}"
            lang_cells.append(cell)
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{item['id']}`",
                    ", ".join(item["categories"]),
                    compact(" > ".join(item["section_path"]), 90),
                    compact(item.get("citation") or "", 80),
                    str(item["source_length"]),
                    *lang_cells,
                ]
            )
            + " |"
        )
    lines.append("")

    lines.extend(["## Side By Side", ""])
    selected_by_id = {row["id"]: row for row in selected}
    for item in packet["items"]:
        row = selected_by_id[item["id"]]
        lines.extend(
            [
                f"### {item['id']}",
                "",
                f"- Categories: `{', '.join(item['categories'])}`",
                f"- Section: `{compact(' > '.join(item['section_path']), 180)}`",
                f"- Citation: `{item.get('citation') or 'missing'}`",
                f"- Source page: `{item.get('source_page')}`",
                "",
                "**Arabic Source**",
                "",
                "```text",
                fenced(compact(row.get("text") or "", source_chars)),
                "```",
                "",
            ]
        )

        for lang in langs:
            translation = translations.get(lang, {}).get(item["id"])
            summary = item["translations"].get(lang) or {}
            lines.extend([f"**{lang} Translation**", ""])
            if translation:
                lines.extend(
                    [
                        f"- Status: `{summary.get('status')}`",
                        f"- Model: `{summary.get('model')}`",
                        f"- Target chars/source ratio: `{summary.get('target_len')}` / `{summary.get('ratio')}`",
                        f"- Arabic leak chars: `{summary.get('arabic_leak')}`",
                        "",
                        "```text",
                        fenced(compact(translation.get("text") or "", translation_chars)),
                        "```",
                        "",
                    ]
                )
                if summary.get("notes") or summary.get("warnings"):
                    lines.append(f"- Notes: `{json.dumps(summary.get('notes'), ensure_ascii=False)}`")
                    lines.append(f"- Warnings: `{json.dumps(summary.get('warnings'), ensure_ascii=False)}`")
                    lines.append("")
            else:
                lines.extend(["_Missing._", ""])

    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-dir", required=True, type=Path)
    parser.add_argument("--lang", action="append", dest="langs", help="Language code; repeatable.")
    parser.add_argument("--source", default="passages.jsonl")
    parser.add_argument("--manuscript", default="clean/manuscript.md")
    parser.add_argument("--id", action="append", dest="ids", help="Passage ID; repeatable or comma-separated.")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--source-chars", type=int, default=1400)
    parser.add_argument("--translation-chars", type=int, default=1400)
    parser.add_argument("--out-dir", type=Path, default=Path("reports/translation-reviews"))
    parser.add_argument("--name", help="Output filename stem.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    book_dir = args.book_dir.resolve()
    langs = args.langs or ["id", "en"]
    source_path = book_dir / args.source
    rows = read_jsonl(source_path)
    if args.manuscript:
        rows = overlay_clean_text(rows, book_dir / args.manuscript)
    translations = load_translations(book_dir, langs)
    selected = select_rows(rows, translations, parse_id_args(args.ids), args.limit)
    packet = build_packet(book_dir, langs, selected, translations, source_path)

    stem = args.name or f"{packet['book_id']}-translation-review-batch"
    json_path = args.out_dir / f"{stem}.json"
    md_path = args.out_dir / f"{stem}.md"
    write_json(json_path, packet)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(
        render_markdown(packet, selected, translations, args.source_chars, args.translation_chars),
        encoding="utf-8",
    )

    print(f"ok: wrote {json_path}")
    print(f"ok: wrote {md_path}")


if __name__ == "__main__":
    main()
