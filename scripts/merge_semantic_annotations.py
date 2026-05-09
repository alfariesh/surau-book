#!/usr/bin/env python3
"""Merge validated LLM semantic proposals into a reviewed annotation layer."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from translate_passages import project_relative, read_jsonl, write_jsonl
from validate_semantic_proposals import resolve_book_path, validate_proposals


PROJECT_ROOT = Path(__file__).resolve().parents[1]

KIND_TO_ROLE = {
    "ayah": "ayat",
    "body": "body",
    "hadith": "quote",
    "quote": "quote",
    "matn": "matn",
    "dua": "matn",
    "poem": "poem",
    "list": "body",
    "biography": "body",
    "source_catalog": "body",
}
ROLE_TO_LAYOUT = {
    "ayat": "ayah_text_block",
    "body": "body",
    "matn": "matn_block",
    "poem": "poem_block",
    "quote": "quote_block",
}


def load_validation_report(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def finding_summary(findings: list[dict[str, Any]]) -> str:
    if not findings:
        return "no findings"
    counts = Counter(item.get("code", "unknown") for item in findings)
    return ", ".join(f"{code}={count}" for code, count in sorted(counts.items()))


def proposal_to_annotation(
    proposal: dict[str, Any],
    draft: dict[str, Any],
    *,
    decision: str,
) -> dict[str, Any]:
    kind = str(proposal.get("primary_kind") or draft.get("kind") or "body")
    role = KIND_TO_ROLE.get(kind, "body")
    layout = ROLE_TO_LAYOUT.get(role, "body")
    annotation = dict(draft)
    annotation.update(
        {
            "kind": kind,
            "role": role,
            "layout": layout,
            "status": "reviewed" if decision == "approved" else "machine_validated",
            "confidence": proposal.get("confidence", draft.get("confidence")),
            "signals": sorted(
                set(
                    list(draft.get("signals") or [])
                    + [
                        "llm_semantic_proposal",
                        f"llm_component:{proposal.get('layout_component') or 'body'}",
                    ]
                )
            ),
            "llm_proposal": {
                "model": proposal.get("model"),
                "layout_component": proposal.get("layout_component"),
                "reason_ar": proposal.get("reason_ar"),
                "segments": proposal.get("segments") or [],
                "entities": proposal.get("entities") or [],
                "enhancements": proposal.get("enhancements") or [],
                "typst_hints": proposal.get("typst_hints") or {},
                "review_notes": proposal.get("review_notes") or [],
            },
            "review_decision": decision,
            "generated_by": "scripts/merge_semantic_annotations.py",
        }
    )
    return annotation


def merge_annotations(
    *,
    book_dir: Path,
    draft_path: Path,
    proposals_path: Path,
    manuscript: str,
    validation_report: dict[str, Any] | None,
    allow_warnings: bool,
    approve_ids: set[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if validation_report is None:
        validation_report = validate_proposals(
            book_dir=book_dir,
            proposals_path=proposals_path,
            manuscript=manuscript,
        )

    findings_by_id = validation_report.get("findings_by_id") or {}
    draft_rows = read_jsonl(draft_path)
    proposal_rows = read_jsonl(proposals_path)
    draft_by_id = {
        row["id"]: row
        for row in draft_rows
        if isinstance(row, dict) and row.get("id")
    }
    proposal_by_id = {
        row["id"]: row
        for row in proposal_rows
        if isinstance(row, dict) and row.get("id")
    }

    accepted: dict[str, dict[str, Any]] = {}
    skipped: list[dict[str, Any]] = []

    for proposal_id, proposal in proposal_by_id.items():
        draft = draft_by_id.get(proposal_id)
        findings = findings_by_id.get(proposal_id) or []
        has_fail = any(item.get("severity") == "fail" for item in findings)
        has_warn = any(item.get("severity") == "warn" for item in findings)

        if draft is None:
            skipped.append(
                {
                    "id": proposal_id,
                    "reason": "missing_draft_annotation",
                    "findings": finding_summary(findings),
                }
            )
            continue
        if has_fail:
            skipped.append(
                {
                    "id": proposal_id,
                    "reason": "validation_failed",
                    "findings": finding_summary(findings),
                }
            )
            continue
        if has_warn and not allow_warnings and proposal_id not in approve_ids:
            skipped.append(
                {
                    "id": proposal_id,
                    "reason": "needs_human_review_or_allow_warnings",
                    "findings": finding_summary(findings),
                }
            )
            continue

        decision = "approved" if proposal_id in approve_ids else "auto_validated"
        accepted[proposal_id] = proposal_to_annotation(proposal, draft, decision=decision)

    merged_rows = [accepted.get(row.get("id"), row) for row in draft_rows]
    summary = {
        "schema_version": "0.1",
        "book_dir": project_relative(book_dir),
        "draft": project_relative(draft_path),
        "proposals": project_relative(proposals_path),
        "validation_status": validation_report.get("status"),
        "draft_count": len(draft_rows),
        "proposal_count": len(proposal_rows),
        "accepted_count": len(accepted),
        "accepted_ids": sorted(accepted),
        "skipped_count": len(skipped),
        "skipped": skipped,
        "allow_warnings": allow_warnings,
        "approved_ids": sorted(approve_ids),
        "kind_counts": dict(sorted(Counter(row.get("kind", "unknown") for row in merged_rows).items())),
        "role_counts": dict(sorted(Counter(row.get("role", "unknown") for row in merged_rows).items())),
    }
    return merged_rows, summary


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Semantic Annotation Merge",
        "",
        f"- Validation status: `{summary.get('validation_status')}`",
        f"- Draft rows: `{summary.get('draft_count')}`",
        f"- Proposals: `{summary.get('proposal_count')}`",
        f"- Accepted: `{summary.get('accepted_count')}`",
        f"- Skipped: `{summary.get('skipped_count')}`",
        "",
    ]
    accepted = summary.get("accepted_ids") or []
    if accepted:
        lines.append("Accepted IDs:")
        lines.extend(f"- `{pid}`" for pid in accepted)
        lines.append("")

    skipped = summary.get("skipped") or []
    if skipped:
        lines.append("Skipped IDs:")
        for item in skipped:
            lines.append(
                f"- `{item.get('id')}` `{item.get('reason')}`: {item.get('findings')}"
            )
        lines.append("")

    lines.extend(
        [
            "## Counts",
            "",
            f"- Kinds: `{summary.get('kind_counts')}`",
            f"- Roles: `{summary.get('role_counts')}`",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def parse_id_args(values: list[str] | None) -> set[str]:
    ids: list[str] = []
    for value in values or []:
        ids.extend(item.strip() for item in value.split(",") if item.strip())
    return set(ids)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-dir", required=True, type=Path)
    parser.add_argument(
        "--manuscript",
        default="clean/manuscript.md",
        help="Clean manuscript path relative to --book-dir.",
    )
    parser.add_argument(
        "--draft",
        default="annotations/semantic-draft.jsonl",
        help="Draft annotation JSONL path relative to --book-dir.",
    )
    parser.add_argument(
        "--proposals",
        default="annotations/semantic-llm-proposals.jsonl",
        help="Proposal JSONL path relative to --book-dir.",
    )
    parser.add_argument(
        "--validation",
        default=None,
        help="Validation JSON path relative to project root. If missing, validation runs in-process.",
    )
    parser.add_argument(
        "--out",
        default="annotations/semantic-reviewed.jsonl",
        help="Reviewed annotation JSONL path relative to --book-dir.",
    )
    parser.add_argument(
        "--summary",
        default="annotations/semantic-reviewed.summary.json",
        help="Reviewed annotation summary JSON path relative to --book-dir.",
    )
    parser.add_argument(
        "--report",
        default=None,
        help="Merge Markdown report path relative to project root.",
    )
    parser.add_argument(
        "--allow-warnings",
        action="store_true",
        help="Allow non-failing proposals with warnings to merge.",
    )
    parser.add_argument(
        "--approve-id",
        action="append",
        help="Human-approved proposal ID or comma-separated IDs. Fail findings still block merge.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    book_dir = args.book_dir.resolve()
    draft_path = resolve_book_path(book_dir, args.draft)
    proposals_path = resolve_book_path(book_dir, args.proposals)
    report_stem = book_dir.name
    validation_arg = args.validation or f"reports/semantic-enrichment/{report_stem}-validation.json"
    validation_path = (PROJECT_ROOT / validation_arg).resolve()
    validation_report = load_validation_report(validation_path)
    approve_ids = parse_id_args(args.approve_id)

    merged_rows, summary = merge_annotations(
        book_dir=book_dir,
        draft_path=draft_path,
        proposals_path=proposals_path,
        manuscript=args.manuscript,
        validation_report=validation_report,
        allow_warnings=args.allow_warnings,
        approve_ids=approve_ids,
    )

    out_path = resolve_book_path(book_dir, args.out)
    summary_path = resolve_book_path(book_dir, args.summary)
    report_arg = args.report or f"reports/semantic-enrichment/{report_stem}-merge.md"
    report_path = (PROJECT_ROOT / report_arg).resolve()
    write_jsonl(out_path, merged_rows)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_markdown(summary), encoding="utf-8")

    print(f"accepted {summary['accepted_count']} / {summary['proposal_count']} proposals")
    print(f"wrote {out_path}")
    print(f"wrote {summary_path}")
    print(f"wrote {report_path}")


if __name__ == "__main__":
    main()
