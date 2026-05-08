# Translation Model Evaluation Round 2

Source report:

- `reports/translation-ab-tests/afdhalush-id-3sample-excerpt-models-round2.json`
- `reports/translation-ab-tests/afdhalush-id-3sample-excerpt-models-round2.md`

Models:

- `openai/gpt-5.4-mini`
- `google/gemini-3.1-flash-lite-preview`
- `x-ai/grok-4.3`

Same samples as round 1:

- `ASH-00008`: basmalah.
- `ASH-00009`: muqaddimah prose.
- `ASH-00367`: salawat/du'a excerpt, truncated to 1200 chars.

## Round 2 Ranking

| Rank | Model | Verdict | Notes |
| --- | --- | --- | --- |
| 1 | `google/gemini-3.1-flash-lite-preview` | Best of round 2 | Very fast, clean Indonesian, good devotional tone. Strongest practical draft model in this batch. |
| 2 | `x-ai/grok-4.3` | Good but slower | Faithful enough and stylistically readable, but slower and slightly less polished than Gemini. |
| 3 | `openai/gpt-5.4-mini` | Fast but not safe enough here | Very fast, but left raw Arabic terms/tokens in Indonesian output, e.g. `ذلك`, `ذرة نسبت إلى جميع العالمين`, `سيدنا`, `أهل الشهود`. Needs stricter prompting or post-QA before use. |

## Latency

| Model | Success | Avg Latency | Per-Sample Latencies |
| --- | --- | --- | --- |
| `openai/gpt-5.4-mini` | 3/3 | 4.6s | 1.469s, 7.151s, 5.328s |
| `google/gemini-3.1-flash-lite-preview` | 3/3 | 2.9s | 1.288s, 3.091s, 4.406s |
| `x-ai/grok-4.3` | 3/3 | 38.3s | 10.579s, 52.509s, 51.804s |

## Combined Recommendation

After both rounds, use this routing:

```text
best quality for review/publish: deepseek-v4-pro
best fast bulk draft: google/gemini-3.1-flash-lite-preview
second fast draft option: qwen/qwen3.6-flash
fallback quality option: x-ai/grok-4.3
avoid for this corpus: minimax/minimax-m2.7
needs stricter prompt/QA before use: openai/gpt-5.4-mini
```

## Notes

`google/gemini-3.1-flash-lite-preview` is substantially faster than the earlier fast candidates and did not show the severe terminology issues seen in `minimax/minimax-m2.7`.

`openai/gpt-5.4-mini` may improve with a stricter prompt that forbids untranslated Arabic tokens except approved terms, but in this test it is not ready as-is for automated kitab translation.

`x-ai/grok-4.3` is usable, especially for a secondary pass, but it is not clearly better than `deepseek-v4-pro` in quality or Gemini in speed.
