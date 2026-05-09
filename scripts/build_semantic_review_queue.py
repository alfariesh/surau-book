#!/usr/bin/env python3
"""Build a human review queue from semantic proposal validation findings."""

from __future__ import annotations

import argparse
import html
import json
from collections import Counter
from pathlib import Path
from typing import Any

from translate_passages import project_relative, read_jsonl, write_jsonl
from validate_semantic_proposals import resolve_book_path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

ISSUE_ACTIONS = {
    "scripture_segment_missing_ref": {
        "issue_type": "missing_reference",
        "priority": "high",
        "action": "Cari rujukan ayat/hadits yang tepat. Isi verified_ref sebelum status reviewed.",
    },
    "scripture_segment_not_marked_for_review": {
        "issue_type": "review_flag",
        "priority": "medium",
        "action": "Pastikan segmen ayat/hadits tetap butuh review sampai rujukan diverifikasi.",
    },
    "segment_text_not_exact_source_substring": {
        "issue_type": "source_mismatch",
        "priority": "blocker",
        "action": "Jangan merge. Regenerate proposal dengan span_id exact dari source.",
    },
    "source_span_text_mismatch": {
        "issue_type": "source_mismatch",
        "priority": "blocker",
        "action": "Jangan merge. Periksa source_span start/end terhadap manuscript canonical.",
    },
    "latin_technical_term_in_arabic_label": {
        "issue_type": "arabic_label_cleanup",
        "priority": "low",
        "action": "Ganti label Arab agar tidak memuat istilah teknis Latin.",
    },
}


def truncate(text: str, limit: int = 220) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"File not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def proposal_by_id(path: Path) -> dict[str, dict[str, Any]]:
    return {
        row["id"]: row
        for row in read_jsonl(path)
        if isinstance(row, dict) and row.get("id")
    }


def passage_by_id(book_dir: Path) -> dict[str, dict[str, Any]]:
    return {
        row["id"]: row
        for row in read_jsonl(book_dir / "passages.jsonl")
        if isinstance(row, dict) and row.get("id")
    }


def issue_metadata(code: str) -> dict[str, str]:
    return ISSUE_ACTIONS.get(
        code,
        {
            "issue_type": code,
            "priority": "medium",
            "action": "Review manual berdasarkan finding validator.",
        },
    )


def make_queue(
    *,
    book_dir: Path,
    proposals_path: Path,
    validation_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    proposals = proposal_by_id(proposals_path)
    passages = passage_by_id(book_dir)
    validation = load_json(validation_path)
    rows: list[dict[str, Any]] = []

    for index, finding in enumerate(validation.get("findings") or [], start=1):
        if not isinstance(finding, dict):
            continue
        proposal_id = finding.get("proposal_id")
        if not proposal_id:
            continue
        proposal = proposals.get(str(proposal_id), {})
        passage = passages.get(str(proposal_id), {})
        segment_index = finding.get("segment_index")
        segments = proposal.get("segments") if isinstance(proposal.get("segments"), list) else []
        segment = (
            segments[segment_index]
            if isinstance(segment_index, int) and 0 <= segment_index < len(segments)
            else {}
        )
        code = str(finding.get("code") or "unknown")
        meta = issue_metadata(code)
        segment_text = str(segment.get("text") or finding.get("text_preview") or "")
        source_span = segment.get("source_span") if isinstance(segment.get("source_span"), dict) else {}
        queue_id = (
            f"{proposal_id}:s{segment_index}:{code}"
            if isinstance(segment_index, int)
            else f"{proposal_id}:row:{code}:{index}"
        )

        rows.append(
            {
                "schema_version": "0.1",
                "queue_id": queue_id,
                "work_id": proposal.get("work_id") or passage.get("work_id") or book_dir.name,
                "passage_id": proposal_id,
                "sequence": proposal.get("sequence") or passage.get("sequence"),
                "section_path": proposal.get("section_path") or passage.get("section_path") or [],
                "source_citation": proposal.get("source_citation") or passage.get("citation"),
                "model": proposal.get("model"),
                "proposal_status": proposal.get("proposal_status"),
                "proposal_kind": proposal.get("primary_kind"),
                "layout_component": proposal.get("layout_component"),
                "severity": finding.get("severity"),
                "code": code,
                "issue_type": meta["issue_type"],
                "priority": meta["priority"],
                "recommended_action": meta["action"],
                "status": "needs_review",
                "segment_index": segment_index,
                "segment_kind": segment.get("kind"),
                "segment_ref": segment.get("ref") or "",
                "review_required": segment.get("review_required"),
                "source_span": source_span,
                "text": segment_text,
                "text_preview": truncate(segment_text),
                "finding_message": finding.get("message"),
                "review": {
                    "decision": "pending",
                    "verified_ref": "",
                    "takhrij_grade": "",
                    "reviewer": "",
                    "notes": "",
                },
            }
        )

    rows.sort(
        key=lambda row: (
            int(row.get("sequence") or 0),
            int(row.get("segment_index") if isinstance(row.get("segment_index"), int) else 9999),
            row.get("code") or "",
        )
    )
    summary = {
        "schema_version": "0.1",
        "book_dir": project_relative(book_dir),
        "proposals": project_relative(proposals_path),
        "validation": project_relative(validation_path),
        "count": len(rows),
        "status_counts": dict(Counter(row["status"] for row in rows)),
        "severity_counts": dict(Counter(row["severity"] for row in rows)),
        "issue_type_counts": dict(Counter(row["issue_type"] for row in rows)),
        "priority_counts": dict(Counter(row["priority"] for row in rows)),
        "segment_kind_counts": dict(Counter(row.get("segment_kind") or "row" for row in rows)),
        "passage_count": len({row["passage_id"] for row in rows}),
    }
    return rows, summary


def render_markdown(rows: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    lines = [
        "# Semantic Review Queue",
        "",
        f"- Items: `{summary['count']}`",
        f"- Passages: `{summary['passage_count']}`",
        f"- Issue types: `{summary['issue_type_counts']}`",
        f"- Priorities: `{summary['priority_counts']}`",
        f"- Segment kinds: `{summary['segment_kind_counts']}`",
        "",
        "## Review Fields",
        "",
        "Isi hasil review di `review.verified_ref`, `review.takhrij_grade`, `review.decision`, dan `review.notes` pada JSONL/decision file.",
        "",
    ]
    for row in rows:
        section = " > ".join(row.get("section_path") or [])
        citation = (row.get("source_citation") or {}).get("label") or ""
        lines.extend(
            [
                f"## {row['queue_id']}",
                "",
                f"- Passage: `{row['passage_id']}`",
                f"- Section: `{section}`",
                f"- Kind: `{row.get('segment_kind')}`",
                f"- Issue: `{row['issue_type']}` / `{row['code']}`",
                f"- Priority: `{row['priority']}`",
                f"- Current ref: `{row.get('segment_ref') or ''}`",
                f"- Citation: {citation}",
                f"- Action: {row['recommended_action']}",
                "",
                f"> {row.get('text_preview') or ''}",
                "",
                "Review:",
                "- decision: `pending | reviewed | rejected | needs_source_check`",
                "- verified_ref:",
                "- takhrij_grade:",
                "- notes:",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_html(rows: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    cards = []
    for row in rows:
        section = " &gt; ".join(html.escape(item) for item in row.get("section_path") or [])
        citation = html.escape((row.get("source_citation") or {}).get("label") or "")
        text = html.escape(row.get("text") or row.get("text_preview") or "")
        ref = html.escape(row.get("segment_ref") or "")
        cards.append(
            f"""
<article class="item" data-kind="{html.escape(str(row.get('segment_kind') or ''))}" data-priority="{html.escape(row['priority'])}" data-issue="{html.escape(row['issue_type'])}">
  <header>
    <span class="qid">{html.escape(row['queue_id'])}</span>
    <span class="badge">{html.escape(row['priority'])}</span>
    <span class="badge muted">{html.escape(row['issue_type'])}</span>
  </header>
  <dl>
    <dt>Passage</dt><dd>{html.escape(row['passage_id'])}</dd>
    <dt>Section</dt><dd>{section}</dd>
    <dt>Kind</dt><dd>{html.escape(str(row.get('segment_kind') or ''))}</dd>
    <dt>Current ref</dt><dd>{ref}</dd>
    <dt>Citation</dt><dd>{citation}</dd>
    <dt>Action</dt><dd>{html.escape(row['recommended_action'])}</dd>
  </dl>
  <blockquote dir="rtl" lang="ar">{text}</blockquote>
  <section class="review">
    <label>Decision <input placeholder="pending / reviewed / rejected"></label>
    <label>Verified ref <input></label>
    <label>Takhrij grade <input></label>
    <label>Notes <textarea></textarea></label>
  </section>
</article>
"""
        )
    return f"""<!doctype html>
<html lang="id">
<head>
  <meta charset="utf-8">
  <title>Semantic Review Queue</title>
  <style>
    :root {{ color-scheme: light; font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    body {{ margin: 0; background: #f8f7f2; color: #1f1b16; }}
    main {{ max-width: 1080px; margin: 0 auto; padding: 32px 20px 56px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; }}
    .summary {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; margin: 18px 0; }}
    .summary div {{ background: white; border: 1px solid #ded6c3; padding: 10px; }}
    .summary strong {{ display: block; font-size: 22px; }}
    .toolbar {{ position: sticky; top: 0; background: #f8f7f2; padding: 10px 0; z-index: 2; }}
    .toolbar input, .toolbar select {{ padding: 8px; border: 1px solid #cfc4aa; background: white; }}
    .item {{ background: white; border: 1px solid #ded6c3; margin: 12px 0; padding: 14px; }}
    .item header {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}
    .qid {{ font-weight: 700; }}
    .badge {{ border: 1px solid #997d44; color: #6e5520; padding: 2px 8px; font-size: 12px; }}
    .muted {{ border-color: #b9ae98; color: #625846; }}
    dl {{ display: grid; grid-template-columns: 120px 1fr; gap: 6px 12px; font-size: 13px; }}
    dt {{ color: #6b6254; }}
    dd {{ margin: 0; }}
    blockquote {{ font-family: "Amiri", "Scheherazade New", serif; font-size: 22px; line-height: 1.9; border-right: 3px solid #997d44; margin: 16px 0; padding: 8px 16px; background: #fffdf7; }}
    .review {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }}
    label {{ display: grid; gap: 4px; font-size: 12px; color: #625846; }}
    input, textarea {{ font: inherit; padding: 8px; border: 1px solid #cfc4aa; }}
    textarea {{ min-height: 62px; }}
  </style>
</head>
<body>
<main>
  <h1>Semantic Review Queue</h1>
  <p>Review ayat/hadits/quote yang masih punya warning validator. Field input di halaman ini bersifat bantu baca; sumber final tetap JSONL.</p>
  <section class="summary">
    <div><span>Items</span><strong>{summary['count']}</strong></div>
    <div><span>Passages</span><strong>{summary['passage_count']}</strong></div>
    <div><span>Warnings</span><strong>{summary.get('severity_counts', {}).get('warn', 0)}</strong></div>
    <div><span>High</span><strong>{summary.get('priority_counts', {}).get('high', 0)}</strong></div>
    <div><span>Hadith</span><strong>{summary.get('segment_kind_counts', {}).get('hadith', 0)}</strong></div>
  </section>
  <section class="toolbar">
    <input id="q" placeholder="Cari passage, teks, ref..." oninput="filterItems()">
    <select id="kind" onchange="filterItems()">
      <option value="">All kinds</option>
      <option value="ayah">ayah</option>
      <option value="hadith">hadith</option>
      <option value="quote">quote</option>
    </select>
  </section>
  {''.join(cards)}
</main>
<script>
function filterItems() {{
  const q = document.getElementById('q').value.toLowerCase();
  const kind = document.getElementById('kind').value;
  document.querySelectorAll('.item').forEach((item) => {{
    const text = item.innerText.toLowerCase();
    const okQ = !q || text.includes(q);
    const okKind = !kind || item.dataset.kind === kind;
    item.style.display = okQ && okKind ? '' : 'none';
  }});
}}
</script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-dir", required=True, type=Path)
    parser.add_argument(
        "--proposals",
        default="annotations/semantic-llm-proposals.jsonl",
        help="Proposal JSONL path relative to --book-dir.",
    )
    parser.add_argument(
        "--validation",
        help="Validation JSON path relative to project root. Defaults to reports/semantic-enrichment/{book}-validation.json.",
    )
    parser.add_argument(
        "--out",
        default="annotations/semantic-review-queue.jsonl",
        help="Queue JSONL path relative to --book-dir.",
    )
    parser.add_argument(
        "--summary",
        default="annotations/semantic-review-queue.summary.json",
        help="Queue summary JSON path relative to --book-dir.",
    )
    parser.add_argument(
        "--report",
        help="Markdown report path relative to project root. Defaults to reports/semantic-enrichment/{book}-review-queue.md.",
    )
    parser.add_argument(
        "--html",
        help="HTML report path relative to project root. Defaults to reports/semantic-enrichment/{book}-review-queue.html.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    book_dir = args.book_dir.resolve()
    validation_arg = args.validation or f"reports/semantic-enrichment/{book_dir.name}-validation.json"
    report_arg = args.report or f"reports/semantic-enrichment/{book_dir.name}-review-queue.md"
    html_arg = args.html or f"reports/semantic-enrichment/{book_dir.name}-review-queue.html"

    proposals_path = resolve_book_path(book_dir, args.proposals)
    validation_path = (PROJECT_ROOT / validation_arg).resolve()
    out_path = resolve_book_path(book_dir, args.out)
    summary_path = resolve_book_path(book_dir, args.summary)
    report_path = (PROJECT_ROOT / report_arg).resolve()
    html_path = (PROJECT_ROOT / html_arg).resolve()

    rows, summary = make_queue(
        book_dir=book_dir,
        proposals_path=proposals_path,
        validation_path=validation_path,
    )
    write_jsonl(out_path, rows)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_markdown(rows, summary), encoding="utf-8")
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(render_html(rows, summary), encoding="utf-8")

    print(f"review items: {len(rows)}")
    print(f"wrote {out_path}")
    print(f"wrote {summary_path}")
    print(f"wrote {report_path}")
    print(f"wrote {html_path}")


if __name__ == "__main__":
    main()
