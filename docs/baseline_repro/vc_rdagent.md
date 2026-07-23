# VC-RDAgent Reproduction Documentation

## Source

- Repo: not public — vendored at `agents/vc_rdagent/`
- Paper: Chen et al., **VC-RDAgent: Variant- and Phenotype-Conditional Rare
  Disease Diagnosis with Offline IC + Poincaré + LR Fusion.**
- License: **No LICENSE file in upstream**. Academic fair use only.
- Date acquired: ~2026-04

## Paper-claimed results

| Setup | Metric | Value | Context |
|---|---|---|---|
| Phenopacket-Store, Stage 1 (offline) | R@1 | 0.27 | Paper Table 3 |
| Phenopacket-Store, Stage 2 (LLM-refine) | R@1 | 0.33 | Paper Table 3 |

## How we reproduce

- **Mode**: Stage 1 offline (IC + Poincaré + frequency-LR fusion) —
  **0 LLM calls**, deterministic
- **Stage 2**: not run in pilot (`use_llm_refine=False`); paper-aligned
  Stage 2 needs local Qwen3-8B or another LLM — deferred
- **Sample**: 50 case (25 PP-Store + 25 RareArena), seed=42

## Endpoint patches

| File | Change | Behavior-preserving? |
|---|---|---|
| None for Stage 1 (no LLM call) | n/a | n/a |
| Stage 2: OpenRouter wiring deferred | n/a | n/a |

## Behavior-changing patches

**None.**

## Adapter wrapper

- File: `harness/agents/vc_rdagent.py`
- Subprocess to Stage 1 pipeline
- `cost = 0` by construction (no LLM)
- Latency is the primary cost metric

## Observed results vs paper

| Backbone | Mode | n_ok | R@1 | R@5 | Paper expected |
|---|---|---|---|---|---|
| n/a (offline) | Stage 1 | 50/50 | **0.28** | 0.34 | 0.27 ✅ |
| n/a | Stage 2 | not run | n/a | n/a | 0.33 |

## Known incompatibilities

- **VC-RDAgent Stage 1 requires structured HPO input** (`CanonicalCase.gold_hpo_terms`).
  Datasets that supply no gold HPO input (RareArena RDS, legacy MIMIC-IV
  diverse) all return `agent_error: no usable gold_hpo_terms; VC-RDAgent
  Stage 1 requires HPO`. We skip vc_rdagent on these datasets via
  `phase4a_runner.NO_HPO_DATASETS = {"rarearena_rds", "mimic_diverse"}`
  (2026-05-19 fix). Stage 2 (LLM-refine) could extract HPO from text first,
  but is deferred to v2.
- Same restriction applies to LIRICAL (classical Bayesian also HPO-input).

## Per-dataset compatibility

| Dataset | HPO available | vc_rdagent runnable |
|---|---|---|
| Phenopacket-Store | ✅ structured | ✅ |
| RareBench HF (4 splits) | ✅ structured (`Phenotype` field) | ✅ |
| RareArena RDS | ❌ free-text only | ❌ skip |
| MIMIC-IV diverse | ❌ structured ICD only | ❌ skip |

## Run receipts

- Phase 0 V3: `data/round2/phase0/predictions_v3.jsonl`
- Historical RUN_REPORT: `tasks/stream_E_agent_scouting/agents/vc_rdagent_RUN_REPORT.md`

## Last-updated

- 2026-05-19 — Initial doc; Stage 2 pending
