#!/usr/bin/env python3
"""Sync Typst page-map citations into passages.jsonl edition_refs."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
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
    text = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for row in rows
    )
    path.write_text(text, encoding="utf-8")


def load_page_map(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Page map not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not data.get("edition"):
        raise SystemExit(f"Page map has no edition: {path}")
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise SystemExit(f"Page map entries must be a list: {path}")
    return data


def load_book(path: Path) -> dict[str, Any]:
    if yaml is None or not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def project_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


def validate_mapping(rows: list[dict[str, Any]], page_map: dict[str, Any]) -> dict[str, list[str]]:
    passage_ids = [row.get("id") for row in rows if row.get("id")]
    passage_set = set(passage_ids)
    entries = page_map.get("entries") or []
    entry_ids = [entry.get("id") for entry in entries if isinstance(entry, dict) and entry.get("id")]
    entry_set = set(entry_ids)
    duplicate_entries = sorted(pid for pid in entry_set if entry_ids.count(pid) > 1)

    return {
        "duplicate_page_map_ids": duplicate_entries[:50],
        "missing_page_map_ids": sorted(passage_set - entry_set)[:50],
        "extra_page_map_ids": sorted(entry_set - passage_set)[:50],
    }


def page_locator(entry: dict[str, Any]) -> dict[str, Any]:
    page = entry.get("page")
    label = entry.get("page_label") or (str(page) if page is not None else "")
    locator = {
        "type": entry.get("locator_type") or "page",
        "label": label,
    }
    if page is not None:
        locator["page"] = page
    return locator


def public_citation(pid: str, edition: str, ref: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": f"edition_refs.{edition}",
        "edition_id": edition,
        "anchor_id": pid,
        "label": ref["label"],
        "locator": ref["locator"],
    }


def sync_edition_refs(
    rows: list[dict[str, Any]],
    page_map: dict[str, Any],
    page_map_path: Path,
    default_edition: str | None,
) -> tuple[list[dict[str, Any]], int]:
    edition = page_map["edition"]
    page_semantics = page_map.get("page_semantics") or "start_page"
    entries = {
        entry["id"]: entry
        for entry in page_map.get("entries") or []
        if isinstance(entry, dict) and entry.get("id")
    }
    source = project_relative(page_map_path)
    changed = 0

    for row in rows:
        pid = row.get("id")
        if pid not in entries:
            continue
        entry = entries[pid]
        edition_refs = row.get("edition_refs")
        if not isinstance(edition_refs, dict):
            edition_refs = {}

        next_ref = {
            "label": entry.get("citation")
            or f"{page_map.get('work_id')}, ed. {edition}, hlm. {entry.get('page')}, {pid}.",
            "locator": page_locator(entry),
            "page": entry.get("page"),
            "page_semantics": page_semantics,
            "physical_page": entry.get("physical_page"),
            "viewer": {
                "pdf_page": entry.get("physical_page"),
            },
            "source": source,
        }
        next_ref = {
            key: value
            for key, value in next_ref.items()
            if value is not None and value != {"pdf_page": None}
        }

        before_ref = edition_refs.get(edition)
        before_citation = row.get("citation")
        if edition_refs.get(edition) != next_ref:
            edition_refs[edition] = next_ref
            row["edition_refs"] = edition_refs
            changed += 1
        if default_edition == edition:
            next_citation = public_citation(pid, edition, next_ref)
            if before_ref != next_ref or before_citation != next_citation:
                row["citation"] = next_citation
                if before_ref == next_ref:
                    changed += 1

    return rows, changed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-dir", required=True, type=Path)
    parser.add_argument("--edition", default="surau-v0")
    parser.add_argument("--page-map", help="Defaults to editions/{edition}/page-map.json")
    parser.add_argument("--passages", default="passages.jsonl")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--backup", action="store_true", help="Write passages.jsonl.bak before updating.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    book_dir = args.book_dir.resolve()
    passages_path = book_dir / args.passages
    book = load_book(book_dir / "book.yml")
    default_edition = book.get("default_edition")
    page_map_path = (
        (book_dir / args.page_map)
        if args.page_map
        else book_dir / "editions" / args.edition / "page-map.json"
    )

    rows = read_jsonl(passages_path)
    page_map = load_page_map(page_map_path)
    if page_map["edition"] != args.edition:
        raise SystemExit(
            f"Edition mismatch: --edition={args.edition}, page-map edition={page_map['edition']}"
        )

    validation = validate_mapping(rows, page_map)
    if any(validation.values()):
        raise SystemExit(json.dumps(validation, ensure_ascii=False, indent=2))

    rows, changed = sync_edition_refs(rows, page_map, page_map_path, default_edition)
    if not args.dry_run:
        if args.backup:
            shutil.copy2(passages_path, passages_path.with_suffix(passages_path.suffix + ".bak"))
        write_jsonl(passages_path, rows)

    action = "would update" if args.dry_run else "updated"
    print(f"ok: {action} {changed} passages for edition {args.edition}")


if __name__ == "__main__":
    main()
