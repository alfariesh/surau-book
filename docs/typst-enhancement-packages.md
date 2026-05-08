# Typst Enhancement Packages

This note records the package decisions for the Surau Arabic book layout pipeline.
The rule is simple: packages may improve presentation, but the canonical source
remains the reviewed text, passage IDs, semantic tags, and edition page map.

## Core candidates

| Package | Status | Use |
| --- | --- | --- |
| `naifs-islamic-research-toolkit` | Use now | Qur'an rendering and Islamic research helpers. Requires Qur'an fonts through `--font-path`. |
| `fletcher` | Use now | Small editorial diagrams: extraction flow, sanad/relationship sketches, concept maps. |
| `marginalia` | Use carefully | Short editor notes and learning hints in the outer margin. Best for print editions with enough outside margin. |
| `zebra` | Use now | QR codes for stable passage links, chapter links, and companion app links. |

## Deferred candidates

| Package | Status | Reason |
| --- | --- | --- |
| `glossarium` | Defer | Useful for multilingual glossary/index, but the default output needs a custom Arabic/RTL renderer. |
| `bidi-flow` / `auto-bidi` | Test per edition | Needed for Arabic-English or Arabic-Indonesian pages. Arabic-only editions do not need it yet. |
| `timeliney` / `zeitline` | Later | Good for Tarikh-style chronology pages after semantic events exist. |
| `genealotree` | Later | Good for khalifah/ulama genealogy after people entities are extracted. |
| `pintorita` | Later | Good for lightweight charts once QA or knowledge-graph metrics become part of the book. |
| `cap-able`, `smartaref`, `varioref` | Later | Useful after figures/tables/sections are formalized across a full edition. |

## Current prototype

The first enhanced prototype is:

`books/afdhalush-shalawat/editions/surau-enhanced-prototype/book.typ`

It tests:

- semantic section cards
- Qur'an block rendering
- matn/quote/poetry blocks
- margin notes
- QR citation block with fixed size
- simple editorial diagram
- manual RTL glossary table
- bilingual text island

Compile it with:

```sh
typst compile --font-path assets/fonts/quran/hafs \
  books/afdhalush-shalawat/editions/surau-enhanced-prototype/book.typ \
  books/afdhalush-shalawat/editions/surau-enhanced-prototype/output.pdf
```

For live preview:

```sh
typst watch --font-path assets/fonts/quran/hafs \
  books/afdhalush-shalawat/editions/surau-enhanced-prototype/book.typ \
  books/afdhalush-shalawat/editions/surau-enhanced-prototype/output.pdf
```

The optimized A5 spacing test is:

`books/afdhalush-shalawat/editions/surau-enhanced-optimized/book.typ`

It keeps mirrored print margins, but reduces the outside margin and margin-note
lane so single-page preview does not look overly padded. QR codes are fixed at
20mm by default through Zebra's `width` parameter.

## Integration rule

Do not put decorative decisions directly into extracted manuscript text. Add a
reviewable layer first, for example `annotations.jsonl` or enhanced passage
metadata:

```json
{"id":"ASH-00009","kind":"matn","tags":["salawat"],"layout_hint":"matn_block"}
{"id":"ASH-00010","kind":"quote","source_ref":"sawaeq","layout_hint":"quote_block"}
{"id":"ASH-00011","kind":"ayah","quran_ref":"33:56","layout_hint":"ayah_block"}
```

The Typst builder can then map semantic tags to layout components. This keeps
API, RAG, graph, translation, and print layout aligned to one citation source.
