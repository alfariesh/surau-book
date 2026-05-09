#!/usr/bin/env python3
"""Create Firestore-ready editorial review task drafts from local QA reports."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVER_TIMESTAMP = "__SERVER_TIMESTAMP__"
PRIORITY_RANK = {
    "blocker": 10,
    "high": 20,
    "medium": 40,
    "low": 70,
}


def project_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists() or yaml is None:
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
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


def compact(text: str, limit: int = 480) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def stable_id(work_id: str, task_type: str, source_key: str) -> str:
    digest = hashlib.sha1(f"{work_id}:{task_type}:{source_key}".encode("utf-8")).hexdigest()[:16]
    return f"{work_id}__{task_type}__{digest}"


def citation_label(row: dict[str, Any] | None) -> str:
    if not row:
        return ""
    citation = row.get("citation") or row.get("source_citation") or {}
    return citation.get("label") if isinstance(citation, dict) else ""


def load_passages(book_dir: Path) -> dict[str, dict[str, Any]]:
    return {
        row["id"]: row
        for row in read_jsonl(book_dir / "passages.jsonl")
        if isinstance(row, dict) and row.get("id")
    }


def task_doc(
    *,
    work_id: str,
    task_type: str,
    source_key: str,
    priority: str,
    title: str,
    reason: str,
    recommended_action: str,
    passage_id: str | None = None,
    section_path: list[str] | None = None,
    source_citation_label: str = "",
    text_preview: str = "",
    source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    priority = priority if priority in PRIORITY_RANK else "medium"
    doc_id = stable_id(work_id, task_type, source_key)
    data = {
        "schema_version": "0.1",
        "task_id": doc_id,
        "work_id": work_id,
        "passage_id": passage_id,
        "task_type": task_type,
        "priority": priority,
        "priority_rank": PRIORITY_RANK[priority],
        "status": "open",
        "assigned_to": None,
        "title": title,
        "reason": compact(reason, 1200),
        "recommended_action": compact(recommended_action, 1200),
        "section_path": section_path or [],
        "source_citation_label": source_citation_label or "",
        "text_preview": compact(text_preview, 2500),
        "source": source or {},
        "created_by": "system",
        "created_at": SERVER_TIMESTAMP,
        "updated_at": SERVER_TIMESTAMP,
    }
    return {
        "collection": "reviewTasks",
        "doc_id": doc_id,
        "data": data,
    }


def tasks_from_semantic_queue(
    *,
    work_id: str,
    path: Path,
) -> list[dict[str, Any]]:
    rows = read_jsonl(path)
    tasks = []
    for row in rows:
        passage_id = row.get("passage_id")
        segment_kind = row.get("segment_kind") or row.get("proposal_kind") or "segment"
        priority = row.get("priority") or "high"
        if priority == "blocker":
            priority = "blocker"
        tasks.append(
            task_doc(
                work_id=work_id,
                task_type="semantic_reference_review",
                source_key=str(row.get("queue_id") or f"{passage_id}:{row.get('segment_index')}"),
                priority=priority,
                title=f"Verify {segment_kind} reference for {passage_id}",
                reason=row.get("finding_message") or "Semantic validator found a segment that needs editor review.",
                recommended_action=row.get("recommended_action") or "Review semantic segment and fill verified reference if needed.",
                passage_id=passage_id,
                section_path=row.get("section_path") or [],
                source_citation_label=citation_label(row),
                text_preview=row.get("text_preview") or row.get("text") or "",
                source={
                    "kind": "semantic_review_queue",
                    "path": project_relative(path),
                    "id": row.get("queue_id"),
                    "code": row.get("code"),
                    "segment_index": row.get("segment_index"),
                    "segment_kind": segment_kind,
                },
            )
        )
    return tasks


def tasks_from_cleaning_report(
    *,
    work_id: str,
    qa: dict[str, Any],
    qa_path: Path,
    passages: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    tasks = []
    for sample in qa.get("cleaning_report", {}).get("suspicious_samples") or []:
        passage_id = sample.get("passage_id")
        passage = passages.get(passage_id or "")
        tasks.append(
            task_doc(
                work_id=work_id,
                task_type="cleaning_suspicious",
                source_key=f"cleaning:{sample.get('line')}:{passage_id}:{sample.get('pattern')}",
                priority="medium",
                title=f"Review cleaning artifact in {passage_id}",
                reason=f"Cleaning report flagged `{sample.get('pattern')}` around line {sample.get('line')}.",
                recommended_action="Check canonical clean manuscript around this passage and decide whether the marker is real text or extraction artifact.",
                passage_id=passage_id,
                section_path=(passage or {}).get("section_path") or [],
                source_citation_label=citation_label(passage),
                text_preview=sample.get("text") or "",
                source={
                    "kind": "qa_cleaning_suspicious_sample",
                    "path": project_relative(qa_path),
                    "line": sample.get("line"),
                    "pattern": sample.get("pattern"),
                },
            )
        )
    return tasks


def tasks_from_toc(
    *,
    work_id: str,
    qa: dict[str, Any],
    qa_path: Path,
) -> list[dict[str, Any]]:
    tasks = []
    for item in qa.get("toc", {}).get("unmatched") or []:
        title = item.get("title") or "Untitled TOC entry"
        tasks.append(
            task_doc(
                work_id=work_id,
                task_type="toc_unmatched_heading",
                source_key=f"toc:{item.get('index')}:{item.get('page')}:{title}",
                priority="medium",
                title=f"Resolve TOC heading: {compact(title, 80)}",
                reason="TOC entry was not found in manuscript headings.",
                recommended_action="Check whether the heading is missing, normalized differently, or should be ignored for this edition.",
                passage_id=None,
                section_path=[],
                source_citation_label="",
                text_preview=title,
                source={
                    "kind": "qa_toc_unmatched",
                    "path": project_relative(qa_path),
                    "toc_index": item.get("index"),
                    "source_page": item.get("page"),
                    "source_level": item.get("source_level"),
                    "level": item.get("level"),
                },
            )
        )
    return tasks


def tasks_from_length_outliers(
    *,
    work_id: str,
    qa: dict[str, Any],
    qa_path: Path,
    passages: dict[str, dict[str, Any]],
    long_limit: int | None,
    short_limit: int | None,
) -> list[dict[str, Any]]:
    tasks = []
    long_rows = qa.get("passages", {}).get("long_passages") or []
    short_rows = qa.get("passages", {}).get("short_passages") or []
    if long_limit is not None:
        long_rows = long_rows[:long_limit]
    if short_limit is not None:
        short_rows = short_rows[:short_limit]

    for item in long_rows:
        passage_id = item.get("id")
        passage = passages.get(passage_id or "")
        tasks.append(
            task_doc(
                work_id=work_id,
                task_type="long_passage_review",
                source_key=f"long:{passage_id}:{item.get('length')}",
                priority="low",
                title=f"Review long passage {passage_id}",
                reason=f"QA found a long passage ({item.get('length')} chars).",
                recommended_action="Check whether this passage should stay merged or be split before editorial review/layout.",
                passage_id=passage_id,
                section_path=item.get("section_path") or (passage or {}).get("section_path") or [],
                source_citation_label=citation_label(passage),
                text_preview=item.get("text") or (passage or {}).get("text") or "",
                source={
                    "kind": "qa_long_passage",
                    "path": project_relative(qa_path),
                    "length": item.get("length"),
                    "source_page": item.get("source_page"),
                },
            )
        )

    for item in short_rows:
        passage_id = item.get("id")
        passage = passages.get(passage_id or "")
        tasks.append(
            task_doc(
                work_id=work_id,
                task_type="short_passage_review",
                source_key=f"short:{passage_id}:{item.get('length')}",
                priority="low",
                title=f"Review short passage {passage_id}",
                reason=f"QA found a very short passage ({item.get('length')} chars).",
                recommended_action="Check whether this is a real short label, page artifact, heading fragment, or should be merged.",
                passage_id=passage_id,
                section_path=item.get("section_path") or (passage or {}).get("section_path") or [],
                source_citation_label=citation_label(passage),
                text_preview=item.get("text") or (passage or {}).get("text") or "",
                source={
                    "kind": "qa_short_passage",
                    "path": project_relative(qa_path),
                    "length": item.get("length"),
                    "source_page": item.get("source_page"),
                },
            )
        )

    return tasks


def tasks_from_translation_rows(
    *,
    work_id: str,
    book_dir: Path,
    passages: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    tasks = []
    translations_dir = book_dir / "translations"
    if not translations_dir.exists():
        return tasks

    for path in sorted(translations_dir.glob("*/passages.jsonl")):
        lang = path.parent.name
        for row in read_jsonl(path):
            warnings = row.get("warnings") or []
            if not warnings:
                continue
            passage_id = row.get("source_passage_id")
            passage = passages.get(passage_id or "")
            tasks.append(
                task_doc(
                    work_id=work_id,
                    task_type="translation_warning",
                    source_key=f"translation:{lang}:{row.get('id')}:{'|'.join(map(str, warnings))}",
                    priority="medium",
                    title=f"Review {lang} translation warning for {passage_id}",
                    reason="LLM translation returned warnings.",
                    recommended_action="Review translation wording, source damage warnings, and decide whether the translation needs correction or source review.",
                    passage_id=passage_id,
                    section_path=row.get("section_path") or (passage or {}).get("section_path") or [],
                    source_citation_label=citation_label(passage),
                    text_preview="; ".join(str(item) for item in warnings),
                    source={
                        "kind": "translation_warning",
                        "path": project_relative(path),
                        "translation_id": row.get("id"),
                        "lang": lang,
                        "warnings": warnings,
                    },
                )
            )
    return tasks


def tasks_from_translation_qa(
    *,
    work_id: str,
    qa: dict[str, Any],
    qa_path: Path,
    passages: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    tasks = []
    for translation in qa.get("translations") or []:
        lang = translation.get("lang")
        for category, priority in [
            ("arabic_leak_rows", "high"),
            ("length_ratio_outliers", "medium"),
            ("source_citation_mismatches", "high"),
            ("id_shape_mismatches", "medium"),
        ]:
            for item in translation.get(category) or []:
                passage_id = item.get("source_passage_id")
                passage = passages.get(passage_id or "")
                tasks.append(
                    task_doc(
                        work_id=work_id,
                        task_type="translation_qa",
                        source_key=f"translation_qa:{lang}:{category}:{item.get('id') or passage_id}",
                        priority=priority,
                        title=f"Fix {lang} translation QA: {category}",
                        reason=f"Translation QA reported `{category}`.",
                        recommended_action="Review translation row and source anchor metadata before marking reviewed.",
                        passage_id=passage_id,
                        section_path=(passage or {}).get("section_path") or [],
                        source_citation_label=citation_label(passage),
                        text_preview=item.get("text") or json.dumps(item, ensure_ascii=False),
                        source={
                            "kind": "translation_qa",
                            "path": project_relative(qa_path),
                            "lang": lang,
                            "category": category,
                            "item": item,
                        },
                    )
                )
    return tasks


def dedupe(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for task in tasks:
        by_id[task["doc_id"]] = task
    return sorted(
        by_id.values(),
        key=lambda task: (
            task["data"]["priority_rank"],
            task["data"].get("work_id") or "",
            task["data"].get("passage_id") or "",
            task["data"].get("task_type") or "",
            task["doc_id"],
        ),
    )


def render_markdown(tasks: list[dict[str, Any]], work_id: str) -> str:
    counts = Counter(task["data"]["task_type"] for task in tasks)
    priorities = Counter(task["data"]["priority"] for task in tasks)
    lines = [
        f"# Editorial Review Tasks: {work_id}",
        "",
        "These rows are Firestore-ready drafts for `reviewTasks`. They have not been uploaded.",
        "",
        f"- Total: `{len(tasks)}`",
        f"- Types: `{dict(counts)}`",
        f"- Priorities: `{dict(priorities)}`",
        "",
        "| Priority | Type | Passage | Title | Source |",
        "| --- | --- | --- | --- | --- |",
    ]
    for task in tasks:
        data = task["data"]
        source = data.get("source") or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{data.get('priority')}`",
                    f"`{data.get('task_type')}`",
                    f"`{data.get('passage_id') or ''}`",
                    compact(data.get("title") or "", 90),
                    f"`{source.get('kind') or ''}`",
                ]
            )
            + " |"
        )

    lines.extend(["", "## Samples", ""])
    for task in tasks[:30]:
        data = task["data"]
        lines.extend(
            [
                f"### {task['doc_id']}",
                "",
                f"- Type: `{data['task_type']}`",
                f"- Priority: `{data['priority']}`",
                f"- Passage: `{data.get('passage_id') or ''}`",
                f"- Section: `{ ' > '.join(data.get('section_path') or []) }`",
                f"- Citation: {data.get('source_citation_label') or ''}",
                f"- Reason: {data.get('reason') or ''}",
                f"- Action: {data.get('recommended_action') or ''}",
                "",
                f"> {data.get('text_preview') or ''}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-dir", required=True, type=Path)
    parser.add_argument("--qa-report", type=Path)
    parser.add_argument("--semantic-queue", default="annotations/semantic-review-queue.jsonl")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--review-md", type=Path)
    parser.add_argument("--long-limit", type=int, default=13)
    parser.add_argument("--short-limit", type=int, default=10)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    book_dir = args.book_dir.resolve()
    book = load_yaml(book_dir / "book.yml")
    work_id = book.get("id") or book_dir.name
    qa_path = args.qa_report or PROJECT_ROOT / "reports" / "qa" / f"{work_id}.json"
    semantic_queue_path = book_dir / args.semantic_queue if args.semantic_queue else None
    out_path = args.out or PROJECT_ROOT / "reports" / "editorial-review-tasks" / f"{work_id}-review-tasks.jsonl"
    md_path = args.review_md or PROJECT_ROOT / "reports" / "editorial-review-tasks" / f"{work_id}-review-tasks.md"

    qa = load_json(qa_path)
    passages = load_passages(book_dir)
    tasks: list[dict[str, Any]] = []

    if semantic_queue_path and semantic_queue_path.exists():
        tasks.extend(tasks_from_semantic_queue(work_id=work_id, path=semantic_queue_path))

    if qa:
        tasks.extend(tasks_from_cleaning_report(work_id=work_id, qa=qa, qa_path=qa_path, passages=passages))
        tasks.extend(tasks_from_toc(work_id=work_id, qa=qa, qa_path=qa_path))
        tasks.extend(
            tasks_from_length_outliers(
                work_id=work_id,
                qa=qa,
                qa_path=qa_path,
                passages=passages,
                long_limit=args.long_limit,
                short_limit=args.short_limit,
            )
        )
        tasks.extend(tasks_from_translation_qa(work_id=work_id, qa=qa, qa_path=qa_path, passages=passages))

    tasks.extend(tasks_from_translation_rows(work_id=work_id, book_dir=book_dir, passages=passages))
    tasks = dedupe(tasks)
    if args.limit is not None:
        tasks = tasks[: args.limit]

    counts = Counter(task["data"]["task_type"] for task in tasks)
    priorities = Counter(task["data"]["priority"] for task in tasks)
    print(f"tasks={len(tasks)} types={dict(counts)} priorities={dict(priorities)}")

    if args.dry_run:
        for task in tasks[:10]:
            data = task["data"]
            print(f"- {task['doc_id']} {data['priority']} {data['task_type']} {data.get('passage_id') or ''}: {data['title']}")
        return

    write_jsonl(out_path, tasks)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(tasks, work_id), encoding="utf-8")
    print(f"ok: wrote {project_relative(out_path)}")
    print(f"ok: wrote {project_relative(md_path)}")


if __name__ == "__main__":
    main()
