# Round 2 Phase 1 — Pillar 5 (Reasoning Trace) Report


- Sample: 10 Phenopacket-Store cases (seed=42)
- Agents: deeprare, llm_control, maidxo, mdagents
- LLM judge: Gemini Flash (`google/gemini-3-flash-preview`)

## Per-agent mean (1-5) scores

| Agent | n | factual | relevance | depth | faithful | mean trace_len (chars) | judge errors |
|---|---|---|---|---|---|---|---|
| `deeprare` | 10 | 1.70 | 1.40 | 1.90 | 1.70 | 18429 | 0 |
| `llm_control` | 10 | 4.70 | 4.50 | 3.60 | 4.90 | 986 | 0 |
| `maidxo` | 10 | nan | nan | nan | nan | 0 | 10 |
| `mdagents` | 10 | 5.00 | 5.00 | 4.00 | 5.00 | 337 | 8 |

## Notes

- Judge model is Gemini Flash — **same backbone as the agents under test**, so any self-preference bias should appear as systematically elevated scores for `llm_control` (single Gemini Flash call) relative to scaffolded agents.
- Score scale: 1 (poor) → 5 (excellent) per axis.
- `judge errors` counts rows where the judge JSON parse failed or the trace was empty.