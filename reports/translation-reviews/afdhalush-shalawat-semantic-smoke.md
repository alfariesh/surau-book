# Translation Review: afdhalush-shalawat

This packet is for human/editorial review before bulk translation.

- Book dir: `books/afdhalush-shalawat`
- Source: `books/afdhalush-shalawat/passages.jsonl`
- Languages: `id, en`
- Passages: `3`

## Translate Missing

`en` missing `2` rows:

```bash
python3 scripts/translate_passages.py \
  --book-dir books/afdhalush-shalawat \
  --lang en \
  --id ASH-00009,ASH-00033 \
  --annotations annotations/semantic-reviewed.jsonl \
  --model deepseek-v4-pro \
  --row-deadline 300 \
  --continue-on-error
```

## Batch Index

| ID | Categories | Section | Citation | Source Chars | id | en |
| --- | --- | --- | --- | --- | --- | --- |
| `ASH-00008` | manual | مقدمة | Afdhalush Shalawat, ed. surau-v0, hlm. 6, ASH-00008. | 24 | machine_draft / ratio 2.38 | machine_draft / ratio 2.46 |
| `ASH-00009` | manual | مقدمة | Afdhalush Shalawat, ed. surau-v0, hlm. 6, ASH-00009. | 868 | machine_draft / ratio 1.95 | missing |
| `ASH-00033` | manual | القسم الأول > الفصل الثاني: في الأحاديث التي ورد فيها الترغيب في الصلاة عليه صلى الله علي… | Afdhalush Shalawat, ed. surau-v0, hlm. 13, ASH-00033. | 1642 | machine_draft / ratio 1.61 | missing |

## Side By Side

### ASH-00008

- Categories: `manual`
- Section: `مقدمة`
- Citation: `Afdhalush Shalawat, ed. surau-v0, hlm. 6, ASH-00008.`
- Source page: `7`

**Arabic Source**

```text
بسم اللّٰه الرحمن الرحيم
```

**id Translation**

- Status: `machine_draft`
- Model: `deepseek-v4-pro`
- Target chars/source ratio: `57` / `2.38`
- Arabic leak chars: `0`

```text
Dengan nama Allah Yang Maha Pengasih lagi Maha Penyayang.
```

**en Translation**

- Status: `machine_draft`
- Model: `deepseek-v4-pro`
- Target chars/source ratio: `59` / `2.46`
- Arabic leak chars: `0`

```text
In the Name of Allah, the Most Gracious, the Most Merciful.
```

### ASH-00009

- Categories: `manual`
- Section: `مقدمة`
- Citation: `Afdhalush Shalawat, ed. surau-v0, hlm. 6, ASH-00009.`
- Source page: `7`

**Arabic Source**

```text
الحمد للّٰه رب العالمين حمداً يقترن بحكمته البالغة، ويحيط بنعمه السابغة، ويخص نعمته عليّ بالإيمان والإسلام فإنها أعظم نعمه، وأن جعلني من أمة سيدنا محمد خير الأنام وجعلها خير أمّة، كما أحمده على أن صلّى هو وملائكته على هذا النبي الكريم وأمر المؤمنين بذلك تشريفاًله وتعظيماً، فقال تعالى:} إنَّ اللّٰه وَمَلاَئِكَتَهُ يُصَلُّونَ عَلَى النَّبِيِّ يَا أَيُّ هَا الَّذِينَ آمَنُوا صَلُّوا عَلَيْهِ وَسَلِّمُوا تَسْلِيمَا {، اللهم صلِّ عليه وعلى آله أفضل صلاة صليتها أو تصليها على أحد من عبادك الأبرار والمقربين، تكون صلاتك على سيدنا إبراهيم وآله مع كمالها بالنسبة إليها كالذرة بالنسبة إلى جميع العالمين، وعلى إخوانه الأنبياء الذين تقدموه في الزمان، تقدم الأمراء على السلطان، وأصحابه نجوم الهدى، وأئمة أمته ومن بهم اقتدى، وسلم اللهم عليهم تسليماًكذلك، فالكل مملوك وأنت وحدك المالك، وأشهد أن لا إله إلا اللّٰه وحده لا شريك له، وأشهد أن سيدنا محمداًنبيّه ورسوله خير نبيّ أرسله،
```

**id Translation**

- Status: `machine_draft`
- Model: `deepseek-v4-pro`
- Target chars/source ratio: `1695` / `1.95`
- Arabic leak chars: `0`

```text
Segala puji bagi Allah, Rabb semesta alam, pujian yang menyertai hikmah-Nya yang sempurna, meliputi nikmat-nikmat-Nya yang luas, dan secara khusus nikmat-Nya kepadaku berupa iman dan Islam, karena itulah nikmat-Nya yang terbesar, dan bahwa Dia menjadikanku bagian dari umat junjungan kita Muhammad, sebaik-baik manusia, dan menjadikannya umat terbaik, sebagaimana aku memuji-Nya karena Dia dan para malaikat-Nya bershalawat kepada nabi yang mulia ini, dan memerintahkan orang-orang beriman untuk bershalawat sebagai penghormatan dan pengagungan baginya, maka Allah Ta'ala berfirman: "Sesungguhnya Allah dan malaikat-malaikat-Nya bershalawat untuk Nabi. Hai orang-orang yang beriman, bershalawatlah kamu untuk Nabi dan ucapkanlah salam penghormatan kepadanya." Ya Allah, limpahkanlah shalawat kepadanya dan kepada keluarganya, shalawat terbaik yang pernah Engkau limpahkan atau akan Engkau limpahkan kepada seorang hamba-Mu yang saleh dan terdekat; dan jadikanlah shalawat-Mu kepada junjungan kita Ibrahim dan keluarganya—dengan segala kesempurnaannya—sementara shalawat ini di sisinya laksana sebutir atom di hadapan seluruh alam, serta kepada saudara-saudaranya para nabi yang mendahuluinya dalam zaman, sebagaimana para panglima mendahului sultan, dan para sahabatnya yang menjadi bintang-bintang petunjuk, para imam umatnya dan orang-orang yang mengikuti mereka, dan limpahkanlah salam, ya Allah,…
```

- Notes: `[]`
- Warnings: `["Teks asli berakhir dengan koma, menandakan kalimat belum selesai."]`

**en Translation**

_Missing._

### ASH-00033

- Categories: `manual`
- Section: `القسم الأول > الفصل الثاني: في الأحاديث التي ورد فيها الترغيب في الصلاة عليه صلى الله عليه وسلم`
- Citation: `Afdhalush Shalawat, ed. surau-v0, hlm. 13, ASH-00033.`
- Source page: `13`

**Arabic Source**

```text
قال رسول اللّٰه صلى اللّٰه عليه وسلم مَنْ صَلَّى عَلَيَّ صَلاَةً صَلَّى اللّٰه عَلَيْهِ بِهَا عَشْراً رواه مسلم. وقال صلى اللّٰه عليه وسلم صَلُّوا عَلَيَّ فَإِنَّ صَلاَتَك عَلَيَّ زَكَاةٌ لَكُمْ وَإِنَّ هَا أَضْعَافٌ مُضَاعَفَةٌ. وكان صلى اللّٰه عليه وسلم يقول صَلُّوا عَلَيَّ فَإِنَّ اللّٰه عَزَّ وَجَلَّ يُصَلِّي عَلَيْكُمْ. وقال صلى اللّٰه عليه وسلم لاَتَجْعَلُوا قَبْرِي عِيداًوَصَلُّوا عَلَيَّ فَإِنَّ صَلاَتَكُمْ تَبْلُغُنِي حَيْثُ كُنْتُمْ. وقال صلى اللّٰه عليه وسلم حَيْثُمَا كُنْتُمْ فَصَلُّوا عَلَيَّ فَإِنَّ صَلاَتَكُمْ تَبْلُغُنِي حَيْثُ كُنْتُمْ. وقال صلى اللّٰه عليه وسلم حَيْثُمَا كُنْتُمْ فَصَلُّوا عَلَيُّ فَإِنُّ صَلاَتَكُمْ تَبْلُغُنِي. وقال صلى اللّٰه عليه وسلم إِ نُّ للّٰه مَلاَئِكَةً سَيُّاحِينَ يُبَلِّغُونِي عَنْ أُمُّ تِي السَّ لاَمَ. وقال صلى اللّٰه عليه وسلم مَنْ صَلُّى عَلَيُّ بَلَغَتْنِي صَلاَتُهُ وَصَلُّيْتُ عَلَيْهِ وَكُتِبَ لَهُ سِوَى ذَلِكَ عَشْرُ حَسَنَاتٍ. وقال صلى اللّٰه عليه وسلم مَنْ صَلُّى عَلَيُّ عِنْدَ قَبْرِي سَمِعْتُهُ وَمَنْ صَلُّى عَلَيَّ غَائِباًبُلِّغْتُهُ وقال صلى اللّٰه عليه وسلم مَا مِنْ أَحَدٍ يُسَلِّمُ عَلَيُّ إِلاَّ رَدَّ اللّٰه عَلَيَّ رُوحِي حَتَّى أَرُدَّ عَلَيْهِ السَّ لاَمَ. وقال صلى اللّٰه عليه وسلم لَقِيتُ جِبْرِيلَ فَقَالَ لِي إِ نِّي أُبَشِّرُكَ أَنَّ يَقُولُ مَنِْنِي جِبْرِيلُ عَلَيْهِ السَّ لاَمُ فَقَالَ يَا مُحَمَّدُ لاَيُصَلِّي عَلَيْكَ سَلَّمَ عَلَيْكَ سَلَّمْتُ عَلَيْهِ وَمَنْ صَلَّى عَلَيْكَ صَلَّيْتُ عَلَيْهِ. وقال ص…
```

**id Translation**

- Status: `machine_draft`
- Model: `deepseek-v4-pro`
- Target chars/source ratio: `2639` / `1.61`
- Arabic leak chars: `0`

```text
Rasulullah shallallâhu ‘alaihi wa sallam bersabda: "Barangsiapa bershalawat kepadaku satu kali, maka Allah bershalawat kepadanya sepuluh kali." (HR. Muslim). Beliau shallallâhu ‘alaihi wa sallam bersabda: "Bershalawatlah kepadaku, karena sesungguhnya shalawat kalian kepadaku adalah zakat (penyuci) bagi kalian, dan sesungguhnya itu adalah pahala yang berlipat ganda." Dan beliau shallallâhu ‘alaihi wa sallam bersabda: "Bershalawatlah kepadaku, karena sesungguhnya Allah ‘Azza wa Jalla bershalawat kepada kalian." Beliau shallallâhu ‘alaihi wa sallam bersabda: "Janganlah kalian jadikan kuburanku sebagai ied (hari raya), dan bershalawatlah kepadaku, karena sesungguhnya shalawat kalian sampai kepadaku di mana pun kalian berada." Beliau shallallâhu ‘alaihi wa sallam bersabda: "Di mana pun kalian berada, bershalawatlah kepadaku, karena sesungguhnya shalawat kalian sampai kepadaku di mana pun kalian berada." Beliau shallallâhu ‘alaihi wa sallam bersabda: "Di mana pun kalian berada, bershalawatlah kepadaku, karena sesungguhnya shalawat kalian sampai kepadaku." Beliau shallallâhu ‘alaihi wa sallam bersabda: "Sesungguhnya Allah memiliki malaikat-malaikat yang berkeliling (sayyâhîn), mereka menyampaikan kepadaku salam dari umatku." Beliau shallallâhu ‘alaihi wa sallam bersabda: "Barangsiapa bershalawat kepadaku, maka shalawatnya sampai kepadaku, dan aku pun bershalawat kepadanya, serta dica…
```

- Notes: `["Pada hadis kedua, kata 'zakat' di sini bermakna penyuci atau pembersih, bukan zakat wajib."]`
- Warnings: `["Teks pada hadis ke-10 dan ke-11 tampak rusak atau tidak lengkap, sehingga terjemahan didasarkan pada teks yang terlihat."]`

**en Translation**

_Missing._
