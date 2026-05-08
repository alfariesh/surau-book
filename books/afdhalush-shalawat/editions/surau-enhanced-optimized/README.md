# Surau Enhanced Optimized

This is an isolated Typst test for a more compact modern Arabic turath edition.
It does not replace `surau-v0`; it tests smaller margins, tighter component
spacing, and smaller QR citation blocks.

## What it tests

- Qur'an rendering with `naifs-islamic-research-toolkit`
- editorial diagrams with `fletcher`
- QR citation links with `zebra`
- compact symmetric A5 preview margins
- smaller QR code size
- matn, quote, poetry, ayah, glossary, inline note, and bilingual layout blocks

## Compile

```sh
typst compile --font-path assets/fonts/quran/hafs \
  books/afdhalush-shalawat/editions/surau-enhanced-optimized/book.typ \
  books/afdhalush-shalawat/editions/surau-enhanced-optimized/output.pdf
```

## Watch

```sh
typst watch --font-path assets/fonts/quran/hafs \
  books/afdhalush-shalawat/editions/surau-enhanced-optimized/book.typ \
  books/afdhalush-shalawat/editions/surau-enhanced-optimized/output.pdf
```

VS Code tasks are also available:

- `Typst Compile: Afdhalush Enhanced Optimized`
- `Typst Watch: Afdhalush Enhanced Optimized`

## Notes

`glossarium` was tested, but the default output is not yet suitable for this
Arabic RTL edition. The prototype uses a manual glossary table until we add a
custom renderer or generate glossary pages from API data.

The old prototype used a large outside margin for `marginalia`, so page padding
looked large and alternated between right and left in single-page PDF preview.
This variant uses symmetric left/right margins for editing preview and moves
learning notes into inline blocks. For a final print edition, mirrored
inside/outside margins can be restored once the trim size and binding are fixed.
