# LIRICAL Reproduction Documentation

## Source

- Repo: `https://github.com/TheJacksonLaboratory/LIRICAL`
- Paper: Robinson et al., **LIRICAL: Likelihood Ratio Interpretation of
  Clinical AbnormaLities.** *AJHG* 2020.
- License: **Apache 2.0**
- Date acquired: ~2026-04
- Version: distributed jar `lirical.jar`

## Paper-claimed results

| Setup | Metric | Value | Context |
|---|---|---|---|
| Phenopacket-Store, HPO-only | R@1 | ~0.42 | Paper Table 2 |
| Phenopacket-Store, HPO + VCF | R@1 | ~0.50 | Paper Table 2 |

## How we reproduce

- **Algorithm**: classical Bayesian likelihood-ratio (no LLM)
- **Backbone**: n/a (classical)
- **Mode**: HPO-only (we don't run with VCF — variants need a real VCF
  file format which we don't have for all cases)
- **Sample**: 50 case Phenopacket-Store with seed=42

## Endpoint patches

n/a — no LLM, no endpoint.

## Behavior-changing patches

**None.**

## Adapter wrapper

- File: `harness/agents/lirical.py`
- Subprocess to `java -jar lirical.jar phenopacket -p <phenopacket.json>`
- Output: TSV of disease likelihoods
- Parsing: take top-K from TSV, map disease names to ORPHA/OMIM

## Observed results vs paper

| Setup | Backbone | n_ok | R@1 | R@5 | Paper expected |
|---|---|---|---|---|---|
| HPO-only (gold HPO mode) | n/a | 50/50 | **0.40** | 0.48 | ~0.42 ✅ |

## Known incompatibilities

None — classical baseline, fully reproducible.

## Run receipts

- Phase 0 V3: `data/round2/phase0/predictions_v3.jsonl`
- Historical RUN_REPORT: `tasks/stream_E_agent_scouting/agents/lirical_RUN_REPORT.md`

## Last-updated

- 2026-05-19 — Initial doc

## Per-dataset compatibility (2026-05-19 update)

| Dataset | HPO available | LIRICAL runnable |
|---|---|---|
| Phenopacket-Store | ✅ | ✅ |
| RareBench HF | ✅ | ✅ |
| RareArena RDS | ❌ free-text | ❌ skip via `phase4a_runner.NO_HPO_DATASETS` |
| MIMIC-IV diverse | ❌ | ❌ skip |
