# Surau Enhanced Prototype

This is an isolated Typst prototype for a modern Arabic turath edition. It does
not replace `surau-v0`; it tests layout components before they become part of
the generated edition pipeline.

## What it tests

- Qur'an rendering with `naifs-islamic-research-toolkit`
- editorial diagrams with `fletcher`
- margin notes with `marginalia`
- QR citation links with `zebra`
- matn, quote, poetry, ayah, glossary, and bilingual layout blocks

## Compile

```sh
typst compile --font-path assets/fonts/quran/hafs \
  books/afdhalush-shalawat/editions/surau-enhanced-prototype/book.typ \
  books/afdhalush-shalawat/editions/surau-enhanced-prototype/output.pdf
```

## Watch

```sh
typst watch --font-path assets/fonts/quran/hafs \
  books/afdhalush-shalawat/editions/surau-enhanced-prototype/book.typ \
  books/afdhalush-shalawat/editions/surau-enhanced-prototype/output.pdf
```

VS Code tasks are also available:

- `Typst Compile: Afdhalush Enhanced Prototype`
- `Typst Watch: Afdhalush Enhanced Prototype`

## Notes

`glossarium` was tested, but the default output is not yet suitable for this
Arabic RTL edition. The prototype uses a manual glossary table until we add a
custom renderer or generate glossary pages from API data.
