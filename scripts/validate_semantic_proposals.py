#!/usr/bin/env python3
"""Validate LLM semantic enrichment proposals against canonical source text."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from translate_passages import (
    overlay_manuscript_text,
    project_relative,
    read_jsonl,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

ALLOWED_PRIMARY_KINDS = {
    "body",
    "ayah",
    "hadith",
    "quote",
    "matn",
    "dua",
    "poem",
    "list",
    "biography",
    "source_catalog",
}
ALLOWED_SEGMENT_KINDS = ALLOWED_PRIMARY_KINDS | {"prose", "list_item"}
ALLOWED_LAYOUT_COMPONENTS = {
    "body",
    "ayah_block",
    "hadith_block",
    "quote_block",
    "matn_block",
    "poem_block",
    "table_block",
    "editor_note_block",
}
SCRIPTURE_KINDS = {"ayah", "hadith"}
TECHNICAL_LATIN_RE = re.compile(
    r"\b(?:API|RAG|Graph|PDF|Typst|QR|role|matn|pipeline)\b",
    re.IGNORECASE,
)


def truncate(text: str, limit: int = 160) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def resolve_book_path(book_dir: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return book_dir / path


def load_source_passages(book_dir: Path, manuscript: str) -> tuple[dict[str, dict[str, Any]], int]:
    rows = read_jsonl(book_dir / "passages.jsonl")
    rows, overlay_count = overlay_manuscript_text(rows, resolve_book_path(book_dir, manuscript))
    return {
        row["id"]: row
        for row in rows
        if isinstance(row, dict) and row.get("id")
    }, overlay_count


def load_proposals(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"Proposal file not found: {path}")
    return read_jsonl(path)


def add_finding(
    findings: list[dict[str, Any]],
    *,
    proposal_id: str | None,
    severity: str,
    code: str,
    message: str,
    segment_index: int | None = None,
    text_preview: str | None = None,
) -> None:
    finding: dict[str, Any] = {
        "proposal_id": proposal_id,
        "severity": severity,
        "code": code,
        "message": message,
    }
    if segment_index is not None:
        finding["segment_index"] = segment_index
    if text_preview:
        finding["text_preview"] = truncate(text_preview)
    findings.append(finding)


def collect_arabic_label_text(proposal: dict[str, Any]) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    for key in ("reason_ar",):
        value = proposal.get(key)
        if isinstance(value, str) and value.strip():
            values.append((key, value))

    for index, item in enumerate(proposal.get("enhancements") or []):
        if not isinstance(item, dict):
            continue
        for key in ("title_ar", "reason_ar"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                values.append((f"enhancements[{index}].{key}", value))

    for index, value in enumerate(proposal.get("review_notes") or []):
        if isinstance(value, str) and value.strip():
            values.append((f"review_notes[{index}]", value))

    return values


def validate_proposals(
    *,
    book_dir: Path,
    proposals_path: Path,
    manuscript: str = "clean/manuscript.md",
) -> dict[str, Any]:
    source_by_id, overlay_count = load_source_passages(book_dir, manuscript)
    proposals = load_proposals(proposals_path)
    findings: list[dict[str, Any]] = []
    duplicate_counts = Counter(
        str(row.get("id"))
        for row in proposals
        if isinstance(row, dict) and row.get("id")
    )

    for proposal_id, count in duplicate_counts.items():
        if count > 1:
            add_finding(
                findings,
                proposal_id=proposal_id,
                severity="fail",
                code="duplicate_proposal_id",
                message=f"Proposal ID appears {count} times.",
            )

    for proposal in proposals:
        if not isinstance(proposal, dict):
            add_finding(
                findings,
                proposal_id=None,
                severity="fail",
                code="invalid_proposal_row",
                message="Proposal row is not an object.",
            )
            continue

        proposal_id = proposal.get("id")
        if not isinstance(proposal_id, str) or not proposal_id.strip():
            add_finding(
                findings,
                proposal_id=None,
                severity="fail",
                code="missing_proposal_id",
                message="Proposal row has no id.",
            )
            continue

        source = source_by_id.get(proposal_id)
        source_text = str(source.get("text") or "") if source else ""
        if not source:
            add_finding(
                findings,
                proposal_id=proposal_id,
                severity="fail",
                code="unknown_passage_id",
                message="Proposal ID does not exist in passages.jsonl.",
            )

        primary_kind = proposal.get("primary_kind")
        if primary_kind not in ALLOWED_PRIMARY_KINDS:
            add_finding(
                findings,
                proposal_id=proposal_id,
                severity="fail",
                code="invalid_primary_kind",
                message=f"primary_kind must be one of {sorted(ALLOWED_PRIMARY_KINDS)}.",
            )

        layout_component = proposal.get("layout_component")
        if layout_component not in ALLOWED_LAYOUT_COMPONENTS:
            add_finding(
                findings,
                proposal_id=proposal_id,
                severity="fail",
                code="invalid_layout_component",
                message=f"layout_component must be one of {sorted(ALLOWED_LAYOUT_COMPONENTS)}.",
            )

        confidence = proposal.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
            add_finding(
                findings,
                proposal_id=proposal_id,
                severity="warn",
                code="invalid_confidence",
                message="confidence should be a number from 0 to 1.",
            )

        for field, value in collect_arabic_label_text(proposal):
            if TECHNICAL_LATIN_RE.search(value):
                add_finding(
                    findings,
                    proposal_id=proposal_id,
                    severity="warn",
                    code="latin_technical_term_in_arabic_label",
                    message=f"{field} contains Latin technical/product terms; keep Arabic editions Arabic-only.",
                    text_preview=value,
                )

        segments = proposal.get("segments")
        if segments is None:
            segments = []
        if not isinstance(segments, list):
            add_finding(
                findings,
                proposal_id=proposal_id,
                severity="fail",
                code="invalid_segments",
                message="segments must be a list.",
            )
            segments = []

        if primary_kind in SCRIPTURE_KINDS and not segments:
            add_finding(
                findings,
                proposal_id=proposal_id,
                severity="warn",
                code="scripture_without_segments",
                message="ayah/hadith proposals should include exact source segments.",
            )

        for index, segment in enumerate(segments):
            if not isinstance(segment, dict):
                add_finding(
                    findings,
                    proposal_id=proposal_id,
                    severity="fail",
                    code="invalid_segment",
                    message="segment row is not an object.",
                    segment_index=index,
                )
                continue

            segment_kind = segment.get("kind")
            segment_text = str(segment.get("text") or "")
            validation_error = segment.get("validation_error")
            if validation_error:
                add_finding(
                    findings,
                    proposal_id=proposal_id,
                    severity="fail",
                    code=str(validation_error),
                    message="Segment carries a validation_error from proposal normalization.",
                    segment_index=index,
                    text_preview=segment_text,
                )

            if segment_kind not in ALLOWED_SEGMENT_KINDS:
                add_finding(
                    findings,
                    proposal_id=proposal_id,
                    severity="fail",
                    code="invalid_segment_kind",
                    message=f"segment.kind must be one of {sorted(ALLOWED_SEGMENT_KINDS)}.",
                    segment_index=index,
                )

            if segment_text and source_text and segment_text not in source_text:
                add_finding(
                    findings,
                    proposal_id=proposal_id,
                    severity="fail",
                    code="segment_text_not_exact_source_substring",
                    message="Segment text is not an exact substring of the canonical clean manuscript.",
                    segment_index=index,
                    text_preview=segment_text,
                )

            source_span = segment.get("source_span")
            if isinstance(source_span, dict):
                start = source_span.get("start")
                end = source_span.get("end")
                if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end < start:
                    add_finding(
                        findings,
                        proposal_id=proposal_id,
                        severity="fail",
                        code="invalid_source_span_range",
                        message="source_span start/end is not a valid range.",
                        segment_index=index,
                    )
                elif source_text[start:end] != segment_text:
                    add_finding(
                        findings,
                        proposal_id=proposal_id,
                        severity="fail",
                        code="source_span_text_mismatch",
                        message="segment.text does not match canonical text at source_span start/end.",
                        segment_index=index,
                        text_preview=segment_text,
                    )

            if segment_kind in SCRIPTURE_KINDS:
                if not segment_text:
                    add_finding(
                        findings,
                        proposal_id=proposal_id,
                        severity="warn",
                        code="scripture_segment_empty",
                        message="ayah/hadith segment has no text.",
                        segment_index=index,
                    )
                if not segment.get("ref"):
                    add_finding(
                        findings,
                        proposal_id=proposal_id,
                        severity="warn",
                        code="scripture_segment_missing_ref",
                        message="ayah/hadith segment has no visible reference.",
                        segment_index=index,
                        text_preview=segment_text,
                    )
                if segment.get("review_required") is not True:
                    add_finding(
                        findings,
                        proposal_id=proposal_id,
                        severity="warn",
                        code="scripture_segment_not_marked_for_review",
                        message="ayah/hadith segment should remain review_required until verified.",
                        segment_index=index,
                        text_preview=segment_text,
                    )

    severity_counts = Counter(item["severity"] for item in findings)
    findings_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for finding in findings:
        proposal_id = finding.get("proposal_id") or "_global"
        findings_by_id[str(proposal_id)].append(finding)

    status = "pass"
    if severity_counts.get("fail"):
        status = "fail"
    elif severity_counts.get("warn"):
        status = "warn"

    strict_safe_ids = []
    non_failing_ids = []
    for proposal in proposals:
        proposal_id = proposal.get("id")
        if not proposal_id:
            continue
        current = findings_by_id.get(str(proposal_id), [])
        if not current:
            strict_safe_ids.append(str(proposal_id))
            non_failing_ids.append(str(proposal_id))
        elif not any(item["severity"] == "fail" for item in current):
            non_failing_ids.append(str(proposal_id))

    return {
        "schema_version": "0.1",
        "book_dir": project_relative(book_dir),
        "manuscript": manuscript,
        "proposals": project_relative(proposals_path),
        "status": status,
        "source_passage_count": len(source_by_id),
        "proposal_count": len(proposals),
        "source_overlay_count": overlay_count,
        "finding_counts": dict(sorted(severity_counts.items())),
        "findings": findings,
        "findings_by_id": dict(sorted(findings_by_id.items())),
        "strict_safe_ids": strict_safe_ids,
        "non_failing_ids": non_failing_ids,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Semantic Proposal Validation",
        "",
        f"- Status: `{report['status']}`",
        f"- Proposals: `{report['proposal_count']}`",
        f"- Findings: `{report.get('finding_counts') or {}}`",
        f"- Strict safe IDs: `{len(report.get('strict_safe_ids') or [])}`",
        f"- Non-failing IDs: `{len(report.get('non_failing_ids') or [])}`",
        "",
    ]
    findings_by_id = report.get("findings_by_id") or {}
    if not findings_by_id:
        lines.append("_No findings._")
        return "\n".join(lines).rstrip() + "\n"

    for proposal_id, findings in findings_by_id.items():
        lines.append(f"## {proposal_id}")
        lines.append("")
        for finding in findings:
            location = ""
            if finding.get("segment_index") is not None:
                location = f" segment `{finding['segment_index']}`"
            preview = f" - {finding['text_preview']}" if finding.get("text_preview") else ""
            lines.append(
                f"- `{finding['severity']}` `{finding['code']}`{location}: "
                f"{finding['message']}{preview}"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-dir", required=True, type=Path)
    parser.add_argument(
        "--manuscript",
        default="clean/manuscript.md",
        help="Clean manuscript path relative to --book-dir.",
    )
    parser.add_argument(
        "--proposals",
        default="annotations/semantic-llm-proposals.jsonl",
        help="Proposal JSONL path relative to --book-dir.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Validation JSON path relative to project root.",
    )
    parser.add_argument(
        "--markdown",
        default=None,
        help="Validation Markdown path relative to project root.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when validation has fail findings.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    book_dir = args.book_dir.resolve()
    proposals_path = resolve_book_path(book_dir, args.proposals)
    report = validate_proposals(
        book_dir=book_dir,
        proposals_path=proposals_path,
        manuscript=args.manuscript,
    )

    report_stem = book_dir.name
    out_path = (
        PROJECT_ROOT
        / (args.out or f"reports/semantic-enrichment/{report_stem}-validation.json")
    ).resolve()
    markdown_path = (
        PROJECT_ROOT
        / (args.markdown or f"reports/semantic-enrichment/{report_stem}-validation.md")
    ).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")

    print(f"{report['status']}: {report['proposal_count']} proposals, {report.get('finding_counts') or {}}")
    print(f"wrote {out_path}")
    print(f"wrote {markdown_path}")

    if args.strict and report["status"] == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
