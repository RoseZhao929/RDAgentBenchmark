# Phase 3.1 — P1 Extraction on Opus Silver Gold(non-leaky)


N=50 PMC OA cases | Backbone=openrouter/google/gemini-3-flash-preview-20251217


## Per-agent micro-averaged P/R/F1(phrase→HP-ID normalized)

| Agent | OK | Mean Prec | Mean Recall | Mean F1 | Mean Jaccard | Mean latency |
|---|---|---|---|---|---|---|
| `deeprare` | 0/50 | — | — | — | — | — |
| `llm_control` | 50/50 | 0.718 | 0.649 | 0.672 | 0.541 | 2.6s |
| `rdma` | 50/50 | 0.629 | 0.528 | 0.562 | 0.432 | 5.5s |

## What this replaces

- Phase 1 `p1_extraction_pilot.py` used `synthesize_vignette_from_hpo(case)` for Phenopacket-Store cases — phrase_f1≈1.0 was leaky tautology(LLM read its own synthesized labels).
- This pilot uses **real PMC OA case_excerpt as input** + **Opus 4.7 silver gold** as reference. Disagreement is real(Opus vs Gemini Jaccard 0.41,§Round 2 worklog).