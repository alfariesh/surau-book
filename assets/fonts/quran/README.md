# Quran Fonts

This folder contains a small font subset for Surau Typst experiments with
`@preview/naifs-islamic-research-toolkit`.

Source:

- Repository: https://github.com/NaifAlsultan/typst-quran-package
- Font directory: `fonts/hafs`

The package expects the original font filenames. Do not rename the `.ttf` files.

Compile any edition that uses the Quran package with:

```bash
typst compile --font-path assets/fonts/quran/hafs input.typ output.pdf
```

Current subset:

- `QCF4_Hafs_01_W.ttf`: Surah al-Fatihah and bracket glyphs used in smoke tests.
- `QCF4_Hafs_33_W.ttf`: QS al-Ahzab 33:56 prototype render.

Download more page fonts only when a verified Quran annotation needs them.
