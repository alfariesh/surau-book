#!/usr/bin/env python3
"""Run lightweight QA checks for a generated Typst PDF edition."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


LATIN_RE = re.compile(r"[A-Za-z]")
TECHNICAL_TERM_RE = re.compile(r"\b(?:API|RAG|Graph|PDF|Typst|QR|role|matn|pipeline)\b")
QR_WIDTH_RE = re.compile(r"qrcode\([\s\S]{0,500}?width:\s*([0-9.]+)mm")


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=False)


def parse_pdfinfo(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()
    if "Pages" in data:
        try:
            data["Pages"] = int(data["Pages"])
        except ValueError:
            pass
    return data


def extract_text(pdf: Path, page: int | None = None) -> str:
    command = ["pdftotext"]
    if page is not None:
        command.extend(["-f", str(page), "-l", str(page)])
    command.extend([str(pdf), "-"])
    result = run(command)
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or result.stdout.strip())
    return result.stdout


def analyze_source_typst(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {"exists": False, "qr_widths_mm": [], "oversized_qr_widths_mm": []}
    text = path.read_text(encoding="utf-8")
    widths = [float(match.group(1)) for match in QR_WIDTH_RE.finditer(text)]
    return {
        "exists": True,
        "path": str(path),
        "qr_widths_mm": widths,
        "oversized_qr_widths_mm": [width for width in widths if width > 30],
    }


def analyze_pdf(pdf: Path, source_typst: Path | None = None) -> dict[str, Any]:
    if not pdf.exists():
        raise SystemExit(f"PDF not found: {pdf}")

    pdfinfo_result = run(["pdfinfo", str(pdf)])
    if pdfinfo_result.returncode != 0:
        raise SystemExit(pdfinfo_result.stderr.strip() or pdfinfo_result.stdout.strip())
    info = parse_pdfinfo(pdfinfo_result.stdout)
    text = extract_text(pdf)

    latin_lines = [
        {"line": line_no, "text": line.strip()}
        for line_no, line in enumerate(text.splitlines(), start=1)
        if LATIN_RE.search(line)
    ]
    technical_lines = [
        {"line": line_no, "text": line.strip()}
        for line_no, line in enumerate(text.splitlines(), start=1)
        if TECHNICAL_TERM_RE.search(line)
    ]

    blank_pages = []
    pages = info.get("Pages")
    if isinstance(pages, int):
        for page in range(1, pages + 1):
            page_text = extract_text(pdf, page=page).strip()
            if len(page_text) < 8:
                blank_pages.append(page)

    source = analyze_source_typst(source_typst)
    warnings = []
    if latin_lines:
        warnings.append({"severity": "warn", "message": "PDF visible text contains Latin letters"})
    if technical_lines:
        warnings.append({"severity": "warn", "message": "PDF visible text contains technical terms"})
    if source["oversized_qr_widths_mm"]:
        warnings.append({"severity": "warn", "message": "QR code width is larger than 30mm"})
    if blank_pages:
        warnings.append({"severity": "info", "message": "PDF has very low-text pages"})

    status = "warn" if any(item["severity"] == "warn" for item in warnings) else "ok"
    return {
        "status": status,
        "pdf": str(pdf),
        "pdfinfo": info,
        "source_typst": source,
        "latin_line_count": len(latin_lines),
        "latin_lines": latin_lines[:50],
        "technical_line_count": len(technical_lines),
        "technical_lines": technical_lines[:50],
        "blank_pages": blank_pages[:50],
        "warnings": warnings,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Layout QA: {Path(report['pdf']).name}",
        "",
        f"- Status: `{report['status']}`",
        f"- Pages: `{report['pdfinfo'].get('Pages', 'unknown')}`",
        f"- Latin lines: `{report['latin_line_count']}`",
        f"- Technical-term lines: `{report['technical_line_count']}`",
        f"- Blank/low-text pages: `{len(report['blank_pages'])}`",
        "",
        "## Warnings",
        "",
    ]
    if report["warnings"]:
        for item in report["warnings"]:
            lines.append(f"- `{item['severity']}` {item['message']}")
    else:
        lines.append("_None._")
    lines.append("")

    if report["source_typst"].get("exists"):
        lines.extend(
            [
                "## Source Typst",
                "",
                f"- Path: `{report['source_typst']['path']}`",
                f"- QR widths mm: `{report['source_typst']['qr_widths_mm']}`",
                "",
            ]
        )

    if report["latin_lines"]:
        lines.append("## Latin Samples")
        lines.append("")
        for item in report["latin_lines"][:15]:
            lines.append(f"- line {item['line']}: {item['text']}")
        lines.append("")

    if report["technical_lines"]:
        lines.append("## Technical-Term Samples")
        lines.append("")
        for item in report["technical_lines"][:15]:
            lines.append(f"- line {item['line']}: {item['text']}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--source-typst", type=Path)
    parser.add_argument("--out", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = analyze_pdf(args.pdf, args.source_typst)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        args.out.with_suffix(".md").write_text(render_markdown(report), encoding="utf-8")
    print(f"{report['status']}: {args.pdf}")


if __name__ == "__main__":
    main()
