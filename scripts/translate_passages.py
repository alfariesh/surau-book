#!/usr/bin/env python3
"""Translate canonical passage rows with an OpenAI-compatible LLM gateway."""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

try:
    import certifi
except ImportError:  # pragma: no cover
    certifi = None


DEFAULT_API_BASE = "https://api.kilo.ai/api/gateway"
DEFAULT_MODEL = "deepseek-v4-pro"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
PASSAGE_RE = re.compile(r'^::passage\{id="([^"]+)"\}\s*$')
HEADING_RE = re.compile(r"^#{1,6}\s+")

LANGUAGE_NAMES = {
    "id": "Indonesian",
    "en": "English",
    "ms": "Malay",
}

LANGUAGE_STYLE_RULES = {
    "id": [
        "Use natural Indonesian suitable for a pesantren-style Islamic education platform.",
        "Keep common Islamic terms such as shalawat, makrifat, syuhud, and hadirat when clearer than over-translation.",
    ],
    "en": [
        "Use clear scholarly English.",
        "Keep common Islamic terms such as salawat, ma'rifah, shuhud, and hadrah when clearer than over-translation.",
    ],
    "ms": [
        "Use natural Malay suitable for Islamic learning materials.",
        "Keep common Islamic terms when clearer than over-translation.",
    ],
}


class RowDeadlineExceeded(TimeoutError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    if yaml is None or not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if yaml is not None:
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        return
    lines = [f"{key}: {value}" for key, value in data.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for row in rows
    )
    path.write_text(text, encoding="utf-8")


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


def overlay_manuscript_text(
    rows: list[dict[str, Any]],
    manuscript_path: Path,
) -> tuple[list[dict[str, Any]], int]:
    passages = parse_manuscript_passages(manuscript_path)
    if not passages:
        return rows, 0

    overlaid = []
    changed = 0
    source = project_relative(manuscript_path)
    for row in rows:
        next_row = dict(row)
        pid = row.get("id")
        if pid in passages and passages[pid] != row.get("text"):
            next_row["text"] = passages[pid]
            next_row["_translation_source_text"] = source
            changed += 1
        elif pid in passages:
            next_row["_translation_source_text"] = source
        overlaid.append(next_row)
    return overlaid, changed


def project_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


def chat_url(api_base: str) -> str:
    base = api_base.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def ssl_context(ca_bundle: str | None = None) -> ssl.SSLContext:
    if ca_bundle:
        return ssl.create_default_context(cafile=ca_bundle)
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()


def parse_id_args(values: list[str] | None) -> set[str] | None:
    if not values:
        return None
    ids: set[str] = set()
    for value in values:
        ids.update(item.strip() for item in value.split(",") if item.strip())
    return ids


def select_rows(
    rows: list[dict[str, Any]],
    ids: set[str] | None,
    limit: int | None,
    offset: int,
) -> list[dict[str, Any]]:
    selected = [row for row in rows if not ids or row.get("id") in ids]
    if offset:
        selected = selected[offset:]
    if limit is not None:
        selected = selected[:limit]
    return selected


def load_annotations(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    if not path.exists():
        raise SystemExit(f"Annotation file not found: {path}")
    return {
        row["id"]: row
        for row in read_jsonl(path)
        if isinstance(row, dict) and row.get("id")
    }


def resolve_book_path(book_dir: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    return book_dir / path


def truncate(text: str, limit: int = 360) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def semantic_context(annotation: dict[str, Any] | None) -> dict[str, Any]:
    if not annotation:
        return {}

    proposal = annotation.get("llm_proposal")
    proposal = proposal if isinstance(proposal, dict) else {}
    segments = proposal.get("segments") if isinstance(proposal.get("segments"), list) else []
    clean_segments = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        source_span = segment.get("source_span")
        source_span = source_span if isinstance(source_span, dict) else {}
        clean_segments.append(
            {
                "span_id": segment.get("span_id") or source_span.get("span_id"),
                "kind": segment.get("kind"),
                "ref": segment.get("ref") or "",
                "review_required": bool(segment.get("review_required")),
                "source_span": {
                    key: source_span.get(key)
                    for key in ("start", "end", "reason")
                    if source_span.get(key) is not None
                },
                "text_preview": truncate(segment.get("text") or "", 120),
            }
        )

    context = {
        "kind": annotation.get("kind"),
        "role": annotation.get("role"),
        "layout": annotation.get("layout"),
        "status": annotation.get("status"),
        "review_decision": annotation.get("review_decision"),
        "segment_count": len(clean_segments),
        "segments": clean_segments,
        "has_review_notes": bool(proposal.get("review_notes")),
    }
    return {key: value for key, value in context.items() if value not in (None, "", [], {})}


def translation_guidance_from_semantics(context: dict[str, Any]) -> list[str]:
    if not context:
        return []

    segment_kinds = {
        segment.get("kind")
        for segment in context.get("segments", [])
        if isinstance(segment, dict) and segment.get("kind")
    }
    guidance = [
        "Use the semantic_context only as translation guidance; do not add it as commentary.",
        "Do not translate or mention internal fields such as kind, role, layout, span_id, or review_required.",
    ]
    if "ayah" in segment_kinds:
        guidance.append(
            "For Qur'an segments, translate the meaning carefully and do not assert a surah/ayah reference unless it is explicitly reviewed in the source metadata."
        )
    if "hadith" in segment_kinds:
        guidance.append(
            "For hadith/report segments, translate the source wording only; do not add takhrij, grading, isnad claims, or source claims that are not in the Arabic."
        )
    if any(segment.get("review_required") for segment in context.get("segments", []) if isinstance(segment, dict)):
        guidance.append(
            "If a source phrase looks damaged or OCR-corrupted, do not silently reconstruct it from memory; translate the visible wording as faithfully as possible and put uncertainty in warnings."
        )
    if "dua" in segment_kinds or context.get("role") == "matn":
        guidance.append("For du'a or salawat, preserve devotional tone and repeated invocations.")
    if "quote" in segment_kinds or context.get("role") == "quote":
        guidance.append("For quoted scholarly material, preserve attribution if it appears in the Arabic text.")
    return guidance


def ensure_translation_yml(
    path: Path,
    book: dict[str, Any],
    lang: str,
    source_path: Path,
    model: str,
) -> None:
    defaults = {
        "schema_version": 0.1,
        "work_id": book.get("id"),
        "lang": lang,
        "source_language": book.get("canonical_language") or book.get("language") or "ar",
        "source_passages": project_relative(source_path),
        "status": "machine_draft",
        "translator": "Surau LLM Draft",
        "translation_type": "meaning",
        "citation_policy": "cite_source_passage",
        "model": model,
    }
    data = load_yaml(path) if path.exists() else {}
    changed = not path.exists()
    for key, value in defaults.items():
        if key not in data:
            data[key] = value
            changed = True
    if data.get("model") != model:
        data["model"] = model
        changed = True
    if not changed:
        return
    write_yaml(path, data)


def build_messages(
    row: dict[str, Any],
    target_lang: str,
    annotation: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    target_name = LANGUAGE_NAMES.get(target_lang, target_lang)
    section_path = " > ".join(row.get("section_path") or [])
    citation = (row.get("citation") or {}).get("label") or ""
    semantics = semantic_context(annotation)
    style_rules = LANGUAGE_STYLE_RULES.get(
        target_lang,
        [f"Use natural {target_name} suitable for Islamic learning materials."],
    )

    system = (
        "You translate classical Arabic Islamic texts for a scholarly multilingual Islamic "
        f"education platform. Translate into {target_name} only. Be faithful, clear, and "
        "reverent. Do not add commentary, takhrij, or new claims. Preserve names, book titles, "
        "and important Islamic terms when a direct translation would be misleading. Do not leave "
        "untranslated Arabic words unless they are approved technical terms or proper names. "
        "Return strict JSON only."
    )
    user = {
        "task": f"Translate the Arabic passage into {target_name}.",
        "output_schema": {
            "translation": "string",
            "notes": ["short optional translator notes, empty array if none"],
            "warnings": ["short optional warnings about ambiguity, empty array if none"],
        },
        "style": [
            *style_rules,
            "Keep honorifics concise and respectful.",
            "For salawat/du'a passages, preserve devotional tone.",
            "Do not omit repeated phrases unless the source repeats them.",
            *translation_guidance_from_semantics(semantics),
        ],
        "metadata": {
            "id": row.get("id"),
            "section_path": section_path,
            "citation": citation,
        },
        "semantic_context": semantics,
        "arabic_text": row.get("text") or "",
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ]


def extract_json_object(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def call_llm(
    api_base: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    timeout: float,
    retries: int,
    ca_bundle: str | None,
) -> dict[str, Any]:
    url = chat_url(api_base)
    context = ssl_context(ca_bundle)
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }

    last_error = ""
    for attempt in range(retries + 1):
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
                data = json.loads(response.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(
                    item.get("text", "") if isinstance(item, dict) else str(item)
                    for item in content
                )
            return extract_json_object(str(content))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            last_error = f"HTTP {exc.code}: {body}"
            if exc.code == 400 and "response_format" in payload:
                payload.pop("response_format", None)
            elif exc.code not in {408, 409, 429, 500, 502, 503, 504}:
                break
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
            last_error = str(exc)

        if attempt < retries:
            time.sleep(min(2**attempt, 8))

    raise RuntimeError(last_error or "LLM call failed")


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


def make_translation_row(
    source_row: dict[str, Any],
    lang: str,
    model: str,
    translation: str,
    notes: list[Any],
    warnings: list[Any],
    status: str,
    translator: str,
    annotation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_id = source_row["id"]
    semantics = semantic_context(annotation)
    return {
        "id": f"{source_id}.{lang}",
        "work_id": source_row.get("work_id"),
        "lang": lang,
        "source_lang": source_row.get("lang") or "ar",
        "source_passage_id": source_id,
        "source_sequence": source_row.get("sequence"),
        "section_path": source_row.get("section_path") or [],
        "source_citation": source_row.get("citation"),
        "source_text": source_row.get("_translation_source_text") or "passages.jsonl",
        "translation_status": status,
        "translation_type": "meaning",
        "translator": translator,
        "model": model,
        "semantic_context": semantics,
        "text": translation.strip(),
        "notes": notes if isinstance(notes, list) else [],
        "warnings": warnings if isinstance(warnings, list) else [],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-dir", required=True, type=Path)
    parser.add_argument("--lang", default="id")
    parser.add_argument("--source", default="passages.jsonl")
    parser.add_argument(
        "--annotations",
        default="annotations/semantic-reviewed.jsonl",
        help="Optional semantic annotation JSONL path relative to --book-dir. Pass an empty string to disable.",
    )
    parser.add_argument(
        "--manuscript",
        default="clean/manuscript.md",
        help="Clean manuscript text overlay. Pass an empty string to disable.",
    )
    parser.add_argument("--out", help="Defaults to translations/{lang}/passages.jsonl")
    parser.add_argument("--translation-yml", help="Defaults to translations/{lang}/translation.yml")
    parser.add_argument("--id", action="append", dest="ids", help="Source passage ID; repeatable or comma-separated.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--api-key-env", default="KILO_API_KEY")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--row-deadline", type=float, default=0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--ca-bundle", help="Optional CA bundle path. Defaults to certifi when installed.")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--status", default="machine_draft")
    parser.add_argument("--translator", default="Surau LLM Draft")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    book_dir = args.book_dir.resolve()
    book = load_yaml(book_dir / "book.yml")
    source_path = book_dir / args.source
    out_path = book_dir / (args.out or f"translations/{args.lang}/passages.jsonl")
    translation_yml = book_dir / (
        args.translation_yml or f"translations/{args.lang}/translation.yml"
    )
    annotations = load_annotations(resolve_book_path(book_dir, args.annotations))

    source_rows = read_jsonl(source_path)
    overlay_count = 0
    if args.manuscript:
        source_rows, overlay_count = overlay_manuscript_text(source_rows, book_dir / args.manuscript)
    existing_rows = read_jsonl(out_path)
    existing_by_source = {
        row.get("source_passage_id"): row
        for row in existing_rows
        if row.get("source_passage_id")
    }
    ids = parse_id_args(args.ids)
    selected = select_rows(source_rows, ids, args.limit, args.offset)
    todo = [
        row
        for row in selected
        if row.get("id") and (args.force or row.get("id") not in existing_by_source)
    ]

    if args.dry_run:
        print(
            f"selected={len(selected)} todo={len(todo)} existing={len(existing_rows)} "
            f"text_overlay={overlay_count} annotations={len(annotations)}"
        )
        for row in todo[:10]:
            context = semantic_context(annotations.get(row.get("id", "")))
            kinds = [
                segment.get("kind")
                for segment in context.get("segments", [])
                if isinstance(segment, dict) and segment.get("kind")
            ]
            print(f"- {row.get('id')}: semantic={context.get('kind')} segments={kinds} {(row.get('text') or '')[:80]}")
        return

    ensure_translation_yml(translation_yml, book, args.lang, source_path, args.model)

    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        raise SystemExit(f"Missing API key. Set {args.api_key_env} in your environment.")

    output_by_source = dict(existing_by_source)
    source_order = [row.get("id") for row in source_rows if row.get("id")]

    for index, row in enumerate(todo, start=1):
        pid = row["id"]
        annotation = annotations.get(pid)
        print(f"[{index}/{len(todo)}] translating {pid}", flush=True)
        try:
            result = call_llm_with_deadline(
                args.row_deadline,
                args.api_base,
                api_key,
                args.model,
                build_messages(row, args.lang, annotation),
                args.temperature,
                args.timeout,
                args.retries,
                args.ca_bundle,
            )
            translation = str(result.get("translation") or "").strip()
            if not translation:
                raise RuntimeError(f"Empty translation for {pid}: {result}")
            output_by_source[pid] = make_translation_row(
                row,
                args.lang,
                args.model,
                translation,
                result.get("notes") or [],
                result.get("warnings") or [],
                args.status,
                args.translator,
                annotation,
            )
            ordered = [output_by_source[pid] for pid in source_order if pid in output_by_source]
            write_jsonl(out_path, ordered)
        except Exception as exc:
            if not args.continue_on_error:
                raise
            print(f"[{index}/{len(todo)}] {pid}: error: {exc}", flush=True)

    print(f"ok: wrote {out_path} rows={len(output_by_source)}")


if __name__ == "__main__":
    main()
