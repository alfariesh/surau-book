#!/usr/bin/env python3
"""Build a Typst edition page map from passage metadata."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]

PAGE_MAP_QUERY = """// Generated temporarily by scripts/build_page_map.py.
// It includes the edition, then emits invisible page-map metadata entries.

#include "ENTRYPOINT"

#context {
  for item in query(metadata) {
    let value = item.value
    if type(value) == dictionary and value.at("kind", default: none) == "passage" {
      metadata((
        kind: "page-map-entry",
        id: value.at("id", default: ""),
        role: value.at("role", default: "body"),
        page: counter(page).at(item.location()).first(),
        physical_page: item.location().page(),
      ))
    }
  }
}
"""


def load_yaml(path: Path) -> dict[str, Any]:
    if yaml is None or not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def project_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


def resolve_font_paths(font_paths: list[str] | None) -> list[str]:
    resolved = []
    for value in font_paths or []:
        path = Path(value)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        resolved.append(str(path.resolve()))
    return resolved


def run_typst_query(
    edition_dir: Path,
    entrypoint: str,
    typst_bin: str,
    font_paths: list[str] | None = None,
) -> list[dict[str, Any]]:
    helper_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            suffix=".typ",
            prefix=".page-map-query-",
            dir=edition_dir,
            delete=False,
        ) as handle:
            helper_path = Path(handle.name)
            handle.write(PAGE_MAP_QUERY.replace("ENTRYPOINT", entrypoint))

        command = [typst_bin, "query"]
        for font_path in font_paths or []:
            command.extend(["--font-path", font_path])
        command.extend([helper_path.name, "metadata"])
        result = subprocess.run(
            command,
            cwd=edition_dir,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise SystemExit(result.stderr.strip() or result.stdout.strip())
        return json.loads(result.stdout)
    finally:
        if helper_path and helper_path.exists():
            helper_path.unlink()


def extract_page_entries(raw_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries = []
    for item in raw_items:
        value = item.get("value")
        if not isinstance(value, dict):
            continue
        if value.get("kind") != "page-map-entry":
            continue
        pid = value.get("id")
        if not pid:
            continue
        page = value.get("page")
        physical_page = value.get("physical_page")
        entries.append(
            {
                "id": pid,
                "role": value.get("role") or "body",
                "page": page if isinstance(page, int) else None,
                "physical_page": physical_page if isinstance(physical_page, int) else None,
            }
        )
    return entries


def build_page_map(
    book_dir: Path,
    edition: str,
    entrypoint: str,
    typst_bin: str,
    font_paths: list[str] | None = None,
) -> dict[str, Any]:
    book = load_yaml(book_dir / "book.yml")
    work_id = book.get("id") or book_dir.name
    citation_title = book.get("title_id") or book.get("title_ar") or work_id
    edition_dir = book_dir / "editions" / edition
    if not edition_dir.exists():
        raise SystemExit(f"Edition directory not found: {edition_dir}")
    if not (edition_dir / entrypoint).exists():
        raise SystemExit(f"Typst entrypoint not found: {edition_dir / entrypoint}")

    rows = read_jsonl(book_dir / "passages.jsonl")
    passage_ids = [row.get("id") for row in rows if row.get("id")]
    passage_index = {pid: index for index, pid in enumerate(passage_ids, start=1)}
    raw_items = run_typst_query(
        edition_dir,
        entrypoint,
        typst_bin,
        resolve_font_paths(font_paths),
    )
    entries = extract_page_entries(raw_items)
    entries.sort(key=lambda item: passage_index.get(item["id"], 10**12))

    counts = Counter(item["id"] for item in entries)
    duplicate_ids = sorted(pid for pid, count in counts.items() if count > 1)
    entry_ids = {item["id"] for item in entries}
    passage_id_set = set(passage_ids)

    by_page: dict[str, list[str]] = defaultdict(list)
    page_values = []
    for item in entries:
        if isinstance(item.get("page"), int):
            by_page[str(item["page"])].append(item["id"])
            page_values.append(item["page"])
            item["citation"] = (
                f"{citation_title}, ed. {edition}, hlm. {item['page']}, {item['id']}."
            )

    return {
        "schema_version": "0.1",
        "work_id": work_id,
        "edition": edition,
        "source_typst": entrypoint,
        "source_pdf": (book.get("source") or {}).get("pdf"),
        "page_semantics": "start_page",
        "citation_format": "{title}, ed. {edition}, hlm. {page}, {passage_id}.",
        "entry_count": len(entries),
        "passage_count": len(passage_ids),
        "page_range": {
            "min": min(page_values) if page_values else None,
            "max": max(page_values) if page_values else None,
            "unique": len(set(page_values)),
        },
        "entries": entries,
        "by_page": dict(sorted(by_page.items(), key=lambda item: int(item[0]))),
        "validation": {
            "duplicate_ids": duplicate_ids[:50],
            "missing_passage_ids": sorted(passage_id_set - entry_ids)[:50],
            "extra_page_map_ids": sorted(entry_ids - passage_id_set)[:50],
        },
        "generated_by": project_relative(Path(__file__)),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-dir", required=True, type=Path)
    parser.add_argument("--edition", default="surau-v0")
    parser.add_argument("--entrypoint", default="book.typ")
    parser.add_argument("--out", default="page-map.json")
    parser.add_argument("--typst", default="typst")
    parser.add_argument(
        "--font-path",
        action="append",
        default=[],
        help="Extra Typst font path; repeatable.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    book_dir = args.book_dir.resolve()
    page_map = build_page_map(
        book_dir,
        args.edition,
        args.entrypoint,
        args.typst,
        args.font_path,
    )

    out_path = book_dir / "editions" / args.edition / args.out
    out_path.write_text(json.dumps(page_map, ensure_ascii=False, indent=2), encoding="utf-8")
    validation = page_map["validation"]
    status = "ok"
    if validation["duplicate_ids"] or validation["missing_passage_ids"] or validation["extra_page_map_ids"]:
        status = "warn"
    print(f"{status}: wrote {out_path}")
    print(
        f"entries={page_map['entry_count']} pages={page_map['page_range']['min']}"
        f"-{page_map['page_range']['max']}"
    )


if __name__ == "__main__":
    main()
