// Generated from layouts/surau-arabic-book/components.typ.
// Edit the source layout template, then regenerate this edition.

// Reusable semantic components for Surau Arabic book editions.

#let passage(id, body, role: "body") = [
  #metadata((kind: "passage", id: id, role: role))
  #if role == "matn" [
    #block(above: 0.36em, below: 0.58em)[
      #set par(justify: true, first-line-indent: 0pt, leading: 0.84em)
      #align(center)[
        #text(size: 1.08em, fill: rgb("#15110d"))[#body]
      ]
    ]
  ] else if role == "ayat" [
    #block(above: 0.3em, below: 0.5em)[
      #set par(justify: true, first-line-indent: 0pt, leading: 0.86em)
      #align(center)[
        #text(size: 1.08em, fill: rgb("#2a4f44"))[#body]
      ]
    ]
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
