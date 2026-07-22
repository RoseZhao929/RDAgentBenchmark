# Round 2 Phase 1 — Pillar 5 (Reasoning Trace) Report (v2)


- Sample: 10 Phenopacket-Store cases (seed=42)
- Agents: deeprare, llm_control, maidxo, mdagents
- LLM judge: `anthropic/claude-sonnet-4.5` (non-Gemini family to mitigate self-preference bias)

## Per-agent mean (1-5) scores

| Agent | n | factual | relevance | depth | faithful | mean trace_len | mean chunks | judge errors |
|---|---|---|---|---|---|---|---|---|
| `deeprare` | 10 | 2.31 | 1.33 | 2.58 | 2.72 | 21401 | 9.00 | 0 |
| `llm_control` | 10 | 4.30 | 4.50 | 3.10 | 4.50 | 986 | 1.00 | 0 |
| `maidxo` | 10 | 2.11 | 1.85 | 1.64 | 1.88 | 26972 | 10.50 | 0 |
| `mdagents` | 10 | 4.10 | 4.17 | 3.49 | 4.26 | 20034 | 8.30 | 0 |

## Trace chunking (judge_chunks_used)

| Agent | n graded | min | max | distribution |
|---|---|---|---|---|
| `deeprare` | 10 | 9 | 9 | 9×10 |
| `llm_control` | 10 | 1 | 1 | 1×10 |
| `maidxo` | 10 | 3 | 14 | 3×1, 4×1, 11×2, 12×3, 13×2, 14×1 |
| `mdagents` | 10 | 6 | 11 | 6×2, 7×1, 8×3, 9×1, 10×2, 11×1 |

## Notes

- Judge model: `anthropic/claude-sonnet-4.5` — picked **outside** the Gemini Flash family used by the agents under test, so any residual self-preference bias would push *against* `llm_control` rather than toward it.
- Score scale: 1 (poor) → 5 (excellent) per axis. Chunked traces report the mean across chunks (so values can be fractional).
- `judge_chunks_used` > 1 indicates the trace exceeded 5 000 chars and was split into 3 000-char chunks (500-char overlap); each chunk was judged independently and the per-axis scores were averaged.
- `judge errors` counts rows where every chunk failed JSON parsing or the trace was empty.