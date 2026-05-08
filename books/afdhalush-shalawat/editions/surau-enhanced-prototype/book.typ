// Surau enhanced layout prototype.
// This file intentionally stays separate from surau-v0 production output.

#import "@preview/naifs-islamic-research-toolkit:0.1.0": quran, set-bracket
#import "@preview/fletcher:0.5.8" as fletcher: diagram, node, edge
#import "@preview/marginalia:0.3.1" as marginalia: note, wideblock
#import "@preview/zebra:0.1.0": qrcode

#set document(
  title: "Afdhalush Shalawat - Enhanced Prototype",
  author: "Surau",
)

#show: marginalia.setup.with(
  inner: (far: 0mm, width: 0mm, sep: 0mm),
  outer: (far: 4mm, width: 27mm, sep: 5mm),
  top: 18mm,
  bottom: 22mm,
  book: true,
  clearance: 10pt,
)

#set page(
  paper: "a5",
  binding: right,
  margin: (inside: 18mm, outside: 40mm, top: 18mm, bottom: 22mm),
  header: context {
    if counter(page).get().first() > 1 [
      #set text(size: 7.5pt, fill: luma(38%))
      #set par(justify: false, first-line-indent: 0pt)
      #align(center + horizon)[نموذج سوراو المحسّن]
      #v(-2pt)
      #line(length: 100%, stroke: 0.25pt + luma(70%))
    ]
  },
  footer: context {
    if counter(page).get().first() > 1 [
      #set text(size: 8pt, fill: luma(38%))
      #set par(justify: false, first-line-indent: 0pt)
      #align(center + horizon)[#counter(page).display("١")]
    ]
  },
)

#set text(
  font: (
    "DecoType Naskh",
    "Geeza Pro",
    "Al Bayan",
    "Damascus",
    "Arial Unicode MS",
  ),
  lang: "ar",
  dir: rtl,
  size: 10.8pt,
  fill: rgb("#1d1712"),
)

#set par(justify: true, leading: 0.76em, first-line-indent: 1em)
#set heading(numbering: none)
#set-bracket(true)

#show heading.where(level: 1): it => [
  #pagebreak(weak: true)
  #v(0.45cm)
  #align(center)[#line(length: 58%, stroke: 0.45pt + rgb("#80642e"))]
  #v(0.22cm)
  #align(center)[
    #set par(justify: false, first-line-indent: 0pt)
    #text(size: 18pt, weight: "bold", fill: rgb("#80642e"))[#it.body]
  ]
  #v(0.18cm)
  #align(center)[#line(length: 30%, stroke: 0.35pt + rgb("#b8a77c"))]
  #v(0.45cm)
]

#show heading.where(level: 2): it => [
  #v(0.36cm)
  #align(center)[
    #set par(justify: false, first-line-indent: 0pt)
    #text(size: 13pt, weight: "bold", fill: rgb("#80642e"))[#it.body]
  ]
  #v(0.16cm)
]

#let section-card(title, body) = block(
  above: 0.5em,
  below: 0.7em,
  inset: (x: 0.9em, y: 0.72em),
  radius: 3pt,
  stroke: 0.45pt + rgb("#c7b98f"),
  fill: rgb("#fffdf7"),
)[
  #set par(justify: true, first-line-indent: 0pt)
  #text(size: 9.2pt, weight: "bold", fill: rgb("#80642e"))[#title]
  #v(0.25em)
  #body
]

#let ayah-block(sura, verse, label) = figure(
  kind: "ayah",
  supplement: [آية],
  caption: [#label],
  block(
    inset: (x: 0.75em, y: 0.7em),
    radius: 3pt,
    stroke: 0.45pt + rgb("#98b8ad"),
    fill: rgb("#f7fbf8"),
  )[
    #set par(justify: false, first-line-indent: 0pt, leading: 0.9em)
    #align(center)[
      #text(size: 13pt, fill: rgb("#224f43"))[
        #quran(sura: sura, verse: verse)
      ]
    ]
  ],
)

#let quote-block(source, body) = block(
  breakable: false,
  above: 0.45em,
  below: 0.65em,
  inset: (right: 0.78em, left: 0.7em, y: 0.45em),
  stroke: (right: 1.2pt + rgb("#80642e")),
)[
  #set par(justify: true, first-line-indent: 0pt)
  #text(size: 9.7pt)[#body]
  #v(0.22em)
  #align(left)[#text(size: 8pt, fill: luma(42%))[#source]]
]

#let matn-block(body) = block(
  breakable: false,
  above: 0.55em,
  below: 0.75em,
  inset: (x: 0.5em, y: 0.5em),
)[
  #set par(justify: true, first-line-indent: 0pt, leading: 0.9em)
  #align(center)[
    #text(size: 12pt, weight: "regular", fill: rgb("#15110d"))[#body]
  ]
]

#let poem-block(body) = block(
  breakable: false,
  above: 0.45em,
  below: 0.65em,
  inset: (x: 1em, y: 0.45em),
)[
  #set par(justify: false, first-line-indent: 0pt, leading: 1em)
  #align(center)[#body]
]

#let surau-diagram() = figure(
  kind: "diagram",
  supplement: [مخطط],
  caption: [مسار تحويل النص من PDF إلى طبعة حديثة قابلة للاستشهاد],
  align(center)[
    #set text(size: 8.5pt, fill: rgb("#1d1712"))
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

#let qr-citation(id, label) = figure(
  kind: "qr",
  supplement: [رمز],
  caption: [#label],
  align(center)[
    #qrcode(
      "surau://books/afdhalush-shalawat/passages/" + id,
      quiet-zone: true,
      options: (ec-level: "m"),
    )
  ],
)

#let glossary-ref(term) = text(fill: rgb("#80642e"), weight: "bold")[#term]

#let glossary-table() = [
  #set par(justify: false, first-line-indent: 0pt)
  #set table(
    stroke: (x, y) => if y == 0 { 0.45pt + rgb("#80642e") } else { 0.25pt + rgb("#ded5ba") },
    fill: (x, y) => if y == 0 { rgb("#f7f1df") } else if calc.odd(y) { rgb("#fffdf7") },
    inset: (x: 0.55em, y: 0.45em),
  )
  #table(
    columns: (1fr, 2.2fr),
    table.header[
      #text(weight: "bold", fill: rgb("#80642e"))[المصطلح]
    ][
      #text(weight: "bold", fill: rgb("#80642e"))[المعنى التحريري]
    ],
    [الصلاة على النبي],
    [ذكر تعبدي يتضمن سؤال الرحمة والتعظيم للنبي صلى الله عليه وسلم.],
    [الاستشهاد],
    [رابط ثابت إلى المقطع العربي والصفحة في الطبعة المعتمدة.],
    [وسم دلالي],
    [بيان نوع النص: آية، حديث، دعاء، اقتباس، شعر، أو ملاحظة محرر.],
  )
]

#align(center)[
  #v(1.2cm)
  #text(size: 22pt, weight: "bold", fill: rgb("#80642e"))[
    أفضل الصلوات على سيد السادات
  ]
  #v(0.35cm)
  #line(length: 40%, stroke: 0.45pt + rgb("#80642e"))
  #v(0.65cm)
  #text(size: 12pt)[نموذج طبعة حديثة مدعومة بالوسوم الدلالية]
  #v(1cm)
  #text(size: 8.5pt, fill: luma(40%))[
    هذا الملف لا يغيّر الطبعة الحالية. هدفه اختبار الحزم والمكوّنات قبل دمجها في pipeline.
  ]
]

#pagebreak()

= نموذج الوسوم

#section-card[الفكرة][
  نريد أن يبقى المتن العربي أصلاً ثابتاً، ثم تُضاف إليه وسوم دلالية قابلة للمراجعة:
  آية، حديث، دعاء، اقتباس، شعر، حاشية تعليمية، ورابط استشهاد. عندئذٍ يستطيع
  القارئ رؤية كتاب أجمل، بينما تستطيع المنصة إنتاج API وRAG وGraph من المصدر نفسه.
]

#surau-diagram()

== آية قرآنية

في موضع الاستشهاد بالآية يمكن أن يعتمد المحرر على حزمة القرآن بدل نسخ النص يدوياً.

#ayah-block(33, 56)[الأحزاب ٣٣:٥٦]

#note(counter: none)[
  هذه الحاشية مثال لحزمة `marginalia`: مكان مناسب لتعليق تعليمي قصير لا يدخل في المتن الأصلي.
]

النص المحيط بالآية يبقى في سياقه، أما الآية نفسها فتُعامل كعنصر مستقل له مرجع واضح
وحالة مراجعة خاصة به.

== متن الصلاة

#matn-block[
اللَّهُمَّ صَلِّ عَلَى مُحَمَّدٍ وَعَلَى آلِ مُحَمَّدٍ وَعَلَى أَهْلِ بَيْتِهِ.
]

#quote-block[منسوب إلى الشرح][
هذه الصلاة مثال لمتن تعبدي يمكن تمييزه عن الشرح المحيط به. عند تصدير API يمكن أن يحمل
المقطع `role: matn`، وعند الطباعة يظهر بفسحة أكبر وتوازن بصري أوضح.
]

== شعر وقصيدة

#poem-block[
يا رب صلّ على النبي وآله \
ما لاح برق في الدجى وتبسّما
]

== استشهاد حي

#section-card[رابط المقطع][
يمكن وضع QR في بداية الفصل أو نهاية الصفحة لفتح المقطع في التطبيق، مع بقاء الاستشهاد
المطبوع قابلاً للقراءة دون هاتف.
]

#qr-citation("ASH-00009")[QR لمقطع ASH-00009 في قاعدة سوراو]

#pagebreak()

= مسرد اصطلاحي

في النص التعليمي يمكن الإشارة إلى #glossary-ref[الصلاة على النبي] أو
#glossary-ref[الاستشهاد] أو #glossary-ref[وسم دلالي]. جرّبت حزمة `glossarium`
أثناء العمل، لكنها تحتاج renderer خاص للاتجاه العربي؛ لذلك هذا prototype يستعمل
مسرد سوراو اليدوي إلى أن نربطه لاحقاً بالـ API.

#v(0.5em)
#glossary-table()

#pagebreak()

= نموذج ثنائي اللغة

#section-card[ملاحظة][
للإصدار العربي فقط لا نحتاج حزمة bidi. لكن عند بناء طبعة عربية-إندونيسية أو
عربية-إنجليزية، سنختبر `bidi-flow` أو `auto-bidi` في ملف مستقل لأن اتجاه الفقرات
والأرقام والهوامش يصبح حساساً.
]

#[
  #set text(lang: "id", dir: ltr, font: ("Libertinus Serif", "Times New Roman"), size: 9.5pt)
  #set par(justify: true, first-line-indent: 0pt, leading: 0.82em)
  Translation layer should remain separate from the Arabic anchor. The printed edition may show
  a bilingual explanation, but the public citation should still point to the canonical Arabic
  passage and the selected Surau edition page.
]
