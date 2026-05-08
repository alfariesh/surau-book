// Reusable semantic components for Surau Arabic book editions.

#import "@preview/naifs-islamic-research-toolkit:0.1.0": quran
#import "@preview/fletcher:0.5.8" as fletcher: diagram, node, edge
#import "@preview/zebra:0.1.0": qrcode

#let semantic_card(title, body) = block(
  above: 0.5em,
  below: 0.72em,
  inset: (x: 0.9em, y: 0.72em),
  radius: 3pt,
  stroke: 0.45pt + rgb("#c7b98f"),
  fill: rgb("#fffdf7"),
)[
  #set par(justify: true, first-line-indent: 0pt)
  #text(size: 0.9em, weight: "bold", fill: rgb("#80642e"))[#title]
  #v(0.25em)
  #body
]

#let matn_block(body) = block(
  breakable: true,
  above: 0.42em,
  below: 0.64em,
  inset: (x: 0.55em, y: 0.42em),
)[
  #set par(justify: true, first-line-indent: 0pt, leading: 0.86em)
  #align(center)[
    #text(size: 1.08em, fill: rgb("#15110d"))[#body]
  ]
]

#let ayah_text_block(body) = block(
  breakable: true,
  above: 0.38em,
  below: 0.58em,
  inset: (x: 0.65em, y: 0.58em),
  radius: 3pt,
  stroke: 0.45pt + rgb("#98b8ad"),
  fill: rgb("#f7fbf8"),
)[
  #set par(justify: true, first-line-indent: 0pt, leading: 0.88em)
  #align(center)[
    #text(size: 1.08em, fill: rgb("#2a4f44"))[#body]
  ]
]

#let quran_ayah(sura, verse, caption) = figure(
  kind: "ayah",
  supplement: [آية],
  caption: caption,
  block(
    inset: (x: 0.75em, y: 0.7em),
    radius: 3pt,
    stroke: 0.45pt + rgb("#98b8ad"),
    fill: rgb("#f7fbf8"),
  )[
    #set par(justify: false, first-line-indent: 0pt, leading: 0.9em)
    #align(center)[
      #text(size: 1.2em, fill: rgb("#224f43"))[
        #quran(sura: sura, verse: verse)
      ]
    ]
  ],
)

#let quote_block(source, body) = block(
  breakable: true,
  above: 0.45em,
  below: 0.65em,
  inset: (right: 0.78em, left: 0.7em, y: 0.45em),
  stroke: (right: 1.2pt + rgb("#80642e")),
)[
  #set par(justify: true, first-line-indent: 0pt)
  #text(size: 0.95em)[#body]
  #if source != [] [
    #v(0.22em)
    #align(left)[#text(size: 0.78em, fill: luma(42%))[#source]]
  ]
]

#let poem_block(body) = block(
  breakable: true,
  above: 0.45em,
  below: 0.65em,
  inset: (x: 1em, y: 0.45em),
)[
  #set par(justify: false, first-line-indent: 0pt, leading: 1em)
  #align(center)[#body]
]

#let passage(id, body, role: "body") = [
  #metadata((kind: "passage", id: id, role: role))
  #if role == "matn" [
    #matn_block(body)
  ] else if role == "ayat" [
    #ayah_text_block(body)
  ] else if role == "quote" [
    #quote_block([], body)
  ] else if role == "poem" [
    #poem_block(body)
  ] else [
    #block(above: 0.14em, below: 0.42em)[#body]
  ]
]

#let editor_note(body) = [
  #block(
    above: 0.5em,
    below: 0.5em,
    inset: (x: 0.8em, y: 0.55em),
    stroke: (right: 0.5pt + luma(62%)),
  )[
    #set par(first-line-indent: 0pt)
    #text(size: 0.88em, fill: luma(34%))[#body]
  ]
]

#let divider(width: 58%) = [
  #v(0.28cm)
  #align(center)[#line(length: width, stroke: 0.42pt + luma(62%))]
  #v(0.28cm)
]

#let citation_qr(id, target, caption, size: 20mm) = [
  #metadata((kind: "citation-qr", id: id, target: target))
  #figure(
    kind: "qr",
    supplement: [رمز],
    caption: caption,
    align(center)[
      #qrcode(
        target,
        quiet-zone: true,
        width: size,
        background-fill: white,
        options: (ec-level: "m"),
      )
    ],
  )
]

#let extraction_flow_diagram(caption) = figure(
  kind: "diagram",
  supplement: [مخطط],
  caption: caption,
  align(center)[
    #set text(size: 0.8em, fill: rgb("#1d1712"))
    #fletcher.diagram(
      cell-size: 17mm,
      node-stroke: 0.45pt + rgb("#80642e"),
      node-fill: rgb("#fffdf7"),
      edge-stroke: 0.55pt + rgb("#80642e"),
      fletcher.node((0, 0), align(center)[PDF خام]),
      fletcher.node((1, 0), align(center)[متن منظّف]),
      fletcher.node((2, 0), align(center)[وسوم دلالية]),
      fletcher.node((3, 0), align(center)[Typst]),
      fletcher.node((4, 0), align(center)[طبعة واستشهاد]),
      fletcher.edge((0, 0), (1, 0), "->"),
      fletcher.edge((1, 0), (2, 0), "->"),
      fletcher.edge((2, 0), (3, 0), "->"),
      fletcher.edge((3, 0), (4, 0), "->"),
    )
  ],
)
