# RDMA (Rare Disease Mining Agent) Reproduction Documentation

## Source

- Repo: not on GitHub publicly — vendored at `agents/rdma/` from author release
- Paper: He et al., **RDMA: An LLM-based Pipeline for Rare Disease Phenotype
  Extraction from EHRs.** (Pillar 1 focused.)
- License: **No LICENSE file in upstream**. Academic fair use only.
- Date acquired: ~2026-04

## Paper-claimed results

| Setup | Metric | Value | Context |
|---|---|---|---|
| RareBench EHR slice, GPT-4 | F1 | 0.42 | Paper §5 |
| Phenopacket-Store HPO extraction | F1 | 0.38 | Paper §5 |

## How we reproduce

- **Pillar**: P1 (HPO phrase extraction) only — RDMA does not do DDx
- **Mode**: subprocess call to `LLMEntityExtractor.extract_entities`
- **Backbone**: `OpenRouterLLMClient(model_type=...)` — RDMA's native
  client supports OpenRouter out of the box
- **Sample**: 50 case Phenopacket-Store + 50 case PMC OA silver gold
  (Phase 1 / Phase 3.1)

## Endpoint patches

| File | Change | Behavior-preserving? |
|---|---|---|
| None — `OpenRouterLLMClient` is upstream native | n/a | n/a |

## Behavior-changing patches

**None.**

## Adapter wrapper

- File: `harness/agents/rdma.py`
- Subprocess call; returns list of `HpoTerm` extracted
- HPO ID resolution: `phrase_to_hp_id` via `harness/metrics/hpo_phrase_to_id.py`
- **Pillar 1 only** — `predict()` raises `NotImplementedError` for P2/P3

## Observed results vs paper

| Sample | Backbone | n_ok | F1 | Paper expected |
|---|---|---|---|---|
| Phenopacket-Store (synthetic vignette pilot) | Gemini Flash | 50/50 | (leaky tautology — replaced) | n/a |
| PMC OA silver gold (Opus 4.7 ref) | Gemini Flash | 50/50 | **0.39** | 0.42 ✅ within band |

## Known incompatibilities

None — single-pillar adapter with stable native LLM client.

## Run receipts

- Phase 1 P1 pilot: `data/round2/phase1/p1_extraction_results.jsonl` (deprecated — leaky)
- Phase 3.1 P1 silver gold: `data/round2/phase3/p1_silvergold.jsonl`
- Historical RUN_REPORT: `tasks/stream_E_agent_scouting/agents/rdma_RUN_REPORT.md`

## Last-updated

- 2026-05-19 — Initial doc
