# Round 2 Phase 1 — Pillar 5 (Reasoning Trace) Report (v2)


- Sample: 10 Phenopacket-Store cases (seed=42)
- Agents: llm_control, mdagents
- LLM judge: `google/gemini-3-flash-preview-20251217` (non-Gemini family to mitigate self-preference bias)

## Per-agent mean (1-5) scores

| Agent | n | factual | relevance | depth | faithful | mean trace_len | mean chunks | judge errors |
|---|---|---|---|---|---|---|---|---|
| `llm_control` | 50 | 4.82 | 4.53 | 3.61 | 4.90 | 1065 | 1.00 | 1 |
| `mdagents` | 20 | 4.77 | 4.65 | 4.03 | 4.36 | 19449 | 8.26 | 1 |

## Trace chunking (judge_chunks_used)

| Agent | n graded | min | max | distribution |
|---|---|---|---|---|
| `llm_control` | 49 | 1 | 1 | 1×49 |
| `mdagents` | 19 | 4 | 12 | 4×1, 6×2, 7×2, 8×7, 9×2, 10×3, 11×1, 12×1 |

## Notes

- Judge model: `google/gemini-3-flash-preview-20251217` — picked **outside** the Gemini Flash family used by the agents under test, so any residual self-preference bias would push *against* `llm_control` rather than toward it.
- Score scale: 1 (poor) → 5 (excellent) per axis. Chunked traces report the mean across chunks (so values can be fractional).
- `judge_chunks_used` > 1 indicates the trace exceeded 5 000 chars and was split into 3 000-char chunks (500-char overlap); each chunk was judged independently and the per-axis scores were averaged.
- `judge errors` counts rows where every chunk failed JSON parsing or the trace was empty.