// Surau enhanced optimized layout test.
// This file intentionally stays separate from surau-v0 production output.

#import "@preview/naifs-islamic-research-toolkit:0.1.0": quran, set-bracket
#import "@preview/fletcher:0.5.8" as fletcher: diagram, node, edge
#import "@preview/zebra:0.1.0": qrcode

#set document(
  title: "Afdhalush Shalawat - Enhanced Optimized",
  author: "Surau",
)

#set page(
  paper: "a5",
  binding: right,
  margin: (left: 16mm, right: 16mm, top: 16mm, bottom: 20mm),
  header: context {
    if counter(page).get().first() > 1 [
      #set text(size: 7.5pt, fill: luma(38%))
      #set par(justify: false, first-line-indent: 0pt)
      #align(center + horizon)[نموذج سوراو المحسّن المضغوط]
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
  size: 10.6pt,
  fill: rgb("#1d1712"),
)

#set par(justify: true, leading: 0.73em, first-line-indent: 0.9em)
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
  above: 0.38em,
  below: 0.55em,
  inset: (x: 0.72em, y: 0.55em),
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
    inset: (x: 0.62em, y: 0.56em),
    radius: 3pt,
    stroke: 0.45pt + rgb("#98b8ad"),
    fill: rgb("#f7fbf8"),
  )[
    #set par(justify: false, first-line-indent: 0pt, leading: 0.9em)
    #align(center)[
        #text(size: 12.2pt, fill: rgb("#224f43"))[
        #quran(sura: sura, verse: verse)
      ]
    ]
  ],
)

#let quote-block(source, body) = block(
  breakable: false,
  above: 0.34em,
  below: 0.5em,
  inset: (right: 0.62em, left: 0.56em, y: 0.36em),
  stroke: (right: 1.2pt + rgb("#80642e")),
)[
  #set par(justify: true, first-line-indent: 0pt)
  #text(size: 9.45pt)[#body]
  #v(0.22em)
  #align(left)[#text(size: 8pt, fill: luma(42%))[#source]]
]

#let matn-block(body) = block(
  breakable: false,
  above: 0.42em,
  below: 0.58em,
  inset: (x: 0.38em, y: 0.35em),
)[
  #set par(justify: true, first-line-indent: 0pt, leading: 0.9em)
  #align(center)[
    #text(size: 11.55pt, weight: "regular", fill: rgb("#15110d"))[#body]
  ]
]

#let poem-block(body) = block(
  breakable: false,
  above: 0.34em,
  below: 0.5em,
  inset: (x: 0.72em, y: 0.32em),
)[
  #set par(justify: false, first-line-indent: 0pt, leading: 1em)
  #align(center)[#body]
]

#let learning-note(body) = block(
  above: 0.3em,
  below: 0.55em,
  inset: (x: 0.64em, y: 0.42em),
  radius: 3pt,
  stroke: 0.35pt + rgb("#d7caa4"),
  fill: rgb("#fffdf7"),
)[
  #set par(justify: true, first-line-indent: 0pt, leading: 0.74em)
  #text(size: 8.8pt, fill: luma(35%))[#body]
]

#let surau-diagram() = figure(
  kind: "diagram",
  supplement: [مخطط],
  caption: [مسار تحويل النص من الملف الخام إلى طبعة حديثة قابلة للاستشهاد],
  align(center)[
    #set text(size: 8.5pt, fill: rgb("#1d1712"))
    #fletcher.diagram(
      cell-size: 15mm,
      node-stroke: 0.45pt + rgb("#80642e"),
      node-fill: rgb("#fffdf7"),
      edge-stroke: 0.55pt + rgb("#80642e"),
      fletcher.node((0, 0), align(center)[ملف خام]),
      fletcher.node((1, 0), align(center)[متن منظّف]),
      fletcher.node((2, 0), align(center)[وسوم دلالية]),
      fletcher.node((3, 0), align(center)[صفّ طباعي]),
      fletcher.node((4, 0), align(center)[طبعة واستشهاد]),
      fletcher.edge((0, 0), (1, 0), "->"),
      fletcher.edge((1, 0), (2, 0), "->"),
      fletcher.edge((2, 0), (3, 0), "->"),
      fletcher.edge((3, 0), (4, 0), "->"),
    )
  ],
)

#let qr-citation(id, label, size: 20mm) = figure(
  kind: "qr",
  supplement: [رمز],
  caption: [#label],
  align(center)[
    #qrcode(
      "surau://books/afdhalush-shalawat/passages/" + id,
      quiet-zone: true,
      width: size,
      background-fill: white,
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
  #v(1cm)
  #text(size: 22pt, weight: "bold", fill: rgb("#80642e"))[
    أفضل الصلوات على سيد السادات
  ]
  #v(0.35cm)
  #line(length: 40%, stroke: 0.45pt + rgb("#80642e"))
  #v(0.65cm)
  #text(size: 12pt)[نموذج طبعة حديثة مدعومة بالوسوم الدلالية]
  #v(0.8cm)
  #text(size: 8.5pt, fill: luma(40%))[
    هذا الملف لا يغيّر الطبعة الحالية. هدفه اختبار نسخة أكثر اقتصاداً في الهوامش قبل دمجها في خط المعالجة.
  ]
]

#pagebreak()

= نموذج الوسوم

#section-card[الفكرة][
  نريد أن يبقى المتن العربي أصلاً ثابتاً، ثم تُضاف إليه وسوم دلالية قابلة للمراجعة:
  آية، حديث، دعاء، اقتباس، شعر، حاشية تعليمية، ورابط استشهاد. عندئذٍ يستطيع
  القارئ رؤية كتاب أجمل، بينما تستطيع المنصة إنتاج واجهة بيانات، ونظام سؤال وجواب،
  وشبكة معرفية من المصدر نفسه.
]

#surau-diagram()

== آية قرآنية

في موضع الاستشهاد بالآية يمكن أن يعتمد المحرر على حزمة القرآن بدل نسخ النص يدوياً.

#ayah-block(33, 56)[الأحزاب ٣٣:٥٦]

#learning-note[
  هذه ملاحظة تعليمية داخلية مختصرة: مكان مناسب لتعليق لا يدخل في المتن الأصلي.
]

النص المحيط بالآية يبقى في سياقه، أما الآية نفسها فتُعامل كعنصر مستقل له مرجع واضح
وحالة مراجعة خاصة به.

== متن الصلاة

#matn-block[
اللَّهُمَّ صَلِّ عَلَى مُحَمَّدٍ وَعَلَى آلِ مُحَمَّدٍ وَعَلَى أَهْلِ بَيْتِهِ.
]

#quote-block[منسوب إلى الشرح][
هذه الصلاة مثال لمتن تعبدي يمكن تمييزه عن الشرح المحيط به. عند تصدير البيانات يمكن
أن يُوسم المقطع بأنه من المتن، وعند الطباعة يظهر بفسحة أكبر وتوازن بصري أوضح.
]

== شعر وقصيدة

#poem-block[
يا رب صلّ على النبي وآله \
ما لاح برق في الدجى وتبسّما
]

== استشهاد حي

#section-card[رابط المقطع][
يمكن وضع رمز استشهاد في بداية الفصل أو نهاية الصفحة لفتح المقطع في التطبيق، مع بقاء
الاستشهاد المطبوع قابلاً للقراءة دون هاتف.
]

#qr-citation("ASH-00009", size: 20mm)[رمز استشهاد لمقطع من قاعدة سوراو]

#pagebreak()

= مسرد اصطلاحي

في النص التعليمي يمكن الإشارة إلى #glossary-ref[الصلاة على النبي] أو
#glossary-ref[الاستشهاد] أو #glossary-ref[وسم دلالي]. جرّبنا حزمة مسارد جاهزة
أثناء العمل، لكنها تحتاج ضبطاً خاصاً للاتجاه العربي؛ لذلك تستعمل هذه النسخة
مسرد سوراو اليدوي إلى أن نربطه لاحقاً بواجهة البيانات.

#v(0.5em)
#glossary-table()

#pagebreak()

= ملاحظة للطبعات متعددة اللغة

#section-card[ملاحظة][
للإصدار العربي الخالص لا نحتاج إظهار مصطلحات أعجمية داخل المتن. أما عند بناء طبعة
عربية-إندونيسية أو عربية-إنجليزية، فينبغي أن تبقى الترجمة في طبقة منفصلة، وأن
يشير الاستشهاد العام إلى المقطع العربي والصفحة المعتمدة في طبعة سوراو.
]
