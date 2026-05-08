#!/usr/bin/env python3
"""Generate QA reports for extracted book directories."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ARABIC_INDIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
BIDI_CONTROL_RE = re.compile(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
PASSAGE_REF_RE = re.compile(r'^::passage\{id="([^"]+)"\}\s*$')
ARABIC_DIACRITICS_RE = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]")
ARABIC_LETTER_RE = re.compile(r"[\u0621-\u064a]")

ARTIFACT_PATTERNS = {
    "shamela": "Shamela",
    "contents": "المحتويات",
    "bad_allah_glyph": "᧦",
    "bidi_control": BIDI_CONTROL_RE,
}

CLEAN_ARTIFACT_PATTERNS = {
    "bad_allah_glyph": "᧦",
    "bidi_control": BIDI_CONTROL_RE,
    "legacy_print_marker": re.compile(r"(?:^|[\s،.؛:])-?ط\([،.]?\)?-?"),
    "runtime_error": re.compile(
        r"runtime\s+(?:VBScript|Script)|Microsoft.*error|Subscript.*out\s+of\s+range|/Tafseer/",
        re.IGNORECASE,
    ),
    "star_leftover": re.compile(r"\*"),
    "tatweel_leftover": "ـ",
}

ALLOWED_STATUSES = {
    "raw_extraction",
    "draft_extraction",
    "draft",
    "reviewed",
    "published",
}

ALLOWED_TRANSLATION_STATUSES = {
    "machine_draft",
    "draft",
    "reviewed",
    "published",
}

TRANSLATION_REQUIRED_FIELDS = [
    "id",
    "work_id",
    "lang",
    "source_lang",
    "source_passage_id",
    "source_sequence",
    "section_path",
    "source_citation",
    "translation_status",
    "translation_type",
    "translator",
    "model",
    "text",
]


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    if yaml is not None:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data or {}

    data: dict[str, Any] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith(" ") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()
    return data


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_cleaning_report(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "exists": False,
            "changes": {},
            "profile": {},
            "suspicious_samples": [],
        }
    data = load_json(path)
    data["exists"] = True
    data.setdefault("changes", {})
    data.setdefault("profile", {})
    data.setdefault("suspicious_samples", [])
    return data


def read_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    if not path.exists():
        return rows, [{"line": None, "error": "missing file"}]

    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                errors.append({"line": line_no, "error": str(exc)})
    return rows, errors


def percentile(values: list[int], pct: float) -> int | None:
    if not values:
        return None
    values = sorted(values)
    index = math.ceil((pct / 100) * len(values)) - 1
    index = min(max(index, 0), len(values) - 1)
    return values[index]


def truncate(text: str, limit: int = 150) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def arabic_letter_count(text: str) -> int:
    return len(ARABIC_LETTER_RE.findall(text or ""))


def heading_key(text: str) -> str:
    text = BIDI_CONTROL_RE.sub("", text or "")
    text = ARABIC_DIACRITICS_RE.sub("", text)
    text = text.translate(ARABIC_INDIC_DIGITS)
    return re.sub(r"[^\w\u0621-\u064a]+", "", text, flags=re.UNICODE)


def is_numeric_only(text: str) -> bool:
    compact = text.replace(" ", "").translate(ARABIC_INDIC_DIGITS)
    return bool(re.fullmatch(r"[0-9.()،؛:؟!\-ـ]+", compact))


def count_pattern(text: str, pattern: str | re.Pattern[str]) -> int:
    if isinstance(pattern, str):
        return text.count(pattern)
    return len(pattern.findall(text))


def scan_artifacts(
    text: str,
    patterns: dict[str, str | re.Pattern[str]],
    sample_limit: int = 25,
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    hits: Counter[str] = Counter()
    samples: list[dict[str, Any]] = []

    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line:
            continue
        for name, pattern in patterns.items():
            count = count_pattern(line, pattern)
            if not count:
                continue
            hits[name] += count
            if len(samples) < sample_limit:
                samples.append(
                    {
                        "line": line_no,
                        "pattern": name,
                        "text": truncate(line, 180),
                    }
                )

    return dict(sorted(hits.items())), samples


def artifact_hits(text: str) -> dict[str, int]:
    hits, _ = scan_artifacts(text, ARTIFACT_PATTERNS, sample_limit=0)
    return hits


def first_source_page(row: dict[str, Any]) -> int | None:
    source_blocks = row.get("source_blocks")
    if not isinstance(source_blocks, list):
        return None
    for block in source_blocks:
        if isinstance(block, dict) and isinstance(block.get("pdf_page"), int):
            return block["pdf_page"]
    return None


def parse_manuscript(
    path: Path,
    artifact_patterns: dict[str, str | re.Pattern[str]] = ARTIFACT_PATTERNS,
) -> dict[str, Any]:
    if not path.exists():
        return {
            "exists": False,
            "line_count": 0,
            "headings": [],
            "heading_counts": {},
            "passage_refs": [],
            "artifact_hits": {},
            "artifact_samples": [],
            "skipped_levels": [],
            "adjacent_duplicate_headings": [],
        }

    text = path.read_text(encoding="utf-8")
    artifacts, artifact_samples = scan_artifacts(text, artifact_patterns)
    headings = []
    passage_refs = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        heading_match = HEADING_RE.match(line)
        if heading_match:
            headings.append(
                {
                    "line": line_no,
                    "level": len(heading_match.group(1)),
                    "title": heading_match.group(2),
                }
            )
            continue
        passage_match = PASSAGE_REF_RE.match(line)
        if passage_match:
            passage_refs.append({"line": line_no, "id": passage_match.group(1)})

    heading_counts = Counter(str(item["level"]) for item in headings)
    skipped_levels = []
    previous_level = 0
    for heading in headings:
        level = heading["level"]
        if previous_level and level > previous_level + 1:
            skipped_levels.append(heading)
        previous_level = level

    adjacent_duplicates = []
    for previous, current in zip(headings, headings[1:]):
        if previous["title"] == current["title"] and current["line"] - previous["line"] <= 4:
            adjacent_duplicates.append(current)

    return {
        "exists": True,
        "line_count": len(text.splitlines()),
        "headings": headings,
        "heading_counts": dict(sorted(heading_counts.items(), key=lambda item: int(item[0]))),
        "passage_refs": passage_refs,
        "artifact_hits": artifacts,
        "artifact_samples": artifact_samples,
        "skipped_levels": skipped_levels[:25],
        "adjacent_duplicate_headings": adjacent_duplicates[:25],
    }


def analyze_passages(rows: list[dict[str, Any]], json_errors: list[dict[str, Any]]) -> dict[str, Any]:
    ids = [row.get("id") for row in rows]
    id_counts = Counter(ids)
    duplicate_ids = [pid for pid, count in id_counts.items() if pid and count > 1]

    sequences = [row.get("sequence") for row in rows if isinstance(row.get("sequence"), int)]
    expected_sequences = set(range(1, len(rows) + 1))
    sequence_gaps = sorted(expected_sequences - set(sequences))[:50]
    sequence_duplicates = [seq for seq, count in Counter(sequences).items() if count > 1][:50]

    required_fields = ["id", "work_id", "sequence", "text", "section_path", "source_blocks"]
    missing_required: list[dict[str, Any]] = []
    missing_source_blocks: list[dict[str, Any]] = []
    malformed_source_blocks: list[dict[str, Any]] = []
    missing_review_status: list[str] = []
    missing_lang: list[str] = []
    numeric_only = []
    empty_section_path = []
    artifact_rows = []
    source_pages = []
    lengths = []

    short_passages = []
    long_passages = []

    for row in rows:
        pid = row.get("id", "<missing>")
        text = row.get("text") or ""
        source_page = first_source_page(row)
        lengths.append(len(text))

        missing = [field for field in required_fields if field not in row]
        if missing:
            missing_required.append({"id": pid, "missing": missing})

        if not row.get("review_status"):
            missing_review_status.append(pid)
        if not row.get("lang"):
            missing_lang.append(pid)

        if not row.get("section_path"):
            empty_section_path.append(pid)

        if is_numeric_only(text):
            numeric_only.append({"id": pid, "source_page": source_page, "text": text})

        hits = artifact_hits(text)
        if hits:
            artifact_rows.append(
                {
                    "id": pid,
                    "source_page": source_page,
                    "hits": hits,
                    "text": truncate(text),
                }
            )

        source_blocks = row.get("source_blocks")
        if not source_blocks:
            missing_source_blocks.append({"id": pid})
        elif isinstance(source_blocks, list):
            for block in source_blocks:
                if not isinstance(block, dict):
                    malformed_source_blocks.append({"id": pid, "issue": "source block is not object"})
                    continue
                bbox = block.get("bbox")
                page = block.get("pdf_page")
                if isinstance(page, int):
                    source_pages.append(page)
                if not block.get("block_id") or not isinstance(bbox, list) or len(bbox) != 4:
                    malformed_source_blocks.append(
                        {"id": pid, "issue": "missing block_id or bbox[4]"}
                    )
        else:
            malformed_source_blocks.append({"id": pid, "issue": "source_blocks is not list"})

        if len(text) < 12:
            short_passages.append(
                {
                    "id": pid,
                    "length": len(text),
                    "source_page": source_page,
                    "section_path": row.get("section_path") or [],
                    "text": truncate(text, 80),
                }
            )
        if len(text) > 3000:
            long_passages.append(
                {
                    "id": pid,
                    "length": len(text),
                    "source_page": source_page,
                    "section_path": row.get("section_path") or [],
                    "text": truncate(text, 160),
                }
            )

    by_section = defaultdict(int)
    for row in rows:
        path = row.get("section_path") or []
        by_section[" > ".join(path) if path else "<empty>"] += 1

    top_sections = sorted(by_section.items(), key=lambda item: item[1], reverse=True)[:15]

    return {
        "json_errors": json_errors,
        "count": len(rows),
        "duplicate_ids": duplicate_ids[:50],
        "sequence_gaps": sequence_gaps,
        "sequence_duplicates": sequence_duplicates,
        "missing_required": missing_required[:50],
        "missing_review_status_count": len(missing_review_status),
        "missing_lang_count": len(missing_lang),
        "missing_source_blocks": missing_source_blocks[:50],
        "malformed_source_blocks": malformed_source_blocks[:50],
        "numeric_only": numeric_only[:50],
        "empty_section_path": empty_section_path[:50],
        "artifact_rows": artifact_rows[:50],
        "length_stats": {
            "min": min(lengths) if lengths else None,
            "p50": percentile(lengths, 50),
            "p90": percentile(lengths, 90),
            "p95": percentile(lengths, 95),
            "max": max(lengths) if lengths else None,
            "avg": round(sum(lengths) / len(lengths), 1) if lengths else None,
        },
        "short_passages": short_passages[:50],
        "short_passage_count": len(short_passages),
        "long_passages": sorted(long_passages, key=lambda item: item["length"], reverse=True)[:50],
        "long_passage_count": len(long_passages),
        "source_page_coverage": {
            "min": min(source_pages) if source_pages else None,
            "max": max(source_pages) if source_pages else None,
            "unique_pages": len(set(source_pages)),
        },
        "top_sections": [{"section": section, "count": count} for section, count in top_sections],
    }


def compare_manuscript_to_passages(manuscript: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    manuscript_ids = [item["id"] for item in manuscript["passage_refs"]]
    passage_ids = [row.get("id") for row in rows if row.get("id")]
    manuscript_set = set(manuscript_ids)
    passage_set = set(passage_ids)
    return {
        "manuscript_ref_count": len(manuscript_ids),
        "passage_id_count": len(passage_ids),
        "missing_in_passages": sorted(manuscript_set - passage_set)[:50],
        "missing_in_manuscript": sorted(passage_set - manuscript_set)[:50],
    }


def compare_manuscripts(source: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    source_ids = [item["id"] for item in source["passage_refs"]]
    target_ids = [item["id"] for item in target["passage_refs"]]
    source_set = set(source_ids)
    target_set = set(target_ids)
    return {
        "source_ref_count": len(source_ids),
        "target_ref_count": len(target_ids),
        "missing_in_target": sorted(source_set - target_set)[:50],
        "added_in_target": sorted(target_set - source_set)[:50],
        "source_heading_count": len(source["headings"]),
        "target_heading_count": len(target["headings"]),
    }


def expected_locator(entry: dict[str, Any]) -> dict[str, Any]:
    page = entry.get("page")
    locator = {
        "type": entry.get("locator_type") or "page",
        "label": entry.get("page_label") or (str(page) if page is not None else ""),
    }
    if page is not None:
        locator["page"] = page
    return locator


def expected_public_citation(pid: str, edition: str, ref: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": f"edition_refs.{edition}",
        "edition_id": edition,
        "anchor_id": pid,
        "label": ref["label"],
        "locator": ref["locator"],
    }


def analyze_page_maps(
    book_dir: Path,
    rows: list[dict[str, Any]],
    book: dict[str, Any],
) -> list[dict[str, Any]]:
    passage_ids = [row.get("id") for row in rows if row.get("id")]
    passage_set = set(passage_ids)
    results = []

    for path in sorted((book_dir / "editions").glob("*/page-map.json")):
        data = load_json(path)
        edition = path.parent.name
        entries = data.get("entries") or []
        ids = [item.get("id") for item in entries if isinstance(item, dict) and item.get("id")]
        id_counts = Counter(ids)
        entry_by_id = {
            item["id"]: item
            for item in entries
            if isinstance(item, dict) and item.get("id")
        }
        pages = [
            item.get("page")
            for item in entries
            if isinstance(item, dict) and isinstance(item.get("page"), int)
        ]
        duplicate_ids = sorted(pid for pid, count in id_counts.items() if count > 1)
        validation = {
            "duplicate_ids": duplicate_ids[:50],
            "missing_passage_ids": sorted(passage_set - set(ids))[:50],
            "extra_page_map_ids": sorted(set(ids) - passage_set)[:50],
        }
        missing_edition_refs = []
        mismatched_edition_refs = []
        missing_public_citations = []
        mismatched_public_citations = []
        present_count = 0
        public_citation_count = 0
        default_edition = book.get("default_edition")
        for row in rows:
            pid = row.get("id")
            if pid not in entry_by_id:
                continue
            edition_refs = row.get("edition_refs") or {}
            ref = edition_refs.get(edition) if isinstance(edition_refs, dict) else None
            if not isinstance(ref, dict):
                missing_edition_refs.append(pid)
                continue

            present_count += 1
            entry = entry_by_id[pid]
            expected = {
                "page": entry.get("page"),
                "physical_page": entry.get("physical_page"),
                "label": entry.get("citation"),
                "page_semantics": data.get("page_semantics") or "start_page",
                "locator": expected_locator(entry),
                "viewer": {"pdf_page": entry.get("physical_page")},
            }
            mismatches = {
                key: {"expected": value, "actual": ref.get(key)}
                for key, value in expected.items()
                if value is not None and value != {"pdf_page": None} and ref.get(key) != value
            }
            if mismatches:
                mismatched_edition_refs.append({"id": pid, "mismatches": mismatches})

            if edition == default_edition:
                citation = row.get("citation")
                if not isinstance(citation, dict):
                    missing_public_citations.append(pid)
                    continue

                public_citation_count += 1
                expected_citation = expected_public_citation(pid, edition, ref)
                if citation != expected_citation:
                    mismatched_public_citations.append(
                        {
                            "id": pid,
                            "expected": expected_citation,
                            "actual": citation,
                        }
                    )

        results.append(
            {
                "edition": edition,
                "path": str(path),
                "entry_count": len(entries),
                "passage_count": len(passage_ids),
                "page_semantics": data.get("page_semantics"),
                "page_range": {
                    "min": min(pages) if pages else None,
                    "max": max(pages) if pages else None,
                    "unique": len(set(pages)),
                },
                "validation": validation,
                "edition_refs": {
                    "present_count": present_count,
                    "missing": missing_edition_refs[:50],
                    "mismatched": mismatched_edition_refs[:50],
                },
                "public_citations": {
                    "is_default_edition": edition == default_edition,
                    "present_count": public_citation_count,
                    "missing": missing_public_citations[:50],
                    "mismatched": mismatched_public_citations[:50],
                },
            }
        )

    return results


def analyze_translations(book_dir: Path, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_ids = [row.get("id") for row in rows if row.get("id")]
    source_set = set(source_ids)
    source_by_id = {row.get("id"): row for row in rows if row.get("id")}
    source_citations = {
        row.get("id")
        for row in rows
        if row.get("id") and isinstance(row.get("citation"), dict)
    }
    results = []

    translations_dir = book_dir / "translations"
    if not translations_dir.exists():
        return results

    for path in sorted(translations_dir.glob("*/passages.jsonl")):
        lang = path.parent.name
        translation_rows, json_errors = read_jsonl(path)
        ids = [row.get("id") for row in translation_rows if row.get("id")]
        source_refs = [
            row.get("source_passage_id")
            for row in translation_rows
            if row.get("source_passage_id")
        ]
        duplicate_ids = sorted(pid for pid, count in Counter(ids).items() if count > 1)
        duplicate_source_refs = sorted(
            pid for pid, count in Counter(source_refs).items() if count > 1
        )
        missing_source_passage_id = [
            row.get("id", f"row-{index}")
            for index, row in enumerate(translation_rows, start=1)
            if not row.get("source_passage_id")
        ]
        invalid_source_passage_id = sorted(set(source_refs) - source_set)
        missing_lang = [
            row.get("id", f"row-{index}")
            for index, row in enumerate(translation_rows, start=1)
            if row.get("lang") != lang
        ]
        missing_text = [
            row.get("id", f"row-{index}")
            for index, row in enumerate(translation_rows, start=1)
            if not str(row.get("text") or "").strip()
        ]
        missing_status = [
            row.get("id", f"row-{index}")
            for index, row in enumerate(translation_rows, start=1)
            if not row.get("translation_status")
        ]
        source_citation_missing = sorted(set(source_refs) - source_citations)
        missing_metadata = []
        invalid_translation_status = []
        id_shape_mismatches = []
        source_sequence_mismatches = []
        source_citation_mismatches = []
        arabic_leak_rows = []
        length_ratio_outliers = []

        for index, row in enumerate(translation_rows, start=1):
            row_id = row.get("id", f"row-{index}")
            source_id = row.get("source_passage_id")
            text = str(row.get("text") or "")
            missing_fields = [
                field
                for field in TRANSLATION_REQUIRED_FIELDS
                if field not in row or row.get(field) in (None, "")
            ]
            if missing_fields:
                missing_metadata.append({"id": row_id, "missing": missing_fields})

            status = row.get("translation_status")
            if status and status not in ALLOWED_TRANSLATION_STATUSES:
                invalid_translation_status.append({"id": row_id, "status": status})

            if source_id and row_id != f"{source_id}.{lang}":
                id_shape_mismatches.append(
                    {"id": row_id, "expected": f"{source_id}.{lang}"}
                )

            source_row = source_by_id.get(source_id)
            if source_row:
                if row.get("source_sequence") != source_row.get("sequence"):
                    source_sequence_mismatches.append(
                        {
                            "id": row_id,
                            "source_passage_id": source_id,
                            "expected": source_row.get("sequence"),
                            "actual": row.get("source_sequence"),
                        }
                    )
                if row.get("source_citation") != source_row.get("citation"):
                    source_citation_mismatches.append(
                        {
                            "id": row_id,
                            "source_passage_id": source_id,
                            "expected": source_row.get("citation"),
                            "actual": row.get("source_citation"),
                        }
                    )

                source_text = str(source_row.get("text") or "")
                source_len = len(source_text)
                target_len = len(text)
                ratio = target_len / max(source_len, 1)
                if (source_len >= 80 and (ratio < 0.25 or ratio > 4.0)) or (
                    source_len < 80 and target_len > 400
                ):
                    length_ratio_outliers.append(
                        {
                            "id": row_id,
                            "source_passage_id": source_id,
                            "source_length": source_len,
                            "target_length": target_len,
                            "ratio": round(ratio, 2),
                            "text": truncate(text, 160),
                        }
                    )

            if lang != "ar":
                leak_count = arabic_letter_count(text)
                if leak_count:
                    arabic_leak_rows.append(
                        {
                            "id": row_id,
                            "source_passage_id": source_id,
                            "arabic_letters": leak_count,
                            "text": truncate(text, 160),
                        }
                    )

        results.append(
            {
                "lang": lang,
                "path": str(path),
                "metadata": load_yaml(path.parent / "translation.yml"),
                "count": len(translation_rows),
                "source_coverage": {
                    "translated": len(set(source_refs) & source_set),
                    "source_total": len(source_set),
                },
                "json_errors": json_errors,
                "duplicate_ids": duplicate_ids[:50],
                "duplicate_source_passage_ids": duplicate_source_refs[:50],
                "missing_source_passage_id": missing_source_passage_id[:50],
                "invalid_source_passage_id": invalid_source_passage_id[:50],
                "missing_lang": missing_lang[:50],
                "missing_text": missing_text[:50],
                "missing_translation_status": missing_status[:50],
                "source_citation_missing": source_citation_missing[:50],
                "missing_metadata": missing_metadata[:50],
                "invalid_translation_status": invalid_translation_status[:50],
                "id_shape_mismatches": id_shape_mismatches[:50],
                "source_sequence_mismatches": source_sequence_mismatches[:50],
                "source_citation_mismatches": source_citation_mismatches[:50],
                "arabic_leak_rows": arabic_leak_rows[:50],
                "length_ratio_outliers": length_ratio_outliers[:50],
            }
        )

    return results


def analyze_toc(book_dir: Path, manuscript: dict[str, Any]) -> dict[str, Any]:
    raw = load_json(book_dir / "raw" / "raw.json")
    toc_entries = raw.get("toc") or []
    if not toc_entries:
        return {
            "exists": bool(raw),
            "count": 0,
            "matched": 0,
            "unmatched_count": 0,
            "unmatched": [],
            "heading_counts": {},
            "source_heading_counts": {},
        }

    manuscript_heading_counts = Counter(heading_key(item["title"]) for item in manuscript["headings"])
    unmatched = []
    matched = 0
    for entry in toc_entries:
        key = heading_key(entry.get("title", ""))
        if key and manuscript_heading_counts[key] > 0:
            manuscript_heading_counts[key] -= 1
            matched += 1
            continue
        unmatched.append(
            {
                "index": entry.get("index"),
                "page": entry.get("page"),
                "source_level": entry.get("source_level", entry.get("level")),
                "level": entry.get("level"),
                "title": entry.get("title"),
            }
        )

    heading_counts = Counter(str(item.get("level")) for item in toc_entries if item.get("level"))
    source_heading_counts = Counter(
        str(item.get("source_level", item.get("level"))) for item in toc_entries if item.get("level")
    )

    return {
        "exists": True,
        "count": len(toc_entries),
        "matched": matched,
        "unmatched_count": len(unmatched),
        "unmatched": unmatched[:50],
        "heading_counts": dict(sorted(heading_counts.items(), key=lambda item: int(item[0]))),
        "source_heading_counts": dict(
            sorted(source_heading_counts.items(), key=lambda item: int(item[0]))
        ),
    }


def collect_problem_pages(passages: dict[str, Any], toc: dict[str, Any]) -> list[dict[str, Any]]:
    page_reasons: dict[int, Counter[str]] = defaultdict(Counter)

    for item in passages["short_passages"]:
        if isinstance(item.get("source_page"), int):
            page_reasons[item["source_page"]]["short_passage"] += 1
    for item in passages["long_passages"]:
        if isinstance(item.get("source_page"), int):
            page_reasons[item["source_page"]]["long_passage"] += 1
    for item in passages["numeric_only"]:
        if isinstance(item.get("source_page"), int):
            page_reasons[item["source_page"]]["numeric_only"] += 1
    for item in passages["artifact_rows"]:
        if isinstance(item.get("source_page"), int):
            page_reasons[item["source_page"]]["artifact"] += 1
    for item in toc["unmatched"]:
        if isinstance(item.get("page"), int):
            page_reasons[item["page"]]["toc_not_found"] += 1

    pages = [
        {
            "page": page,
            "score": sum(reasons.values()),
            "reasons": dict(sorted(reasons.items())),
        }
        for page, reasons in page_reasons.items()
    ]
    return sorted(pages, key=lambda item: (-item["score"], item["page"]))[:25]


def build_warnings(
    book: dict[str, Any],
    manuscript: dict[str, Any],
    clean_manuscript: dict[str, Any],
    passages: dict[str, Any],
    page_maps: list[dict[str, Any]],
    translations: list[dict[str, Any]],
    clean_consistency: dict[str, Any],
    raw_clean_consistency: dict[str, Any],
    cleaning_report: dict[str, Any],
    toc: dict[str, Any],
) -> list[dict[str, str]]:
    warnings = []
    status = book.get("status")
    if status and status not in ALLOWED_STATUSES:
        warnings.append({"severity": "warn", "message": f"Unknown book status: {status}"})
    if not book.get("schema_version"):
        warnings.append({"severity": "warn", "message": "book.yml has no schema_version"})
    if not manuscript["exists"]:
        warnings.append({"severity": "fail", "message": "Missing manuscript.md"})
    if passages["json_errors"]:
        warnings.append({"severity": "fail", "message": "passages.jsonl has JSON errors"})
    if passages["duplicate_ids"]:
        warnings.append({"severity": "fail", "message": "Duplicate passage IDs found"})
    if passages["sequence_gaps"] or passages["sequence_duplicates"]:
        warnings.append({"severity": "warn", "message": "Passage sequence is not contiguous"})
    if passages["numeric_only"]:
        warnings.append({"severity": "warn", "message": "Numeric-only passages remain"})
    if manuscript["artifact_hits"] or passages["artifact_rows"]:
        warnings.append({"severity": "warn", "message": "Extraction artifacts remain"})
    if not clean_manuscript["exists"]:
        warnings.append(
            {
                "severity": "warn",
                "message": "Missing clean/manuscript.md; run cleaner before Typst layout",
            }
        )
    elif clean_manuscript["artifact_hits"]:
        warnings.append(
            {
                "severity": "warn",
                "message": "Clean manuscript still has pre-layout artifacts",
            }
        )
    if not cleaning_report["exists"]:
        warnings.append(
            {
                "severity": "warn",
                "message": "Missing clean/cleaning-report.json",
            }
        )
    if clean_manuscript["exists"] and (
        clean_consistency["missing_in_passages"] or clean_consistency["missing_in_manuscript"]
    ):
        warnings.append(
            {
                "severity": "fail",
                "message": "Clean manuscript passage IDs do not match passages.jsonl",
            }
        )
    if clean_manuscript["exists"] and (
        raw_clean_consistency["missing_in_target"] or raw_clean_consistency["added_in_target"]
    ):
        warnings.append(
            {
                "severity": "fail",
                "message": "Clean manuscript passage IDs drifted from manuscript.md",
            }
        )
    for page_map in page_maps:
        validation = page_map["validation"]
        edition_refs = page_map.get("edition_refs") or {}
        public_citations = page_map.get("public_citations") or {}
        if (
            validation["duplicate_ids"]
            or validation["missing_passage_ids"]
            or validation["extra_page_map_ids"]
        ):
            warnings.append(
                {
                    "severity": "fail",
                    "message": f"{page_map['edition']} page-map IDs do not match passages.jsonl",
                }
            )
        if edition_refs.get("missing") or edition_refs.get("mismatched"):
            warnings.append(
                {
                    "severity": "fail",
                    "message": f"{page_map['edition']} edition_refs are not synced with page-map.json",
                }
            )
        if public_citations.get("missing") or public_citations.get("mismatched"):
            warnings.append(
                {
                    "severity": "fail",
                    "message": f"{page_map['edition']} public citations are not synced with edition_refs",
                }
            )
    for translation in translations:
        if translation["json_errors"]:
            warnings.append(
                {
                    "severity": "fail",
                    "message": f"{translation['lang']} translation has JSONL errors",
                }
            )
        if translation["duplicate_ids"] or translation["duplicate_source_passage_ids"]:
            warnings.append(
                {
                    "severity": "fail",
                    "message": f"{translation['lang']} translation has duplicate IDs",
                }
            )
        if translation["missing_source_passage_id"] or translation["invalid_source_passage_id"]:
            warnings.append(
                {
                    "severity": "fail",
                    "message": f"{translation['lang']} translation source_passage_id is invalid",
                }
            )
        if (
            translation["missing_lang"]
            or translation["missing_text"]
            or translation["missing_translation_status"]
            or translation["missing_metadata"]
            or translation["invalid_translation_status"]
        ):
            warnings.append(
                {
                    "severity": "warn",
                    "message": f"{translation['lang']} translation has incomplete rows",
                }
            )
        if translation["source_citation_missing"]:
            warnings.append(
                {
                    "severity": "warn",
                    "message": f"{translation['lang']} translation points to sources without public citation",
                }
            )
        if translation["source_citation_mismatches"]:
            warnings.append(
                {
                    "severity": "fail",
                    "message": f"{translation['lang']} translation source citations drifted from canonical passages",
                }
            )
        if translation["source_sequence_mismatches"] or translation["id_shape_mismatches"]:
            warnings.append(
                {
                    "severity": "warn",
                    "message": f"{translation['lang']} translation anchor metadata needs review",
                }
            )
        if translation["arabic_leak_rows"]:
            warnings.append(
                {
                    "severity": "warn",
                    "message": f"{translation['lang']} translation still contains Arabic-script text",
                }
            )
        if translation["length_ratio_outliers"]:
            warnings.append(
                {
                    "severity": "warn",
                    "message": f"{translation['lang']} translation has unusual source/target length ratios",
                }
            )
    if passages["missing_source_blocks"] or passages["malformed_source_blocks"]:
        warnings.append({"severity": "fail", "message": "Source block provenance is incomplete"})
    if passages["missing_review_status_count"]:
        warnings.append(
            {
                "severity": "warn",
                "message": f"{passages['missing_review_status_count']} passages missing review_status",
            }
        )
    if passages["missing_lang_count"]:
        warnings.append(
            {
                "severity": "warn",
                "message": f"{passages['missing_lang_count']} passages missing lang",
            }
        )

    heading_counts = {int(k): v for k, v in manuscript["heading_counts"].items()}
    if heading_counts.get(1, 0) > 40 and heading_counts.get(2, 0) < 5:
        warnings.append(
            {
                "severity": "info",
                "message": "Heading outline looks flat; this book may need custom H1/H2 rules",
            }
        )
    if heading_counts.get(2, 0) > 1000 and heading_counts.get(3, 0) > 1000:
        warnings.append(
            {
                "severity": "info",
                "message": "Very detailed outline; consider a specialized mode such as Quran/tafsir",
            }
        )
    if manuscript["adjacent_duplicate_headings"]:
        warnings.append({"severity": "warn", "message": "Adjacent duplicate headings found"})
    if toc["unmatched_count"]:
        ratio = toc["unmatched_count"] / max(toc["count"], 1)
        severity = "warn" if toc["unmatched_count"] > 5 and ratio > 0.03 else "info"
        warnings.append(
            {
                "severity": severity,
                "message": f"{toc['unmatched_count']} TOC entries were not found in manuscript headings",
            }
        )
    if passages["long_passage_count"]:
        warnings.append(
            {
                "severity": "info",
                "message": f"{passages['long_passage_count']} passages longer than 3000 chars",
            }
        )
    return warnings


def analyze_book(book_dir: Path) -> dict[str, Any]:
    book = load_yaml(book_dir / "book.yml")
    manuscript = parse_manuscript(book_dir / "manuscript.md")
    clean_manuscript = parse_manuscript(
        book_dir / "clean" / "manuscript.md",
        CLEAN_ARTIFACT_PATTERNS,
    )
    cleaning_report = load_cleaning_report(book_dir / "clean" / "cleaning-report.json")
    rows, errors = read_jsonl(book_dir / "passages.jsonl")
    passages = analyze_passages(rows, errors)
    page_maps = analyze_page_maps(book_dir, rows, book)
    translations = analyze_translations(book_dir, rows)
    consistency = compare_manuscript_to_passages(manuscript, rows)
    clean_consistency = compare_manuscript_to_passages(clean_manuscript, rows)
    raw_clean_consistency = compare_manuscripts(manuscript, clean_manuscript)
    toc = analyze_toc(book_dir, manuscript)
    problem_pages = collect_problem_pages(passages, toc)
    warnings = build_warnings(
        book,
        manuscript,
        clean_manuscript,
        passages,
        page_maps,
        translations,
        clean_consistency,
        raw_clean_consistency,
        cleaning_report,
        toc,
    )

    report = {
        "book_dir": str(book_dir),
        "book": book,
        "manuscript": manuscript,
        "clean_manuscript": clean_manuscript,
        "cleaning_report": cleaning_report,
        "passages": passages,
        "page_maps": page_maps,
        "translations": translations,
        "consistency": consistency,
        "clean_consistency": clean_consistency,
        "raw_clean_consistency": raw_clean_consistency,
        "toc": toc,
        "problem_pages": problem_pages,
        "warnings": warnings,
    }
    if any(item["severity"] == "fail" for item in warnings):
        report["status"] = "fail"
    elif any(item["severity"] == "warn" for item in warnings):
        report["status"] = "warn"
    else:
        report["status"] = "ok"
    return report


def markdown_table(rows: list[list[Any]], headers: list[str]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(item) for item in row) + " |")
    return "\n".join(lines)


def render_samples(title: str, samples: list[dict[str, Any]]) -> list[str]:
    lines = [f"## {title}", ""]
    if not samples:
        lines.append("_None._")
        lines.append("")
        return lines
    for item in samples[:15]:
        path = " > ".join(item.get("section_path") or [])
        suffix = f" ({item.get('length')} chars)" if item.get("length") is not None else ""
        page = f" p.{item['source_page']}" if isinstance(item.get("source_page"), int) else ""
        lines.append(f"- `{item.get('id')}`{page}{suffix}: {truncate(item.get('text', ''))}")
        if path:
            lines.append(f"  Section: {path}")
    lines.append("")
    return lines


def render_line_samples(title: str, samples: list[dict[str, Any]]) -> list[str]:
    lines = [f"## {title}", ""]
    if not samples:
        lines.append("_None._")
        lines.append("")
        return lines
    for item in samples[:15]:
        passage = f" `{item['passage_id']}`" if item.get("passage_id") else ""
        pattern = item.get("pattern", "unknown")
        lines.append(
            f"- line {item.get('line')}{passage} `{pattern}`: "
            f"{truncate(item.get('text', ''), 180)}"
        )
    lines.append("")
    return lines


def render_book_markdown(report: dict[str, Any]) -> str:
    book = report["book"]
    manuscript = report["manuscript"]
    clean_manuscript = report["clean_manuscript"]
    cleaning_report = report["cleaning_report"]
    passages = report["passages"]
    page_maps = report["page_maps"]
    translations = report["translations"]
    consistency = report["consistency"]
    clean_consistency = report["clean_consistency"]
    raw_clean_consistency = report["raw_clean_consistency"]
    toc = report["toc"]
    warnings = report["warnings"]
    clean_profile = cleaning_report.get("profile") or {}

    title = book.get("title_id") or book.get("title_ar") or Path(report["book_dir"]).name
    lines = [
        f"# QA Report: {title}",
        "",
        f"- Status: `{report['status']}`",
        f"- Book ID: `{book.get('id', Path(report['book_dir']).name)}`",
        f"- Schema: `{book.get('schema_version', 'missing')}`",
        f"- Source PDF: `{(book.get('source') or {}).get('pdf', 'unknown')}`",
        f"- Source pages: `{(book.get('source') or {}).get('pages', 'unknown')}`",
        "",
        "## Summary",
        "",
        markdown_table(
            [
                ["Passages", passages["count"]],
                ["Manuscript refs", consistency["manuscript_ref_count"]],
                ["Headings", len(manuscript["headings"])],
                ["Heading counts", json.dumps(manuscript["heading_counts"], ensure_ascii=False)],
                ["Clean refs", clean_consistency["manuscript_ref_count"]],
                ["Clean headings", len(clean_manuscript["headings"])],
                [
                    "Clean artifacts",
                    json.dumps(clean_manuscript["artifact_hits"], ensure_ascii=False),
                ],
                ["TOC entries", toc["count"]],
                ["TOC not found", toc["unmatched_count"]],
                ["Source pages covered", passages["source_page_coverage"]["unique_pages"]],
                ["Length stats", json.dumps(passages["length_stats"], ensure_ascii=False)],
            ],
            ["Metric", "Value"],
        ),
        "",
        "## Warnings",
        "",
    ]

    if warnings:
        for item in warnings:
            lines.append(f"- `{item['severity']}` {item['message']}")
    else:
        lines.append("_None._")
    lines.append("")

    lines.extend(
        [
            "## Consistency",
            "",
            markdown_table(
                [
                    ["Missing in passages", len(consistency["missing_in_passages"])],
                    ["Missing in manuscript", len(consistency["missing_in_manuscript"])],
                    ["Duplicate IDs", len(passages["duplicate_ids"])],
                    ["Sequence gaps", len(passages["sequence_gaps"])],
                    ["JSON errors", len(passages["json_errors"])],
                    ["Numeric-only passages", len(passages["numeric_only"])],
                    ["Missing source blocks", len(passages["missing_source_blocks"])],
                    ["Malformed source blocks", len(passages["malformed_source_blocks"])],
                    ["Artifact rows", len(passages["artifact_rows"])],
                    ["TOC entries not found", toc["unmatched_count"]],
                ],
                ["Check", "Count"],
            ),
            "",
            "## Clean Manuscript",
            "",
            markdown_table(
                [
                    ["Exists", clean_manuscript["exists"]],
                    ["Profile", clean_profile.get("name", "missing")],
                    ["Profile rules", json.dumps(clean_profile.get("rules", []), ensure_ascii=False)],
                    ["Clean refs", clean_consistency["manuscript_ref_count"]],
                    ["Clean missing in passages", len(clean_consistency["missing_in_passages"])],
                    ["Passages missing in clean", len(clean_consistency["missing_in_manuscript"])],
                    ["Missing from raw->clean", len(raw_clean_consistency["missing_in_target"])],
                    ["Added in raw->clean", len(raw_clean_consistency["added_in_target"])],
                    ["Clean headings", len(clean_manuscript["headings"])],
                    [
                        "Clean heading counts",
                        json.dumps(clean_manuscript["heading_counts"], ensure_ascii=False),
                    ],
                    [
                        "Clean artifacts",
                        json.dumps(clean_manuscript["artifact_hits"], ensure_ascii=False),
                    ],
                    [
                        "Cleaning changes",
                        json.dumps(cleaning_report.get("changes", {}), ensure_ascii=False),
                    ],
                    [
                        "Cleaning suspicious samples",
                        len(cleaning_report.get("suspicious_samples", [])),
                    ],
                ],
                ["Check", "Value"],
            ),
            "",
            "## Top Sections",
            "",
        ]
    )
    lines.append(
        markdown_table(
            [[item["section"], item["count"]] for item in passages["top_sections"]],
            ["Section", "Passages"],
        )
    )
    lines.append("")

    lines.extend(render_samples("Short Passages", passages["short_passages"]))
    lines.extend(render_samples("Long Passages", passages["long_passages"]))
    lines.extend(render_line_samples("Clean Artifact Samples", clean_manuscript["artifact_samples"]))
    lines.extend(
        render_line_samples(
            "Cleaning Report Suspicious Samples",
            cleaning_report.get("suspicious_samples", []),
        )
    )

    if page_maps:
        lines.append("## Edition Page Maps")
        lines.append("")
        lines.append(
            markdown_table(
                [
                    [
                        item["edition"],
                        item["entry_count"],
                        item["page_range"]["min"],
                        item["page_range"]["max"],
                        item["page_range"]["unique"],
                        item["edition_refs"]["present_count"],
                        item["public_citations"]["present_count"],
                        len(item["validation"]["missing_passage_ids"]),
                        len(item["validation"]["extra_page_map_ids"]),
                        len(item["validation"]["duplicate_ids"]),
                        len(item["edition_refs"]["missing"]),
                        len(item["edition_refs"]["mismatched"]),
                        len(item["public_citations"]["missing"]),
                        len(item["public_citations"]["mismatched"]),
                    ]
                    for item in page_maps
                ],
                [
                    "Edition",
                    "Entries",
                    "First Page",
                    "Last Page",
                    "Unique Pages",
                    "Synced Refs",
                    "Public Citations",
                    "Missing IDs",
                    "Extra IDs",
                    "Duplicate IDs",
                    "Missing Refs",
                    "Mismatched Refs",
                    "Missing Citations",
                    "Mismatched Citations",
                ],
            )
        )
        lines.append("")

    if translations:
        lines.append("## Translations")
        lines.append("")
        lines.append(
            markdown_table(
                [
                    [
                        item["lang"],
                        item["count"],
                        item["source_coverage"]["translated"],
                        item["source_coverage"]["source_total"],
                        len(item["invalid_source_passage_id"]),
                        len(item["duplicate_ids"]),
                        len(item["missing_text"]),
                        len(item["source_citation_missing"]),
                        len(item["missing_metadata"]),
                        len(item["invalid_translation_status"]),
                        len(item["arabic_leak_rows"]),
                        len(item["length_ratio_outliers"]),
                        len(item["source_citation_mismatches"]),
                    ]
                    for item in translations
                ],
                [
                    "Lang",
                    "Rows",
                    "Sources Covered",
                    "Source Total",
                    "Invalid Sources",
                    "Duplicate IDs",
                    "Missing Text",
                    "Sources Without Citation",
                    "Missing Metadata",
                    "Bad Status",
                    "Arabic Leak",
                    "Ratio Outliers",
                    "Citation Drift",
                ],
            )
        )
        lines.append("")

        quality_samples = []
        for item in translations:
            lang = item["lang"]
            for sample in item["arabic_leak_rows"][:5]:
                quality_samples.append(
                    {
                        "lang": lang,
                        "kind": "arabic_leak",
                        "id": sample.get("id"),
                        "detail": f"{sample.get('arabic_letters')} Arabic letters",
                        "text": sample.get("text", ""),
                    }
                )
            for sample in item["length_ratio_outliers"][:5]:
                quality_samples.append(
                    {
                        "lang": lang,
                        "kind": "length_ratio",
                        "id": sample.get("id"),
                        "detail": (
                            f"{sample.get('target_length')}/{sample.get('source_length')} "
                            f"ratio={sample.get('ratio')}"
                        ),
                        "text": sample.get("text", ""),
                    }
                )
            for sample in item["source_citation_mismatches"][:5]:
                quality_samples.append(
                    {
                        "lang": lang,
                        "kind": "citation_drift",
                        "id": sample.get("id"),
                        "detail": sample.get("source_passage_id"),
                        "text": json.dumps(sample.get("actual"), ensure_ascii=False),
                    }
                )
        if quality_samples:
            lines.append("## Translation Quality Samples")
            lines.append("")
            for sample in quality_samples[:20]:
                lines.append(
                    f"- `{sample['lang']}` `{sample['kind']}` `{sample['id']}` "
                    f"{sample['detail']}: {truncate(sample.get('text', ''), 180)}"
                )
            lines.append("")

    if report["problem_pages"]:
        lines.append("## Problem Pages")
        lines.append("")
        for item in report["problem_pages"][:15]:
            lines.append(
                f"- p.{item['page']} score={item['score']}: "
                f"{json.dumps(item['reasons'], ensure_ascii=False)}"
            )
        lines.append("")

    if toc["unmatched"]:
        lines.append("## TOC Entries Not Found")
        lines.append("")
        for item in toc["unmatched"][:15]:
            lines.append(
                f"- index {item.get('index')} p.{item.get('page')}: "
                f"source H{item.get('source_level')} -> H{item.get('level')} {item.get('title')}"
            )
        lines.append("")

    if manuscript["skipped_levels"]:
        lines.append("## Skipped Heading Levels")
        lines.append("")
        for item in manuscript["skipped_levels"][:15]:
            lines.append(f"- line {item['line']}: H{item['level']} {item['title']}")
        lines.append("")

    if manuscript["adjacent_duplicate_headings"]:
        lines.append("## Adjacent Duplicate Headings")
        lines.append("")
        for item in manuscript["adjacent_duplicate_headings"][:15]:
            lines.append(f"- line {item['line']}: H{item['level']} {item['title']}")
        lines.append("")

    if passages["artifact_rows"]:
        lines.append("## Artifact Rows")
        lines.append("")
        for item in passages["artifact_rows"][:15]:
            lines.append(f"- `{item['id']}` {item['hits']}: {item['text']}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_index(reports: list[dict[str, Any]]) -> str:
    rows = []
    for report in reports:
        book = report["book"]
        passages = report["passages"]
        manuscript = report["manuscript"]
        clean_manuscript = report["clean_manuscript"]
        cleaning_report = report["cleaning_report"]
        page_maps = report["page_maps"]
        translations = report["translations"]
        synced_refs = sum(
            item.get("edition_refs", {}).get("present_count", 0)
            for item in page_maps
        )
        public_citations = sum(
            item.get("public_citations", {}).get("present_count", 0)
            for item in page_maps
        )
        rows.append(
            [
                report["status"],
                book.get("id", Path(report["book_dir"]).name),
                passages["count"],
                len(manuscript["headings"]),
                len(clean_manuscript["headings"]),
                sum(clean_manuscript["artifact_hits"].values()),
                len(cleaning_report.get("suspicious_samples", [])),
                len(page_maps),
                synced_refs,
                public_citations,
                sum(item["count"] for item in translations),
                report["toc"]["unmatched_count"],
                passages["source_page_coverage"]["unique_pages"],
                len(report["warnings"]),
            ]
        )
    lines = [
        "# QA Index",
        "",
        markdown_table(
            rows,
            [
                "Status",
                "Book",
                "Passages",
                "Raw H",
                "Clean H",
                "Clean Artifacts",
                "Clean Suspicious",
                "Page Maps",
                "Page Refs",
                "Citations",
                "Translations",
                "TOC Missing",
                "Source Pages",
                "Findings",
            ],
        ),
        "",
    ]
    return "\n".join(lines)


def discover_book_dirs(books_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in books_dir.iterdir()
        if path.is_dir() and (path / "book.yml").exists()
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--books-dir", type=Path, default=Path("books"))
    parser.add_argument("--out", type=Path, default=Path("reports/qa"))
    parser.add_argument("--book", action="append", help="Book directory name to include; repeatable.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    book_dirs = discover_book_dirs(args.books_dir)
    if args.book:
        wanted = set(args.book)
        book_dirs = [path for path in book_dirs if path.name in wanted or str(path) in wanted]

    args.out.mkdir(parents=True, exist_ok=True)
    reports = []
    for book_dir in book_dirs:
        report = analyze_book(book_dir)
        reports.append(report)
        book_id = report["book"].get("id") or book_dir.name
        (args.out / f"{book_id}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (args.out / f"{book_id}.md").write_text(
            render_book_markdown(report),
            encoding="utf-8",
        )
        print(f"{report['status']}: {book_id}")

    (args.out / "index.md").write_text(render_index(reports), encoding="utf-8")
    (args.out / "index.json").write_text(
        json.dumps(
            [
                {
                    "book_id": report["book"].get("id") or Path(report["book_dir"]).name,
                    "status": report["status"],
                    "warnings": report["warnings"],
                    "passages": report["passages"]["count"],
                    "headings": len(report["manuscript"]["headings"]),
                    "clean_headings": len(report["clean_manuscript"]["headings"]),
                    "clean_artifacts": report["clean_manuscript"]["artifact_hits"],
                    "clean_suspicious_count": len(
                        report["cleaning_report"].get("suspicious_samples", [])
                    ),
                    "page_maps": report["page_maps"],
                    "public_citations": sum(
                        item.get("public_citations", {}).get("present_count", 0)
                        for item in report["page_maps"]
                    ),
                    "translations": report["translations"],
                    "toc_unmatched": report["toc"]["unmatched_count"],
                    "problem_pages": report["problem_pages"],
                }
                for report in reports
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
