# LLM Semantic Enrichment

This layer lets an LLM propose modern educational layout enhancements without
changing the canonical Arabic text.

## Flow

```text
clean/manuscript.md
  + passages.jsonl
  + annotations/semantic-draft.jsonl
  -> exact source_spans (S1, S2, ...)
  -> scripts/enrich_semantics_llm.py
  -> annotations/semantic-llm-proposals.jsonl
  -> human review
  -> reviewed semantic annotations
  -> Typst/API/RAG/graph
```

## What the LLM may do

- classify a passage as ayah, hadith, quote, matn, dua, poem, list, biography, or prose
- select exact source spans by `span_id`
- propose a Typst component such as `ayah_block`, `quote_block`, `matn_block`, or `table_block`
- identify people, books, places, and concepts visible in the text
- propose diagrams, tables, glossary entries, editor notes, cross-references, or illustrations
- mark uncertain references as needing review

Illustration proposals should become reviewable image briefs, not immediate
image assets. See `docs/image-briefs.md` and
`scripts/build_image_briefs.py`. This visual layer is currently parked and
should not drive active Typst builds.

## What the LLM must not do

- rewrite the canonical Arabic text
- return normalized segment text
- invent Qur'an references, hadith grading, source citations, or historical claims
- make public citation decisions
- silently merge changes into `passages.jsonl`

## Run

Dry-run candidate selection:

```sh
python3 scripts/enrich_semantics_llm.py \
  --book-dir books/afdhalush-shalawat \
  --limit 40 \
  --dry-run
```

Dry-run specific passages and inspect exact source spans:

```sh
python3 scripts/enrich_semantics_llm.py \
  --book-dir books/afdhalush-shalawat \
  --id ASH-00008,ASH-00009,ASH-00033 \
  --dry-run \
  --report reports/semantic-enrichment/afdhalush-shalawat-span-dry-run.md
```

LLM run:

```sh
export KILO_API_KEY="..."
python3 scripts/enrich_semantics_llm.py \
  --book-dir books/afdhalush-shalawat \
  --limit 40 \
  --model deepseek-v4-pro
```

Output:

- `books/afdhalush-shalawat/annotations/semantic-llm-proposals.jsonl`
- `reports/semantic-enrichment/afdhalush-shalawat-llm-proposals.md`

Validate proposals against the canonical clean manuscript:

```sh
python3 scripts/validate_semantic_proposals.py \
  --book-dir books/afdhalush-shalawat
```

Merge only safe/reviewed proposals into the edition annotation layer:

```sh
python3 scripts/merge_semantic_annotations.py \
  --book-dir books/afdhalush-shalawat
```

Build a human review queue from validator warnings:

```sh
python3 scripts/build_semantic_review_queue.py \
  --book-dir books/afdhalush-shalawat
```

Outputs:

- `books/afdhalush-shalawat/annotations/semantic-review-queue.jsonl`
- `reports/semantic-enrichment/afdhalush-shalawat-review-queue.md`
- `reports/semantic-enrichment/afdhalush-shalawat-review-queue.html`

After human review, approve non-failing warnings explicitly:

```sh
python3 scripts/merge_semantic_annotations.py \
  --book-dir books/afdhalush-shalawat \
  --approve-id ASH-00008
```

Proposals with `segment_text_not_exact_source_substring` stay blocked because
they contain text that does not match the canonical manuscript exactly.

Build a Typst edition from the reviewed layer:

```sh
python3 scripts/build_typst_edition.py \
  --book-dir books/afdhalush-shalawat \
  --edition surau-v2-enriched \
  --manuscript clean/manuscript.md \
  --style enhanced-compact \
  --annotations annotations/semantic-reviewed.jsonl
```

## Review rule

Treat LLM output as `llm_draft`. Only reviewed proposals should be merged into
the main annotation file that drives generated editions.

The validator blocks any segment whose text is not an exact substring of the
canonical clean manuscript. This is the main guardrail that prevents an LLM from
silently normalizing, correcting, or rewriting kitab text.

The enrichment prompt is span-based: the LLM should return `span_id`, and the
script fills `segment.text` from the canonical manuscript. If the model returns
free text anyway, the script ignores it when a valid `span_id` exists.
