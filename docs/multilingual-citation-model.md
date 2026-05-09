# Multilingual Citation Model

This model keeps citation stable when Surau adds Indonesian, English, bilingual, or commentary layers.

## Core Rule

The Arabic passage is the canonical anchor.

```text
Arabic passage ID -> translations -> editions -> API/RAG citations
```

Translations should not create a detached citation source. They should point back to the Arabic passage with `source_passage_id`.

## Field Roles

```text
source_blocks.pdf_page       old PDF extraction audit
edition_refs.*.locator       public book locator
edition_refs.*.viewer        PDF/app navigation target
citation                     single public citation from default_edition
translations.*               language-specific renderings of the Arabic anchor
```

## Canonical Arabic Passage

```json
{
  "id": "ASH-00367",
  "lang": "ar",
  "text": "تَمْحُوَ عَنَّا...",
  "citation": {
    "source": "edition_refs.surau-v1",
    "edition_id": "surau-v1",
    "anchor_id": "ASH-00367",
    "label": "Afdhalush Shalawat, ed. Surau v1, hlm. 71, ASH-00367.",
    "locator": {
      "type": "page",
      "label": "71",
      "page": 71
    }
  }
}
```

## Translation Row

Store translations separately from the Arabic canonical rows:

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

## LLM Translation Workflow

Translate from the canonical Arabic JSONL layer, not from Typst/PDF layout:

```text
books/{work_id}/passages.jsonl + clean/manuscript.md
  + annotations/semantic-reviewed.jsonl
-> scripts/translate_passages.py
-> books/{work_id}/translations/{lang}/passages.jsonl
-> QA
-> optional translation/bilingual Typst layout
```

The script reads metadata, ordering, and citations from `passages.jsonl`, then overlays cleaner source text from `clean/manuscript.md` by passage ID when that file exists. Disable this with `--manuscript ""` if you intentionally want raw passage text.

By default, the script also reads `annotations/semantic-reviewed.jsonl`. These annotations are not a second source text; they are guidance for the translator so ayah, hadith/report prose, du'a, salawat, quotes, and other semantic segments receive the right tone and boundaries. Disable this with `--annotations ""` if you need a plain translation test.

Semantic guidance rules:

- LLM may use `semantic_context` to understand what kind of passage it is translating.
- LLM must not mention internal fields such as `kind`, `role`, `layout`, or `review_required`.
- Qur'an candidates must be translated carefully without inventing a surah/ayah reference.
- Hadith/report prose must not gain new takhrij, grading, isnad, or source claims.
- Du'a/salawat should preserve devotional repetition and tone.

Set the API key outside the repo:

```bash
export KILO_API_KEY="..."
```

Dry-run a small set:

```bash
python3 scripts/translate_passages.py \
  --book-dir books/afdhalush-shalawat \
  --lang id \
  --id ASH-00008,ASH-00009,ASH-00033 \
  --annotations annotations/semantic-reviewed.jsonl \
  --dry-run
```

Run a small live smoke translation:

```bash
python3 scripts/translate_passages.py \
  --book-dir books/afdhalush-shalawat \
  --lang id \
  --id ASH-00008,ASH-00009,ASH-00033 \
  --annotations annotations/semantic-reviewed.jsonl \
  --model deepseek-v4-pro \
  --timeout 75 \
  --row-deadline 300 \
  --retries 0 \
  --continue-on-error
```

Defaults:

```text
API base: https://api.kilo.ai/api/gateway
Endpoint: /chat/completions
Model: deepseek-v4-pro
```

The script writes after each translated passage, so it can be resumed safely. Existing translations are skipped unless `--force` is passed.

Use `--row-deadline` for batch runs so one slow passage does not stall the whole job. Use `--continue-on-error` when you want the script to keep saving successful rows and report failed IDs at the end of the terminal output.

## Translation Review Loop

Before translating a whole book, create a small representative review packet:

```bash
python3 scripts/build_translation_review.py \
  --book-dir books/afdhalush-shalawat \
  --lang id \
  --lang en
```

This writes:

```text
reports/translation-reviews/{work_id}-translation-review-batch.json
reports/translation-reviews/{work_id}-translation-review-batch.md
```

The review packet selects mixed passages such as opening prose, short headings, salawat formulas, hadith/report prose, poetry sections, very short edge cases, and long passages. It shows Arabic source, available translations, missing translation commands, model metadata, length ratios, Arabic-script leaks, and the public citation attached to the canonical Arabic anchor.

Then run the normal QA report:

```bash
python3 scripts/qa_report.py
```

Translation QA checks JSONL validity, anchor IDs, status fields, model metadata, source citation drift, Arabic-script leakage in non-Arabic translations, and unusual source/target length ratios.

## Public API Shape

Arabic:

```json
{
  "id": "ASH-00367",
  "lang": "ar",
  "text": "تَمْحُوَ عَنَّا...",
  "citation": "Afdhalush Shalawat, ed. Surau v1, hlm. 71, ASH-00367.",
  "viewer": {
    "pdf_page": 75
  }
}
```

Indonesian:

```json
{
  "id": "ASH-00367",
  "lang": "id",
  "source_lang": "ar",
  "arabic": "تَمْحُوَ عَنَّا...",
  "translation": "Engkau menghapus dari kami...",
  "source_passage_id": "ASH-00367",
  "citation": "Afdhalush Shalawat, ed. Surau v1, hlm. 71, ASH-00367.",
  "viewer": {
    "pdf_page": 75
  }
}
```

## Edition IDs

Use separate edition IDs for layout variants:

```text
surau-v1-ar          Arabic print edition
surau-v1-id          Indonesian translation print edition
surau-v1-bilingual   Arabic + Indonesian facing edition
```

The default public citation should come from `book.yml.default_edition`. A translation edition can expose its own locator as secondary metadata, but it should not hide the Arabic canonical citation.

## RAG Source Shape

```json
{
  "passage_id": "ASH-00367",
  "source_lang": "ar",
  "answer_lang": "id",
  "citation": "Afdhalush Shalawat, ed. Surau v1, hlm. 71, ASH-00367.",
  "translation_id": "ASH-00367.id"
}
```

This keeps answers readable in the requested language while preserving scholarly traceability to the Arabic source.
