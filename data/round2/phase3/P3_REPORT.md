# Phase 3.2 — P3 (Genotype-Aware) Report


N=50 Phenopacket-Store cases (all with ≥1 variant). Backbone: `openrouter/google/gemini-3-flash-preview-20251217`


## Per-agent P3 results

| Agent | OK | P3 R@1 | Hits | Mean Lat |
|---|---|---|---|---|
| `deeprare` | 50/50 | 0.38 | 19 | 180.7s |
| `llm_control` | 0/50 | — | — | — |

## Comparison to P2 baseline (same agent, same cases, HPO-only)

Phase 0 V3 P2 R@1 numbers for the same agents (from `REPORT_FINAL.md`):

- `deeprare`: 0.22 (50 mixed cases)
- `llm_control` baseline: 0.26 (sanity check)

**If P3 R@1 > P2 R@1**, genotype channel adds signal (H2 supported).
**If P3 R@1 ≈ P2 R@1**, agent doesn't leverage variant info.