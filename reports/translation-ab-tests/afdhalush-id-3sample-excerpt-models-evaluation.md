# Translation Model Evaluation

Source report:

- `reports/translation-ab-tests/afdhalush-id-3sample-excerpt-models.json`
- `reports/translation-ab-tests/afdhalush-id-3sample-excerpt-models.md`

Samples:

- `ASH-00008`: basmalah, short devotional formula.
- `ASH-00009`: muqaddimah prose with Quran quote and salawat.
- `ASH-00367`: salawat/du'a excerpt, truncated to 1200 chars for fair comparison.

## Ranking

| Rank | Model | Verdict | Notes |
| --- | --- | --- | --- |
| 1 | `deepseek-v4-pro` | Best default for turath translation | Most faithful and natural overall. Strong on Arabic devotional prose, good Islamic terminology, no serious hallucination in the tested samples. Slow on longer passages. |
| 2 | `qwen/qwen3.6-flash` | Best fast fallback | Natural Indonesian and much faster. Good for draft/bulk translation. Occasionally paraphrases too freely and can introduce awkward theological phrasing. |
| 3 | `z-ai/glm-5.1` | Faithful but too slow/stiff | Generally careful and usable, but much slower. Indonesian is more literal and less polished than DeepSeek/Qwen. |
| 4 | `minimax/minimax-m2.7` | Not recommended for this use case | Fast, but made serious terminology mistakes around salawat/prayer, used odd Chinese-style punctuation, produced typos, and added dubious notes. |

## Latency

| Model | Success | Avg Latency | Per-Sample Latencies |
| --- | --- | --- | --- |
| `z-ai/glm-5.1` | 3/3 | 114.0s | 21.204s, 129.512s, 191.334s |
| `deepseek-v4-pro` | 3/3 | 132.1s | 5.522s, 122.599s, 268.322s |
| `minimax/minimax-m2.7` | 3/3 | 31.5s | 11.479s, 33.173s, 49.989s |
| `qwen/qwen3.6-flash` | 3/3 | 30.2s | 5.712s, 34.729s, 50.096s |

## Key Observations

`deepseek-v4-pro` handled `ASH-00009` best: it preserved sentence logic, Quran quotation, salawat language, and devotional register while staying readable in Indonesian.

`qwen/qwen3.6-flash` was the strongest speed/quality tradeoff. However, in `ASH-00009` it rendered part of the salawat setup awkwardly as "shalawat yang Dia berikan kepada diri-Nya sendiri", and in `ASH-00367` it used a looser phrase like "bermain di antara gelombang kehadiran-Mu".

`z-ai/glm-5.1` was careful but slower than expected. It is usable for selective high-value passages, but not attractive for batch translation unless latency improves.

`minimax/minimax-m2.7` should be avoided for this corpus. It mistranslated salawat-related language as "menyembah/melaksanakan solat atas Nabi", inserted non-Indonesian punctuation, and produced malformed words such as "dancelupkan".

## Recommendation

Use this routing:

```text
review-quality draft: deepseek-v4-pro
bulk first draft: qwen/qwen3.6-flash
fallback if DeepSeek/Qwen unavailable: z-ai/glm-5.1
do not use for turath translation: minimax/minimax-m2.7
```

For production translation, translate with `qwen/qwen3.6-flash` first for coverage, then retranslate or review important passages with `deepseek-v4-pro`.
