# Round 2 Phase 1 — Pillar 1 (Phenotype Extraction) Report


- Sample: 50 Phenopacket-Store cases (seed=42, same shuffle as mini pilot).
- Backbone: `openrouter/google/gemini-3-flash-preview`
- Vignette synthesis: HPO labels embedded in a one-paragraph prose.

## Per-agent micro P/R/F1

| Agent | OK/Total | Exact-ID P | R | F1 | Phrase-norm P | R | F1 | mean lat (s) | mean phrases / hits |
|---|---|---|---|---|---|---|---|---|---|
| `deeprare` | 0/50 | (no OK rows: {'not_implemented': 50}) | | | | | | | |
| `llm_control` | 50/50 | 0.000 | 0.000 | 0.000 | 0.947 | 0.995 | 0.970 | 2.6 | 8.3 / 8.3 |
| `rdma` | 50/50 | 0.000 | 0.000 | 0.000 | 0.995 | 0.995 | 0.995 | 5.8 | 7.9 / 7.9 |

## Notes

- **Exact-ID mode**: agent's output IDs must already be HP:\d{7}. Useful for agents like DeepRare (when implemented) that emit IDs directly.
- **Phrase-norm mode**: agent's free-text phrases are passed through `harness.metrics.normalize_phrase` (hp.obo name+synonym table, rapidfuzz @ 90).
- DeepRare is logged as `not_implemented` per harness/agents/deeprare.py (Selenium dependency for OBO).