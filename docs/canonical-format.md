# Surau Canonical Book Format

Version: `0.1`

This format is the shared contract between extraction, editorial review, API, RAG, graph, and print layout. The old PDF is treated as raw material; the canonical files below are the working source for Surau editions.

## Directory Layout

```text
books/{work_id}/
  book.yml
  manuscript.md
  passages.jsonl
  clean/
    manuscript.md
    cleaning-report.json
  raw/
    raw.json
    raw.md
  editions/
    surau-v0/
      book.typ
      output.pdf
      page-map.json
```

Required now:

- `book.yml`
- `manuscript.md`
- `passages.jsonl`
- `raw/raw.json`
- `raw/raw.md`

Optional later:

- `assets/`
- `editions/{edition_id}/`
- `translations/{lang}/`
- `reviews/`
- `graph/`

## Status Lifecycle

Use these values consistently in `book.yml`, front matter, and passage rows:

```text
raw_extraction     extracted but not cleaned
draft_extraction   cleaned automatically, not editor-reviewed
draft              manually edited but not final
reviewed           checked by an editor
published          frozen for an edition/citation
```

## book.yml

Required fields:

```yaml
schema_version: 0.1
id: afdhalush-shalawat
title_ar: أفضل الصلوات على سيد السادات
title_id: Afdhalush Shalawat
author: Yusuf bin Ismail an-Nabhani
language: ar
canonical_language: ar
status: draft_extraction
default_edition: surau-v1
public_citation:
  source: default_edition
  anchor: passage_id
translation_policy:
  anchor_language: ar
  anchor_field: source_passage_id
source:
  pdf: sources/pdfs/AFDHALUSH SHALAWAT.pdf
  pages: 125
outputs:
  raw_json: raw/raw.json
  raw_markdown: raw/raw.md
  manuscript: manuscript.md
  clean_manuscript: clean/manuscript.md
  cleaning_report: clean/cleaning-report.json
  passages: passages.jsonl
```

Recommended later:

```yaml
work_type: book
editorial_policy: source_pdf_used_as_raw_material_only
heading_profile: generic-shamela
default_edition: surau-v1
```

## manuscript.md

`manuscript.md` is for human editing and layout generation. It should be readable and mostly free of machine-only metadata.

## Cleaning Stage

Run the cleaner after extraction to create a non-destructive draft:

```bash
python3 scripts/clean_manuscript.py \
  --book-dir books/afdhalush-shalawat
```

Generated files:

```text
books/{work_id}/clean/
  manuscript.md
  cleaning-report.json
```

`clean/manuscript.md` is an automated draft, not a published text. Review `cleaning-report.json` for suspicious artifacts before marking passages as reviewed.

Cleaning profiles live in:

```text
config/cleaning_profiles.yml
```

Use global rules for safe Arabic text cleanup, then add book-specific profile rules only for repeated source artifacts that are proven in that kitab. Keep profile rules conservative because `clean/manuscript.md` becomes the input for Typst layout and later editorial review.

Required front matter:

```md
---
work_id: afdhalush-shalawat
title_ar: أفضل الصلوات على سيد السادات
schema_version: 0.1
edition_status: draft_extraction
source_policy: source_pdf_used_as_raw_material_only
---
```

Headings use Markdown:

```md
# القسم الأول

## الفصل الأول

::passage{id="ASH-00001"}
النص هنا...
```

Rules:

- Every text unit must start with `::passage{id="..."}`.
- Passage IDs must be stable after editorial work begins.
- Do not use old PDF page numbers as public citation anchors.
- Keep raw source details out of `manuscript.md`; store them in `passages.jsonl`.

## passages.jsonl

One JSON object per line. This is the machine-readable canonical layer.

Required fields:

```json
{
  "id": "ASH-00001",
  "work_id": "afdhalush-shalawat",
  "sequence": 1,
  "lang": "ar",
  "section_path": ["القسم الأول", "الفصل الأول"],
  "text": "النص هنا...",
  "review_status": "draft_extraction",
  "citation": {},
  "source_blocks": [
    {
      "pdf_page": 8,
      "block_id": "afdhalush-shalawat.p0008.b003",
      "bbox": [28.35, 517.7, 566.93, 542.5]
    }
  ],
  "edition_refs": {}
}
```

Optional fields later:

```json
{
  "content_kind": "body",
  "tags": ["shalawat"],
  "entities": [],
  "citations": [],
  "notes": [],
  "normalized_text": "",
  "translation_id": null
}
```

Recommended `content_kind` values:

```text
body
heading
quran_ayah
hadith
poem
footnote
editor_note
glossary_entry
```

## Edition Refs

Edition references are created only after a Surau layout is generated and frozen.

```json
{
  "edition_refs": {
    "surau-v1": {
      "page": 12,
      "physical_page": 16,
      "page_semantics": "start_page",
      "locator": {
        "type": "page",
        "label": "12",
        "page": 12
      },
      "viewer": {
        "pdf_page": 16
      },
      "label": "Afdhalush Shalawat, ed. Surau v1, hlm. 12, ASH-00034.",
      "source": "books/afdhalush-shalawat/editions/surau-v1/page-map.json"
    }
  },
  "citation": {
    "source": "edition_refs.surau-v1",
    "edition_id": "surau-v1",
    "anchor_id": "ASH-00034",
    "label": "Afdhalush Shalawat, ed. Surau v1, hlm. 12, ASH-00034.",
    "locator": {
      "type": "page",
      "label": "12",
      "page": 12
    }
  }
}
```

Public citation should use the Surau edition once published:

```text
Afdhalush Shalawat, ed. Surau v1, hlm. 12, ASH-00034.
```

Before publication, use internal passage IDs only.

Keep these fields semantically separate:

```text
source_blocks.pdf_page     old/source PDF page, for extraction audit only
edition_refs.*.physical_page final PDF file page, for viewer/deep links
edition_refs.*.locator      edition locator, for public citation
citation                    single public citation from book.yml default_edition
```

## Typst Print Edition

Generate a print edition from the canonical manuscript:

```bash
python3 scripts/build_typst_edition.py \
  --book-dir books/afdhalush-shalawat \
  --edition surau-v0 \
  --manuscript clean/manuscript.md
```

Compile the PDF:

```bash
typst compile \
  books/afdhalush-shalawat/editions/surau-v0/book.typ \
  books/afdhalush-shalawat/editions/surau-v0/output.pdf
```

Generated files:

```text
books/{work_id}/editions/{edition_id}/
  book.typ
  theme.typ
  components.typ
  content.typ
  output.pdf
  build-info.json
  page-map.json
```

`content.typ`, `theme.typ`, and `components.typ` are generated into the edition directory. Durable layout changes belong in `layouts/surau-arabic-book/`; edit `manuscript.md` for text changes, then regenerate. Each passage is emitted through a Typst `passage(id, role: "...")[...]` helper so the layout keeps passage IDs available for future page-map/citation work.

Use `book.typ` for local preview and final compilation.

## Page Map And Citation

After compiling or changing the Typst layout, generate a page map:

```bash
python3 scripts/build_page_map.py \
  --book-dir books/afdhalush-shalawat \
  --edition surau-v0
```

The page map lives at:

```text
books/{work_id}/editions/{edition_id}/page-map.json
```

Each entry maps a stable passage ID to the starting page in the Surau edition:

```json
{
  "id": "ASH-00034",
  "role": "body",
  "page": 12,
  "physical_page": 12,
  "citation": "Afdhalush Shalawat, ed. surau-v0, hlm. 12, ASH-00034."
}
```

For now, page maps use `page_semantics: start_page`: the page number is where the passage begins. This is enough for citation, API display, and RAG source attribution. Passage page ranges can be added later by emitting an end marker after each passage body.

Sync the page map into canonical passage rows:

```bash
python3 scripts/sync_edition_refs.py \
  --book-dir books/afdhalush-shalawat \
  --edition surau-v0
```

This fills `edition_refs.{edition_id}` in `passages.jsonl`:

```json
{
  "edition_refs": {
    "surau-v0": {
      "page": 71,
      "physical_page": 71,
      "page_semantics": "start_page",
      "label": "Afdhalush Shalawat, ed. surau-v0, hlm. 71, ASH-00367.",
      "source": "books/afdhalush-shalawat/editions/surau-v0/page-map.json"
    }
  }
}
```

Run QA after syncing. If a page map exists, QA validates that synced `edition_refs` are present and match `page-map.json`.

## Multilingual Model

The Arabic canonical passage remains the main anchor. Translations, summaries, commentary, and bilingual print editions should point back to the Arabic `source_passage_id`; they should not replace the Arabic citation anchor.

Recommended translation layout:

```text
books/{work_id}/translations/{lang}/
  translation.yml
  passages.jsonl
```

Example `translation.yml`:

```yaml
schema_version: 0.1
work_id: afdhalush-shalawat
lang: id
source_language: ar
source_passages: ../../passages.jsonl
status: draft
translator: Surau Editorial
translation_type: meaning
citation_policy: cite_source_passage
```

Example translated passage row:

```json
{
  "id": "ASH-00367.id",
  "work_id": "afdhalush-shalawat",
  "lang": "id",
  "source_passage_id": "ASH-00367",
  "translation_status": "draft",
  "text": "Engkau menghapus dari kami...",
  "translator": "Surau Editorial"
}
```

Create machine-draft translations from canonical Arabic passages:

```bash
python3 scripts/translate_passages.py \
  --book-dir books/afdhalush-shalawat \
  --lang id \
  --id ASH-00008,ASH-00009,ASH-00367
```

Keep provider credentials in environment variables such as `KILO_API_KEY`; do not store API tokens in repo files.

By default, translation uses `passages.jsonl` for metadata/citation and overlays cleaner text from `clean/manuscript.md` by passage ID. This avoids translating raw extraction artifacts while keeping stable canonical IDs.

Default public API responses should expose the Arabic source citation even when the requested text language is a translation:

```json
{
  "id": "ASH-00367",
  "lang": "id",
  "arabic": "تَمْحُوَ عَنَّا...",
  "translation": "Engkau menghapus dari kami...",
  "citation": "Afdhalush Shalawat, ed. Surau v1, hlm. 71, ASH-00367.",
  "source_passage_id": "ASH-00367"
}
```

If a translation is printed as its own edition, create a separate edition ID such as `surau-v1-id` or `surau-v1-bilingual`. That edition can have its own `edition_refs`, but the response should still retain the canonical Arabic citation unless the user explicitly asks for the translation-edition citation.

See also: `docs/multilingual-citation-model.md`.

## Heading Profiles

Not all PDFs expose good H1/H2/H3 data. Use heading profiles per book type. Profiles live in:

```text
config/heading_profiles.yml
```

Extractor usage:

```bash
python3 scripts/extract_book.py \
  --pdf "sources/pdfs/TARIKH AL-KHULAFA’.pdf" \
  --out books/tarikh-al-khulafa \
  --work-id tarikh-al-khulafa \
  --passage-prefix TAK \
  --heading-profile biography
```

When a profile is applied, `raw/raw.json` keeps `source_level` from the old PDF outline and writes the normalized Surau level into `level`. This lets us preserve source traceability while making `manuscript.md`, `passages.jsonl`, API, RAG, graph, and future Typst layout use the cleaner Surau structure.

Generic Shamela:

```yaml
heading_profile: generic-shamela
rules:
  - pattern: "^القسم"
    level: 1
  - pattern: "^الفصل"
    level: 2
  - pattern: "^فائدة|^تنبيه|^مسألة"
    level: 3
```

Tafsir/Quran:

```yaml
heading_profile: quran-tafsir
rules:
  - kind: surah
    level: 1
  - kind: ayah_number
    level: 2
  - kind: ayah_text
    level: 3
```

Tarikh/Biography:

```yaml
heading_profile: biography
mode: biography
start_pattern: "^أبو بكر الصديق"
default_before_start_level: 1
default_after_start_level: 2
rules:
  - pattern: ".*[0-9٠-٩]+\\s*هـ\\s*[ـ-]?\\s*[0-9٠-٩]+\\s*هـ"
    level: 1
  - pattern: "^أبو بكر الصديق"
    level: 1
  - pattern: "^الخلفاء|^الدولة|^دولة"
    level: 1
```

Known limitation: a biography profile can normalize a bad PDF outline, but it cannot always invent missing major headings if the PDF TOC never exposed them. Those cases should be handled by manual editorial review or a later heading-enrichment pass.

## QA Requirements

Before a book can move from `draft_extraction` to `draft`, QA should show:

- no `Shamela.org`
- no `المحتويات`
- no bad glyph `᧦`
- no numeric-only passages
- no duplicate passage IDs
- no adjacent duplicate headings
- heading count distribution is plausible for the book type
- TOC entries are found in `manuscript.md` headings, or intentionally documented
- short/long passages have been sampled and reviewed
- problem pages have been sampled and reviewed
- contiguous sequence numbers
- every passage has `source_blocks`
- every passage has `lang`
- every passage has `review_status`
- `manuscript.md` passage IDs match `passages.jsonl`
- `clean/manuscript.md` exists before Typst layout
- `clean/manuscript.md` passage IDs match both `manuscript.md` and `passages.jsonl`
- `clean/manuscript.md` has zero blocker artifacts such as legacy print markers, runtime errors, stray `*`, bad Allah glyphs, bidi controls, or leftover tatweel
- `clean/cleaning-report.json` suspicious samples are reviewed before the text is promoted to manual editorial work
- if an edition has `page-map.json`, its passage IDs match `passages.jsonl`
- if an edition has `page-map.json`, synced `edition_refs.{edition_id}` exist and match that page map

Generate reports with:

```bash
python3 scripts/qa_report.py
```

## Current Recommendation

For now, use this source of truth order:

```text
raw PDF -> raw/raw.json -> passages.jsonl -> manuscript.md -> Typst/PDF edition
```

For generated print drafts, use the cleaned layer:

```text
raw PDF -> raw/raw.json -> manuscript.md -> clean/manuscript.md -> Typst/PDF edition -> page-map.json -> edition_refs
```

Once manual editing begins, reverse the editorial source:

```text
manuscript.md -> passages.jsonl -> API/RAG/Typst
```

That transition needs a sync script before serious editing starts.
