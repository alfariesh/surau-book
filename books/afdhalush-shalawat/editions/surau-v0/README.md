# Afdhalush Shalawat - Surau v0

Typst print edition generated from:

```text
books/afdhalush-shalawat/clean/manuscript.md
```

Regenerate Typst files:

```bash
python3 scripts/build_typst_edition.py \
  --book-dir books/afdhalush-shalawat \
  --edition surau-v0 \
  --manuscript clean/manuscript.md
```

Compile PDF:

```bash
typst compile \
  books/afdhalush-shalawat/editions/surau-v0/book.typ \
  books/afdhalush-shalawat/editions/surau-v0/output.pdf
```

Generate page map for citation:

```bash
python3 scripts/build_page_map.py \
  --book-dir books/afdhalush-shalawat \
  --edition surau-v0
```

Sync page-map citations into `passages.jsonl`:

```bash
python3 scripts/sync_edition_refs.py \
  --book-dir books/afdhalush-shalawat \
  --edition surau-v0
```

Because `book.yml` sets `default_edition: surau-v0`, this also fills each passage's top-level `citation` field for public API/RAG use.

Layout files:

```text
book.typ               full book entrypoint
theme.typ              generated copy from layouts/surau-arabic-book/theme.typ
components.typ         generated copy from layouts/surau-arabic-book/components.typ
content.typ            generated full manuscript content
build-info.json        generation summary
page-map.json          passage start-page map for citation
assets/fonts/README.md font notes
```

Layout workflow:

1. Edit durable layout in `layouts/surau-arabic-book/`.
2. Run `scripts/clean_manuscript.py` after text extraction changes.
3. Regenerate this edition from `clean/manuscript.md`.
4. Compile or watch `book.typ`.
5. Regenerate `page-map.json` after the PDF layout changes.
6. Sync edition refs into `passages.jsonl`.
7. Keep `content.typ`, `theme.typ`, and `components.typ` generated.

Current edition:

- layout engine: Typst
- paper: A5
- binding: right
- source passages: 1768
- semantic passage roles: body 1709, matn 59
- source headings: 84
- output pages: 113
