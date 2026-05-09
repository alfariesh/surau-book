# Surau Book

Pipeline eksperimen untuk mengubah PDF kitab/turath menjadi sumber data yang
lebih fleksibel: manuscript canonical, passage JSONL, Typst print edition,
semantic annotation, translation draft, QA report, dan citation/page-map.

## Struktur Utama

- `sources/pdfs/`: PDF sumber sebagai raw material.
- `books/*/raw/`: hasil ekstraksi mentah.
- `books/*/clean/`: manuscript hasil cleaning non-destruktif.
- `books/*/passages.jsonl`: passage canonical untuk API, RAG, graph, dan citation.
- `books/*/annotations/`: semantic annotation draft dan LLM proposal.
- `books/*/assets/`: experimental/parked image brief notes for future visual design.
- `books/*/editions/`: output Typst/PDF dan page-map tiap edition.
- `layouts/surau-arabic-book/`: template Typst reusable.
- `scripts/`: extraction, cleaning, Typst build, page-map, QA, translation, enrichment.
- `reports/`: QA, translation review, semantic enrichment, layout QA.

## API Contract

- Human-readable contract: `docs/api-contract-v0.md`
- Machine-readable OpenAPI: `api/openapi.v0.yaml`

API v0 is read-only and should serve normalized data from `book.yml`,
`passages.jsonl`, `annotations/semantic-reviewed.jsonl`,
`translations/{lang}/passages.jsonl`, and edition page maps. Do not expose raw
JSONL rows directly as public responses.

## Workflow Singkat

```sh
python3 scripts/clean_manuscript.py --book-dir books/afdhalush-shalawat
python3 scripts/build_semantic_annotations.py --book-dir books/afdhalush-shalawat
python3 scripts/build_typst_edition.py \
  --book-dir books/afdhalush-shalawat \
  --edition surau-v1-enhanced \
  --manuscript clean/manuscript.md \
  --style enhanced-compact \
  --annotations annotations/semantic-draft.jsonl
typst compile --font-path assets/fonts/quran/hafs \
  books/afdhalush-shalawat/editions/surau-v1-enhanced/book.typ \
  books/afdhalush-shalawat/editions/surau-v1-enhanced/output.pdf
python3 scripts/build_page_map.py \
  --book-dir books/afdhalush-shalawat \
  --edition surau-v1-enhanced \
  --font-path assets/fonts/quran/hafs
python3 scripts/qa_report.py
```

Parked experimental image prompt notes, not part of the active build:

```sh
python3 scripts/build_image_briefs.py \
  --book-dir books/afdhalush-shalawat \
  --levels 1,2
```

## Catatan

Credential LLM tidak disimpan di repo. Gunakan environment variable seperti
`KILO_API_KEY` ketika menjalankan translation atau semantic enrichment.
