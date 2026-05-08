# Surau Arabic Book Layout

This directory is the editable Typst template for Arabic print editions.

Edit these files while watching or compiling a generated edition PDF:

```text
theme.typ       page size, right binding, margins, headers, footers, headings, cover, TOC
components.typ  semantic blocks such as passage, matn, ayah, quote, poetry, QR, diagram
```

Available styles:

- `classic-turath`: balanced print defaults.
- `clean-modern`: lighter modern spacing.
- `ornamental-majlis`: larger display headings and wider leading.
- `enhanced-compact`: symmetric A5 editing/preview margins for the enhanced pipeline.

Generated edition folders import this template. Do not put long-term layout edits
inside `books/*/editions/*/content.typ` because that file is regenerated from
`manuscript.md`.

Recommended font workflow:

1. Keep the current macOS-safe stack for clean local compilation.
2. Add print fonts under an edition or shared assets folder when ready.
3. Compile with `typst compile --font-path <font-dir> ...`.
4. Use `--font-path assets/fonts/quran/hafs` when Qur'an components are enabled.

Good Arabic book font candidates to test later:

- Amiri
- Noto Naskh Arabic
- Scheherazade New
- KFGQPC Uthmanic Script for Qur'an text

Package-backed components currently available:

- `quran_ayah` from `naifs-islamic-research-toolkit`
- `extraction_flow_diagram` from `fletcher`
- `citation_qr` from `zebra`

Keep these components driven by semantic metadata instead of inline decoration in
`manuscript.md`.
