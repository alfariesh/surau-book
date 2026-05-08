# Fonts For Typst App

The local prototype uses fonts already available on this Mac:

```typst
"DecoType Naskh", "Geeza Pro", "Al Bayan", "Damascus"
```

For typst.app, upload one or more `.ttf`/`.otf` files into the project and then add its font family name to `theme.typ`.

Recommended Arabic book fonts:

- Amiri
- Noto Naskh Arabic
- Scheherazade New

Keep the chosen production font stable before freezing `surau-v1`, because font changes can move passages across pages and therefore change citation page numbers.
