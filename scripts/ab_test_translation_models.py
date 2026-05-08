#!/usr/bin/env python3
"""Run translation A/B tests across multiple LLM models."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from translate_passages import (
    DEFAULT_API_BASE,
    build_messages,
    call_llm,
    overlay_manuscript_text,
    parse_id_args,
    read_jsonl,
    select_rows,
)


DEFAULT_MODELS = [
    "z-ai/glm-5.1",
    "deepseek-v4-pro",
    "minimax/minimax-m2.7",
    "qwen/qwen3.6-flash",
]


def slug(value: str) -> str:
    return (
        value.replace("/", "__")
        .replace(":", "-")
        .replace(" ", "-")
        .replace(".", "-")
    )


def truncate(text: str, limit: int = 800) -> str:
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def run_ab_test(args: argparse.Namespace) -> dict[str, Any]:
    book_dir = args.book_dir.resolve()
    rows = read_jsonl(book_dir / args.source)
    overlay_count = 0
    if args.manuscript:
        rows, overlay_count = overlay_manuscript_text(rows, book_dir / args.manuscript)

    selected = select_rows(rows, parse_id_args(args.ids), args.limit, args.offset)
    if args.max_chars:
        truncated = []
        for row in selected:
            next_row = dict(row)
            text = next_row.get("text") or ""
            if len(text) > args.max_chars:
                next_row["text"] = text[: args.max_chars].rstrip()
                next_row["_ab_test_truncated"] = True
            truncated.append(next_row)
        selected = truncated
    if not selected:
        raise SystemExit("No source rows selected.")

    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        raise SystemExit(f"Missing API key. Set {args.api_key_env} in your environment.")

    started = datetime.now(timezone.utc).isoformat()
    report: dict[str, Any] = {
        "schema_version": "0.1",
        "started_at": started,
        "book_dir": str(book_dir),
        "lang": args.lang,
        "models": args.models,
        "source_ids": [row.get("id") for row in selected],
        "text_overlay_count": overlay_count,
        "samples": [],
    }

    def save_partial() -> None:
        if not getattr(args, "_json_path", None):
            return
        args._json_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        args._md_path.write_text(render_markdown(report), encoding="utf-8")

    for row in selected:
        sample = {
            "id": row.get("id"),
            "citation": (row.get("citation") or {}).get("label"),
            "section_path": row.get("section_path") or [],
            "source_text_length": len(row.get("text") or ""),
            "truncated": bool(row.get("_ab_test_truncated")),
            "source_text_preview": truncate(row.get("text") or "", 1200),
            "results": [],
        }
        print(f"sample {row.get('id')} len={sample['source_text_length']}", flush=True)
        messages = build_messages(row, args.lang)
        report["samples"].append(sample)

        for model in args.models:
            print(f"  model {model}", flush=True)
            started_model = time.monotonic()
            result: dict[str, Any]
            try:
                data = call_llm(
                    args.api_base,
                    api_key,
                    model,
                    messages,
                    args.temperature,
                    args.timeout,
                    args.retries,
                    args.ca_bundle,
                )
                result = {
                    "model": model,
                    "ok": True,
                    "latency_seconds": round(time.monotonic() - started_model, 3),
                    "translation": str(data.get("translation") or "").strip(),
                    "notes": data.get("notes") or [],
                    "warnings": data.get("warnings") or [],
                }
                if not result["translation"]:
                    result["ok"] = False
                    result["error"] = f"Empty translation: {data}"
            except Exception as exc:  # noqa: BLE001 - report all model failures.
                result = {
                    "model": model,
                    "ok": False,
                    "latency_seconds": round(time.monotonic() - started_model, 3),
                    "error": str(exc),
                }
            sample["results"].append(result)
            save_partial()
            if args.sleep:
                time.sleep(args.sleep)

        save_partial()

    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Translation A/B Test",
        "",
        f"- Started: `{report['started_at']}`",
        f"- Language: `{report['lang']}`",
        f"- Models: `{', '.join(report['models'])}`",
        f"- Samples: `{', '.join(report['source_ids'])}`",
        f"- Text overlay count: `{report['text_overlay_count']}`",
        "",
    ]

    for sample in report["samples"]:
        lines.extend(
            [
                f"## {sample['id']}",
                "",
                f"- Citation: {sample.get('citation') or 'none'}",
                f"- Source length: `{sample['source_text_length']}`",
                f"- Truncated: `{sample.get('truncated', False)}`",
                "",
                "### Source Preview",
                "",
                sample["source_text_preview"],
                "",
                "### Results",
                "",
            ]
        )
        for result in sample["results"]:
            status = "ok" if result.get("ok") else "failed"
            lines.extend(
                [
                    f"#### {result['model']} ({status}, {result.get('latency_seconds')}s)",
                    "",
                ]
            )
            if result.get("ok"):
                lines.extend(
                    [
                        result.get("translation") or "",
                        "",
                        f"- Notes: `{json.dumps(result.get('notes') or [], ensure_ascii=False)}`",
                        f"- Warnings: `{json.dumps(result.get('warnings') or [], ensure_ascii=False)}`",
                        "",
                    ]
                )
            else:
                lines.extend([f"Error: `{result.get('error')}`", ""])

    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-dir", required=True, type=Path)
    parser.add_argument("--lang", default="id")
    parser.add_argument("--source", default="passages.jsonl")
    parser.add_argument("--manuscript", default="clean/manuscript.md")
    parser.add_argument("--id", action="append", dest="ids", help="Source passage ID; repeatable or comma-separated.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--max-chars", type=int, help="Truncate source text for model comparison only.")
    parser.add_argument("--model", action="append", dest="models", default=[])
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--api-key-env", default="KILO_API_KEY")
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--retries", type=int, default=0)
    parser.add_argument("--ca-bundle")
    parser.add_argument("--sleep", type=float, default=0)
    parser.add_argument("--out-dir", type=Path, default=Path("reports/translation-ab-tests"))
    parser.add_argument("--name", help="Output filename stem.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.models:
        args.models = DEFAULT_MODELS

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.name or datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = args.out_dir / f"{slug(stem)}.json"
    md_path = args.out_dir / f"{slug(stem)}.md"
    args._json_path = json_path
    args._md_path = md_path

    report = run_ab_test(args)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"ok: wrote {json_path}")
    print(f"ok: wrote {md_path}")


if __name__ == "__main__":
    main()
