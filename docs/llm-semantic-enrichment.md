# LLM Semantic Enrichment

This layer lets an LLM propose modern educational layout enhancements without
changing the canonical Arabic text.

## Flow

```text
clean/manuscript.md
  + passages.jsonl
  + annotations/semantic-draft.jsonl
  -> scripts/enrich_semantics_llm.py
  -> annotations/semantic-llm-proposals.jsonl
  -> human review
  -> reviewed semantic annotations
  -> Typst/API/RAG/graph
```

## What the LLM may do

- classify a passage as ayah, hadith, quote, matn, dua, poem, list, biography, or prose
- propose a Typst component such as `ayah_block`, `quote_block`, `matn_block`, or `table_block`
- identify people, books, places, and concepts visible in the text
- propose diagrams, tables, glossary entries, editor notes, cross-references, or illustrations
- mark uncertain references as needing review

## What the LLM must not do

- rewrite the canonical Arabic text
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

## Review rule

Treat LLM output as `llm_draft`. Only reviewed proposals should be merged into
the main annotation file that drives generated editions.
