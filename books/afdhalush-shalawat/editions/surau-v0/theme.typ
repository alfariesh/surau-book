// Generated from layouts/surau-arabic-book/theme.typ.
// Edit the source layout template, then regenerate this edition.

// Surau Arabic book layout template.
// Edit this file to change print layout across generated editions.

#let arabic_font_stack = (
  "DecoType Naskh",
  "Geeza Pro",
  "Al Bayan",
  "Damascus",
  "Arial Unicode MS",
)

#let latin_font_stack = (
  "Libertinus Serif",
  "New Computer Modern",
  "Times New Roman",
)

#let style_config(style) = {
  if style == "clean-modern" {
    (
      text_size: 10.5pt,
      leading: 0.67em,
      margin: (inside: 19mm, outside: 14mm, top: 17mm, bottom: 21mm),
      h1_size: 17.5pt,
      h2_size: 13.8pt,
      h3_size: 11.8pt,
      header_size: 7.6pt,
      footer_size: 8.2pt,
      ink: rgb("#171717"),
      muted: luma(36%),
      rule: luma(72%),
      accent: rgb("#1d5f63"),
      title_size: 22pt,
    )
  } else if style == "ornamental-majlis" {
    (
      text_size: 11.25pt,
      leading: 0.79em,
      margin: (inside: 21mm, outside: 15mm, top: 19mm, bottom: 23mm),
      h1_size: 21pt,
      h2_size: 15.8pt,
      h3_size: 12.8pt,
      header_size: 7.8pt,
      footer_size: 8.4pt,
      ink: rgb("#241c14"),
      muted: luma(34%),
      rule: rgb("#b8a77c"),
      accent: rgb("#80642e"),
      title_size: 25pt,
    )
  } else {
    (
      text_size: 11pt,
      leading: 0.74em,
      margin: (inside: 20mm, outside: 14mm, top: 18mm, bottom: 22mm),
      h1_size: 19.5pt,
      h2_size: 14.8pt,
      h3_size: 12.4pt,
      header_size: 7.7pt,
      footer_size: 8.3pt,
      ink: rgb("#1d1712"),
      muted: luma(35%),
      rule: rgb("#c1b18a"),
      accent: rgb("#5f4828"),
      title_size: 24pt,
    )
  }
}

#let current_heading(level) = context {
  let current = counter(page).get().first()
  let headings = query(heading.where(level: level)).filter(h =>
    counter(page).at(h.location()).first() <= current
  )

  if headings.len() > 0 {
    headings.last().body
  } else {
    []
  }
}

#let running_header(cfg) = context {
  let page_no = counter(page).get().first()
  if page_no > 2 [
    #set text(font: arabic_font_stack, size: cfg.header_size, fill: cfg.muted)
    #set par(justify: false, first-line-indent: 0pt)
    #align(center + horizon)[#current_heading(1)]
    #v(-1.5pt)
    #line(length: 100%, stroke: 0.28pt + cfg.rule)
  ]
}

#let running_footer(cfg) = context {
  let page_no = counter(page).get().first()
  if page_no > 2 [
    #set text(font: arabic_font_stack, size: cfg.footer_size, fill: cfg.muted)
    #set par(justify: false, first-line-indent: 0pt)
    #align(center + horizon)[#counter(page).display("١")]
  ]
}

#let apply_theme(style: "classic-turath", body) = {
  let cfg = style_config(style)

  set page(
    paper: "a5",
    binding: right,
    margin: cfg.margin,
    numbering: "١",
    number-align: bottom + center,
    header: running_header(cfg),
    footer: running_footer(cfg),
    header-ascent: 24%,
    footer-descent: 28%,
  )

  set text(
    font: arabic_font_stack,
    size: cfg.text_size,
    lang: "ar",
    dir: rtl,
    fill: cfg.ink,
  )

  set par(
    justify: true,
    leading: cfg.leading,
    first-line-indent: 1em,
  )

  set heading(numbering: none)

  show heading.where(level: 1): it => [
    #pagebreak(weak: true)
    #v(0.72cm)
    #align(center)[#line(length: 52%, stroke: 0.45pt + cfg.accent)]
    #v(0.23cm)
    #align(center)[
      #set par(justify: false, first-line-indent: 0pt)
      #text(size: cfg.h1_size, weight: "bold", fill: cfg.accent)[#it.body]
    ]
    #v(0.2cm)
    #align(center)[#line(length: 34%, stroke: 0.45pt + cfg.accent)]
    #v(0.48cm)
  ]

  show heading.where(level: 2): it => [
    #v(0.48cm)
    #align(center)[
      #set par(justify: false, first-line-indent: 0pt)
      #text(size: cfg.h2_size, weight: "bold", fill: cfg.accent)[#it.body]
    ]
    #v(0.16cm)
    #align(center)[#line(length: 22%, stroke: 0.32pt + cfg.rule)]
    #v(0.24cm)
  ]

  show heading.where(level: 3): it => [
    #v(0.32cm)
    #block(above: 0pt, below: 0.16cm)[
      #set par(justify: false, first-line-indent: 0pt)
      #text(size: cfg.h3_size, weight: "bold", fill: cfg.accent)[#it.body]
    ]
  ]

  body
}

#let cover(
  title_ar,
  title_id,
  author,
  edition,
  style: "classic-turath",
) = {
  let cfg = style_config(style)
  align(center)[
    #v(1.5cm)
    #line(length: 58%, stroke: 0.45pt + cfg.accent)
    #v(0.28cm)
    #text(size: cfg.title_size, weight: "bold", fill: cfg.accent)[#title_ar]
    #v(0.28cm)
    #line(length: 34%, stroke: 0.45pt + cfg.accent)
    #v(0.78cm)
    #text(font: latin_font_stack, size: 11pt, fill: cfg.muted)[#title_id]
    #v(1.05cm)
    #text(size: 13pt)[#author]
    #v(2.4cm)
    #text(size: 9pt, fill: cfg.muted)[طبعة سوراو]
    #v(0.2cm)
    #text(font: latin_font_stack, size: 8pt, fill: cfg.muted)[#edition]
  ]
}

#let table_of_contents() = [
  #heading(level: 1, outlined: false)[الفهرس]
  #v(0.2cm)
  #outline(title: none, depth: 2)
]
