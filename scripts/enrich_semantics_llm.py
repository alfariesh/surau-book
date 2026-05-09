#!/usr/bin/env python3
"""Ask an LLM for reviewable semantic/layout enrichment proposals.

This creates a proposal layer only. It does not change canonical text,
passages.jsonl, manuscript.md, or the public citation source.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
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


class RowDeadlineExceeded(TimeoutError):
    pass

OUTPUT_SCHEMA = {
    "primary_kind": "body | ayah | hadith | quote | matn | dua | poem | list | biography | source_catalog",
    "layout_component": "body | ayah_block | hadith_block | quote_block | matn_block | poem_block | table_block | editor_note_block",
    "confidence": "number from 0 to 1",
    "reason_ar": "short Arabic reason for the classification",
    "segments": [
        {
            "kind": "ayah | hadith | quote | matn | dua | poem | prose | list_item",
            "span_id": "source span id from source_spans, such as S1; leave empty if no safe source span",
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

HADITH_SPAN_RE = re.compile(
    r"(?:قال رسول اللّٰه|قال رسول الله|وقال صلى اللّٰه عليه وسلم|وقال صلى الله عليه وسلم|وكان صلى اللّٰه عليه وسلم يقول|وكان صلى الله عليه وسلم يقول)"
    r"[^.؟؛\n]{12,900}(?:[.؟؛]|$)"
)
DUA_SPAN_RE = re.compile(r"(?:اللهم|اللَّهُمَّ)[^.؟؛*\n]{10,900}(?:[.؟؛*]|$)")
QURAN_BRACE_RE = re.compile(r"}\s*([^{}]{8,700}?)\s*{")


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


def stripped_span(text: str, start: int, end: int) -> tuple[int, int, str]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end, text[start:end]


def sentence_window(text: str, start: int, end: int, max_chars: int = 900) -> tuple[int, int, str]:
    left = start
    while left > 0 and text[left - 1] not in ".؟؛\n*":
        left -= 1
    right = end
    while right < len(text) and text[right] not in ".؟؛\n*":
        right += 1
    if right < len(text) and text[right] in ".؟؛":
        right += 1
    if right - left > max_chars:
        right = min(len(text), left + max_chars)
    return stripped_span(text, left, right)


def add_source_span(
    spans: list[dict[str, Any]],
    seen_ranges: set[tuple[int, int]],
    *,
    text: str,
    start: int,
    end: int,
    kind_guess: str,
    reason: str,
) -> None:
    start, end, span_text = stripped_span(text, start, end)
    if not span_text or (start, end) in seen_ranges:
        return
    seen_ranges.add((start, end))
    spans.append(
        {
            "span_id": f"S{len(spans) + 1}",
            "kind_guess": kind_guess,
            "start": start,
            "end": end,
            "reason": reason,
            "text": span_text,
        }
    )


def extract_source_spans(row: dict[str, Any], max_spans: int = 18) -> list[dict[str, Any]]:
    """Extract exact source substrings that the LLM may classify.

    The LLM can only point at these spans by ID. We fill final segment text
    from this list so normalization/rewrite cannot slip into the proposal.
    """

    text = str(row.get("text") or "")
    section = " > ".join(row.get("section_path") or [])
    spans: list[dict[str, Any]] = []
    seen_ranges: set[tuple[int, int]] = set()
    quran_ranges: list[tuple[int, int]] = []

    if len(text.strip()) <= 260:
        add_source_span(
            spans,
            seen_ranges,
            text=text,
            start=0,
            end=len(text),
            kind_guess="matn" if text.strip().startswith(("بسم", "اللهم", "اللَّهُمَّ")) else "body",
            reason="short_whole_passage",
        )

    for match in QURAN_BRACE_RE.finditer(text):
        quran_ranges.append((match.start(1), match.end(1)))
        add_source_span(
            spans,
            seen_ranges,
            text=text,
            start=match.start(1),
            end=match.end(1),
            kind_guess="ayah",
            reason="brace_quran_candidate",
        )

    for opener in ("قال تعالى", "قوله تعالى", "فقال تعالى", "قال اللّٰه", "قال الله"):
        start = text.find(opener)
        if start >= 0:
            if any(abs(start - q_start) < 80 for q_start, _ in quran_ranges):
                continue
            span_end = start + len(opener)
            while span_end < len(text) and text[span_end] not in ".؟؛\n*":
                span_end += 1
            if span_end < len(text) and text[span_end] in ".؟؛":
                span_end += 1
            span_end = min(span_end, start + 700)
            add_source_span(
                spans,
                seen_ranges,
                text=text,
                start=start,
                end=span_end,
                kind_guess="ayah",
                reason=f"quran_signal:{opener}",
            )

    for match in HADITH_SPAN_RE.finditer(text):
        add_source_span(
            spans,
            seen_ranges,
            text=text,
            start=match.start(),
            end=match.end(),
            kind_guess="hadith",
            reason="hadith_opener",
        )
        if len(spans) >= max_spans:
            break

    for match in DUA_SPAN_RE.finditer(text):
        add_source_span(
            spans,
            seen_ranges,
            text=text,
            start=match.start(),
            end=match.end(),
            kind_guess="dua",
            reason="dua_opener",
        )
        if len(spans) >= max_spans:
            break

    for phrase in QUOTE_SOURCE_PHRASES:
        start = text.find(phrase)
        if start >= 0:
            span_start, span_end, _ = sentence_window(text, start, start + len(phrase))
            add_source_span(
                spans,
                seen_ranges,
                text=text,
                start=span_start,
                end=span_end,
                kind_guess="quote",
                reason=f"quote_source:{phrase}",
            )

    if "قصيدة" in section and "\n" in text:
        add_source_span(
            spans,
            seen_ranges,
            text=text,
            start=0,
            end=min(len(text), 1200),
            kind_guess="poem",
            reason="poetry_section",
        )

    return spans[:max_spans]


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
    source_spans: list[dict[str, Any]],
) -> list[dict[str, str]]:
    system = (
        "You are a senior editor for classical Arabic Islamic books and a Typst layout "
        "designer. Your job is not to rewrite the source. Propose semantic tags and "
        "layout enhancements for a modern educational edition. For segment annotations, "
        "select only from source_spans by span_id. Do not copy, normalize, correct, or "
        "return source text in segments. Do not invent Qur'an references, hadith grading, "
        "citations, diagrams, or facts. If a reference is uncertain, mark review_required=true. "
        "Return strict JSON only."
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
            "For segments, use span_id only from source_spans. Do not write segment text.",
            "If no listed source span is safe, return segments=[] and explain in review_notes.",
            "Prefer Arabic-only labels for Arabic editions.",
            "Only propose diagram/table/illustration when it genuinely improves understanding.",
            "Use editor_note only for content clearly separate from the original text.",
            "Qur'an and hadith candidates require human review unless a verified reference is visible in the text.",
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
        "source_spans": [
            {
                "span_id": item["span_id"],
                "kind_guess": item["kind_guess"],
                "reason": item["reason"],
                "text": item["text"],
            }
            for item in source_spans
        ],
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
    source_spans: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    source_text = row.get("text") or ""
    spans_by_id = {
        span["span_id"]: span
        for span in source_spans or []
        if isinstance(span, dict) and span.get("span_id")
    }
    validation_warnings = []
    segments = proposal.get("segments") if isinstance(proposal.get("segments"), list) else []
    normalized_segments = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        next_segment = dict(segment)
        span_id = str(next_segment.get("span_id") or "")
        if span_id:
            source_span = spans_by_id.get(span_id)
            if source_span:
                llm_text = str(next_segment.get("text") or "")
                next_segment["text"] = source_span["text"]
                next_segment["source_span"] = {
                    "span_id": source_span["span_id"],
                    "kind_guess": source_span["kind_guess"],
                    "start": source_span["start"],
                    "end": source_span["end"],
                    "reason": source_span["reason"],
                }
                if llm_text and llm_text != source_span["text"]:
                    validation_warnings.append(
                        {
                            "kind": "segment_text_ignored_for_span_id",
                            "segment_kind": next_segment.get("kind"),
                            "span_id": span_id,
                            "text_preview": truncate(llm_text, 120),
                        }
                    )
            else:
                next_segment["text"] = ""
                next_segment["review_required"] = True
                next_segment["validation_error"] = "invalid_source_span_id"
                validation_warnings.append(
                    {
                        "kind": "invalid_source_span_id",
                        "segment_kind": next_segment.get("kind"),
                        "span_id": span_id,
                    }
                )

        segment_text = str(next_segment.get("text") or "")
        if next_segment.get("kind") in {"ayah", "hadith"}:
            next_segment["review_required"] = True
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
        "source_span_count": len(source_spans or []),
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


def call_llm_with_deadline(deadline: float, *args: Any, **kwargs: Any) -> dict[str, Any]:
    if deadline <= 0:
        return call_llm(*args, **kwargs)

    def handle_timeout(signum: int, frame: Any) -> None:
        raise RowDeadlineExceeded(f"row deadline exceeded after {deadline:g}s")

    previous_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, handle_timeout)
    signal.setitimer(signal.ITIMER_REAL, deadline)
    try:
        return call_llm(*args, **kwargs)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


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
        source_spans = row.get("source_spans") or []
        if source_spans:
            lines.append("Source spans:")
            for item in source_spans[:8]:
                lines.append(
                    f"- `{item.get('span_id')}` `{item.get('kind_guess')}` "
                    f"{item.get('reason')}: {truncate(item.get('text') or '', 140)}"
                )
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
        default=None,
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
    parser.add_argument(
        "--row-deadline",
        type=float,
        default=0,
        help="Wall-clock seconds before skipping one LLM row. 0 disables the outer deadline.",
    )
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--ca-bundle")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Skip IDs already present in --out.")
    parser.add_argument(
        "--save-every",
        type=int,
        default=0,
        help="Write JSONL/report after every N successful proposals. 0 writes only at the end.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    book_dir = args.book_dir.resolve()
    book = load_yaml(book_dir / "book.yml")
    annotations_path = book_dir / args.annotations
    out_path = book_dir / args.out
    report_path = (
        PROJECT_ROOT
        / (args.report or f"reports/semantic-enrichment/{book_dir.name}-llm-proposals.md")
    ).resolve()

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
            source_spans = extract_source_spans(row)
            dry_rows.append(
                {
                    "id": row.get("id"),
                    "work_id": row.get("work_id"),
                    "sequence": row.get("sequence"),
                    "section_path": row.get("section_path") or [],
                    "source_annotation": annotation or {},
                    "_semantic_enrichment_reason": row.get("_semantic_enrichment_reason"),
                    "source_spans": source_spans,
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

    proposals = read_jsonl(out_path) if args.resume and out_path.exists() else []
    existing_ids = {
        row.get("id")
        for row in proposals
        if isinstance(row, dict) and row.get("id")
    }
    if existing_ids:
        selected = [row for row in selected if row.get("id") not in existing_ids]
        print(
            f"resume: loaded {len(existing_ids)} existing proposals, {len(selected)} remaining",
            flush=True,
        )

    def save_progress() -> None:
        write_jsonl(out_path, proposals)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(render_report(proposals, out_path, dry_run=False), encoding="utf-8")

    for index, row in enumerate(selected, start=1):
        pid = row.get("id")
        annotation = annotations.get(pid or "")
        source_spans = extract_source_spans(row)
        messages = build_messages(book, row, annotation, source_spans)
        try:
            response = call_llm_with_deadline(
                args.row_deadline,
                api_base=args.api_base,
                api_key=api_key,
                model=args.model,
                messages=messages,
                temperature=args.temperature,
                timeout=args.timeout,
                retries=args.retries,
                ca_bundle=args.ca_bundle,
            )
            proposals.append(normalize_proposal(response, row, annotation, args.model, source_spans))
            print(f"{index}/{len(selected)} {pid}: {proposals[-1]['primary_kind']}", flush=True)
            if args.save_every > 0 and len(proposals) % args.save_every == 0:
                save_progress()
        except Exception as exc:
            if not args.continue_on_error:
                raise
            print(f"{index}/{len(selected)} {pid}: error: {exc}", flush=True)

    save_progress()
    print(f"ok: wrote {out_path}", flush=True)
    print(f"ok: wrote {report_path}", flush=True)


if __name__ == "__main__":
    main()
