#!/usr/bin/env python3
"""Ask an LLM for reviewable semantic/layout enrichment proposals.

This creates a proposal layer only. It does not change canonical text,
passages.jsonl, manuscript.md, or the public citation source.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import OrderedDict
from pathlib import Path
from typing import Any

from translate_passages import (
    DEFAULT_API_BASE,
    DEFAULT_MODEL,
    call_llm,
    load_yaml,
    overlay_manuscript_text,
    project_relative,
    read_jsonl,
    write_jsonl,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

OUTPUT_SCHEMA = {
    "primary_kind": "body | ayah | hadith | quote | matn | dua | poem | list | biography | source_catalog",
    "layout_component": "body | ayah_block | hadith_block | quote_block | matn_block | poem_block | table_block | editor_note_block",
    "confidence": "number from 0 to 1",
    "reason_ar": "short Arabic reason for the classification",
    "segments": [
        {
            "kind": "ayah | hadith | quote | matn | dua | poem | prose | list_item",
            "text": "exact source substring or empty if not safe",
            "ref": "Qur'an/hadith/book/person reference if visible, else empty",
            "confidence": "number from 0 to 1",
            "review_required": "boolean",
        }
    ],
    "entities": [
        {
            "type": "person | book | place | concept",
            "name": "Arabic name exactly as written",
            "role": "author/source/topic/etc",
        }
    ],
    "enhancements": [
        {
            "type": "diagram | table | glossary | editor_note | illustration | crossref",
            "title_ar": "short Arabic title",
            "reason_ar": "why this helps the reader",
            "data_required": "what structured data must be reviewed first",
            "priority": "low | medium | high",
        }
    ],
    "typst_hints": {
        "avoid_page_break_before": "boolean",
        "needs_caption": "boolean",
        "suggested_component": "Typst component name",
    },
    "review_notes": ["short Arabic notes for human reviewer"],
}

QUOTE_SOURCE_PHRASES = (
    "قال القسطلاني",
    "قال السخاوي",
    "قال الشيخ",
    "قال ابن حجر",
    "قال النووي",
    "نقل الشيخ",
    "نقل العلامة",
    "نقل القسطلاني",
    "ونقل",
)


def parse_id_args(values: list[str] | None) -> list[str]:
    ids: list[str] = []
    for value in values or []:
        ids.extend(item.strip() for item in value.split(",") if item.strip())
    return list(OrderedDict.fromkeys(ids))


def truncate(text: str, limit: int = 260) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def load_annotations(path: Path) -> dict[str, dict[str, Any]]:
    return {
        row["id"]: row
        for row in read_jsonl(path)
        if isinstance(row, dict) and row.get("id")
    }


def select_candidate_rows(
    rows: list[dict[str, Any]],
    annotations: dict[str, dict[str, Any]],
    ids: list[str],
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    by_id = {row.get("id"): row for row in rows if row.get("id")}
    if ids:
        missing = [pid for pid in ids if pid not in by_id]
        if missing:
            raise SystemExit(f"Unknown passage IDs: {', '.join(missing)}")
        return [by_id[pid] for pid in ids]

    candidates: OrderedDict[str, dict[str, Any]] = OrderedDict()

    def add(row: dict[str, Any], reason: str) -> None:
        pid = row.get("id")
        if not pid or pid in candidates:
            return
        next_row = dict(row)
        next_row["_semantic_enrichment_reason"] = reason
        candidates[pid] = next_row

    for row in rows:
        pid = row.get("id")
        annotation = annotations.get(pid or "", {})
        text = row.get("text") or ""
        section = " > ".join(row.get("section_path") or [])

        if annotation.get("role") in {"matn", "quote", "poem", "ayat"}:
            add(row, f"heuristic role={annotation.get('role')}")
        elif "قال تعالى" in text or "قوله تعالى" in text or "} " in text or "} " in text:
            add(row, "contains Qur'an-like signal")
        elif any(token in text for token in ("قال رسول", "رواه", "روى", "أخرج")):
            add(row, "contains hadith/transmission signal")
        elif any(token in text for token in QUOTE_SOURCE_PHRASES):
            add(row, "contains quote/source attribution signal")
        elif "القصيدة" in section or "قصيدة" in text:
            add(row, "poetry/qasidah context")
        elif len(text) > 2500:
            add(row, "long passage may need split/table/editorial treatment")

        if len(candidates) >= limit + offset:
            break

    if len(candidates) < limit + offset:
        step = max(len(rows) // max(limit + offset, 1), 1)
        for index in range(0, len(rows), step):
            add(rows[index], "sequence spread sample")
            if len(candidates) >= limit + offset:
                break

    return list(candidates.values())[offset : offset + limit]


def build_messages(
    book: dict[str, Any],
    row: dict[str, Any],
    annotation: dict[str, Any] | None,
) -> list[dict[str, str]]:
    system = (
        "You are a senior editor for classical Arabic Islamic books and a Typst layout "
        "designer. Your job is not to rewrite the source. Propose semantic tags and "
        "layout enhancements for a modern educational edition. Preserve the Arabic text. "
        "Do not invent Qur'an references, hadith grading, citations, diagrams, or facts. "
        "If a reference is uncertain, mark review_required=true. Return strict JSON only."
    )
    user = {
        "task": "Classify this passage and propose reviewable layout/enrichment ideas.",
        "book": {
            "work_id": book.get("id"),
            "title_ar": book.get("title_ar"),
            "author": book.get("author_ar") or book.get("author"),
        },
        "constraints": [
            "Do not alter canonical Arabic text.",
            "Prefer Arabic-only labels for Arabic editions.",
            "Only propose diagram/table/illustration when it genuinely improves understanding.",
            "Use editor_note only for content clearly separate from the original text.",
            "Qur'an and hadith candidates require human review unless exact reference is obvious in the text.",
            "Make suggestions usable by Typst components and API/RAG metadata.",
        ],
        "output_schema": OUTPUT_SCHEMA,
        "metadata": {
            "id": row.get("id"),
            "sequence": row.get("sequence"),
            "section_path": row.get("section_path") or [],
            "existing_annotation": annotation or {},
            "selection_reason": row.get("_semantic_enrichment_reason"),
            "citation": row.get("citation") or {},
        },
        "arabic_text": row.get("text") or "",
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ]


def normalize_proposal(
    proposal: dict[str, Any],
    row: dict[str, Any],
    annotation: dict[str, Any] | None,
    model: str,
) -> dict[str, Any]:
    source_text = row.get("text") or ""
    validation_warnings = []
    segments = proposal.get("segments") if isinstance(proposal.get("segments"), list) else []
    normalized_segments = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        next_segment = dict(segment)
        segment_text = str(next_segment.get("text") or "")
        if segment_text and segment_text not in source_text:
            next_segment["review_required"] = True
            next_segment["validation_error"] = "segment_text_not_exact_source_substring"
            validation_warnings.append(
                {
                    "kind": "segment_text_not_exact_source_substring",
                    "segment_kind": next_segment.get("kind"),
                    "text_preview": truncate(segment_text, 120),
                }
            )
        normalized_segments.append(next_segment)

    return {
        "id": row.get("id"),
        "work_id": row.get("work_id"),
        "sequence": row.get("sequence"),
        "section_path": row.get("section_path") or [],
        "source_citation": row.get("citation"),
        "source_annotation": annotation or {},
        "proposal_status": "llm_draft",
        "model": model,
        "primary_kind": proposal.get("primary_kind") or "body",
        "layout_component": proposal.get("layout_component") or "body",
        "confidence": proposal.get("confidence"),
        "reason_ar": proposal.get("reason_ar") or "",
        "segments": normalized_segments,
        "entities": proposal.get("entities") if isinstance(proposal.get("entities"), list) else [],
        "enhancements": (
            proposal.get("enhancements") if isinstance(proposal.get("enhancements"), list) else []
        ),
        "typst_hints": proposal.get("typst_hints") if isinstance(proposal.get("typst_hints"), dict) else {},
        "review_notes": (
            proposal.get("review_notes") if isinstance(proposal.get("review_notes"), list) else []
        ),
        "validation_warnings": validation_warnings,
        "text_preview": truncate(row.get("text") or ""),
        "generated_by": "scripts/enrich_semantics_llm.py",
    }


def render_report(rows: list[dict[str, Any]], out_jsonl: Path, dry_run: bool) -> str:
    lines = [
        "# Semantic Enrichment Review",
        "",
        f"- Output: `{project_relative(out_jsonl)}`",
        f"- Mode: `{'dry_run' if dry_run else 'llm_draft'}`",
        f"- Rows: `{len(rows)}`",
        "",
    ]
    if not rows:
        lines.append("_No rows._")
        return "\n".join(lines).rstrip() + "\n"

    for row in rows:
        lines.extend(
            [
                f"## {row.get('id')}",
                "",
                f"- Section: `{' > '.join(row.get('section_path') or [])}`",
                f"- Kind: `{row.get('primary_kind', row.get('source_annotation', {}).get('kind', 'pending'))}`",
                f"- Component: `{row.get('layout_component', row.get('source_annotation', {}).get('layout', 'pending'))}`",
                f"- Confidence: `{row.get('confidence', row.get('source_annotation', {}).get('confidence', 'pending'))}`",
                f"- Reason: {row.get('reason_ar') or row.get('_semantic_enrichment_reason') or ''}",
                "",
                f"> {truncate(row.get('text_preview') or row.get('text') or '', 420)}",
                "",
            ]
        )
        enhancements = row.get("enhancements") or []
        if enhancements:
            lines.append("Enhancements:")
            for item in enhancements[:6]:
                lines.append(
                    f"- `{item.get('type', 'unknown')}` {item.get('title_ar', '')}: "
                    f"{item.get('reason_ar', '')}"
                )
            lines.append("")
        validation_warnings = row.get("validation_warnings") or []
        if validation_warnings:
            lines.append("Validation warnings:")
            for item in validation_warnings[:6]:
                lines.append(f"- `{item.get('kind')}` {item.get('text_preview', '')}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-dir", required=True, type=Path)
    parser.add_argument(
        "--manuscript",
        default="clean/manuscript.md",
        help="Clean manuscript path relative to --book-dir for source text overlay.",
    )
    parser.add_argument(
        "--annotations",
        default="annotations/semantic-draft.jsonl",
        help="Heuristic annotation JSONL path relative to --book-dir.",
    )
    parser.add_argument(
        "--out",
        default="annotations/semantic-llm-proposals.jsonl",
        help="Output proposal JSONL path relative to --book-dir.",
    )
    parser.add_argument(
        "--report",
        default="reports/semantic-enrichment/afdhalush-shalawat-llm-proposals.md",
        help="Review markdown path relative to project root.",
    )
    parser.add_argument("--id", action="append", help="Passage ID or comma-separated IDs.")
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--api-key-env", default="KILO_API_KEY")
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--ca-bundle")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    book_dir = args.book_dir.resolve()
    book = load_yaml(book_dir / "book.yml")
    annotations_path = book_dir / args.annotations
    out_path = book_dir / args.out
    report_path = (PROJECT_ROOT / args.report).resolve()

    rows = read_jsonl(book_dir / "passages.jsonl")
    rows, _ = overlay_manuscript_text(rows, book_dir / args.manuscript)
    annotations = load_annotations(annotations_path)
    selected = select_candidate_rows(
        rows,
        annotations,
        parse_id_args(args.id),
        args.limit,
        args.offset,
    )

    if args.dry_run:
        dry_rows = []
        for row in selected:
            annotation = annotations.get(row.get("id", ""))
            dry_rows.append(
                {
                    "id": row.get("id"),
                    "work_id": row.get("work_id"),
                    "sequence": row.get("sequence"),
                    "section_path": row.get("section_path") or [],
                    "source_annotation": annotation or {},
                    "_semantic_enrichment_reason": row.get("_semantic_enrichment_reason"),
                    "text_preview": truncate(row.get("text") or ""),
                }
            )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(render_report(dry_rows, out_path, dry_run=True), encoding="utf-8")
        print(f"dry-run: selected {len(dry_rows)} rows")
        print(f"wrote {report_path}")
        return

    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        raise SystemExit(f"Missing API key env: {args.api_key_env}")

    proposals = []
    for index, row in enumerate(selected, start=1):
        pid = row.get("id")
        annotation = annotations.get(pid or "")
        messages = build_messages(book, row, annotation)
        response = call_llm(
            api_base=args.api_base,
            api_key=api_key,
            model=args.model,
            messages=messages,
            temperature=args.temperature,
            timeout=args.timeout,
            retries=args.retries,
            ca_bundle=args.ca_bundle,
        )
        proposals.append(normalize_proposal(response, row, annotation, args.model))
        print(f"{index}/{len(selected)} {pid}: {proposals[-1]['primary_kind']}")

    write_jsonl(out_path, proposals)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_report(proposals, out_path, dry_run=False), encoding="utf-8")
    print(f"ok: wrote {out_path}")
    print(f"ok: wrote {report_path}")


if __name__ == "__main__":
    main()
