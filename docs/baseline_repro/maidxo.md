# MAI-DxO Reproduction Documentation

## Source

- Repo: `https://github.com/SHB-yh/MaiDxOrchestrator` (community port)
- Paper: Microsoft AI, **The Diagnosis-Orchestration Model.** *NEJM AI*
  2025.
- License: **MIT** (community port)
- Date acquired: ~2026-04

## Paper-claimed results

| Setup | Metric | Value | Context |
|---|---|---|---|
| NEJM clinicopath cases, no_budget mode, GPT-4o | Acc | 0.45 | Paper Table 2 |
| With budget=$5000, GPT-4o | Acc | 0.42 | Paper Table 2 |

## How we reproduce

- **Mode**: `no_budget` with `max_iterations=3` — paper's primary config
- **Backbone**: LiteLLM router → OpenRouter (no source edit; LiteLLM is
  native OpenRouter-compatible)
- **Reasoning effort propagation**: `OPENROUTER_REASONING_EFFORT=minimal`
  for GPT-5 / o-series
- **Sample**: 50 case (25 PP-Store + 25 RareArena), seed=42

## Endpoint patches

| File | Change | Behavior-preserving? |
|---|---|---|
| None — LiteLLM handles OpenRouter natively | n/a | n/a |

## Behavior-changing patches

**Adapter-side noise filter** (`harness/agents/maidxo.py:_NOISE_PATTERNS`,
13 regex patterns):

- Drops candidates matching:
  - "Unable to establish...", "Cannot...", "Failure to..."
  - mmHg / bpm / mg/dL / SpO2 / hemoglobin / DLCO / LVEF / FEV1 / FVC
  - Bare numbers, sentence fragments
- **Why**: MAI-DxO panel on DeepSeek V3.2 (and occasionally Gemini)
  emits **measurement values** as ranked candidates (e.g.,
  `["DLCO", "blood pressure 96/59 mmHg"]`). These are vitals, not
  disease names.
- **Behavior-changing because**: we filter the agent's output before
  evaluation. The agent's internal panel is untouched.
- **Paper-defensible**: documented in §5.1 Agent Fairness Matrix Row 4.
  The patch is in our adapter (`harness/agents/`), not in MAI-DxO's
  source.

**Adapter-side fuzzy fallback** (lines 502-554): re-maps prose disease
names to ORPHA via Orphadata when MAI-DxO's `differential_diagnosis`
output is empty / has only the `final_diagnosis` populated. Wrapper-only.

## Adapter wrapper

- File: `harness/agents/maidxo.py`
- LiteLLM-based subprocess; agent_extra: `{mode, max_iterations,
  timeout_seconds, budget_usd, request_delay}`
- `ranked_predictions` derived from `final_diagnosis` + top-K from
  `differential_diagnosis` dict (if present)
- Noise filter applied post-hoc

## Observed results vs paper

| Backbone | Mode | n_ok | R@1 | R@5 | Paper expected |
|---|---|---|---|---|---|
| Gemini 3 Flash | no_budget, max_iter=3 | 50/50 | 0.14 | — | 0.45 ⚠️ -31pp |
| DeepSeek V3.2 | no_budget, max_iter=3 | 29/50 (some incomplete) | 0.00 | — | 0.45 ⚠️ catastrophic |
| GPT-5 (minimal) instant | max_iter=1 | 5/5 | "No diagnosis formulated" × 5 | — | n/a — documented degenerate (paper §3.2) |
| GPT-5 (minimal) question_only | — | 5/5 timeout 600s | — | — | n/a |
| GPT-5 (minimal) no_budget max_iter=2, 1200s cap | — | 1/3 ok 728s, returns "Diagnosis not reached" | — | — | systematic incompat |

### Gap analysis (Gemini -31pp)

- Paper input = narrative-rich NEJM clinicopath case (~2000 words);
  our input = HPO list + 1-2 sentence vignette
- MAI-DxO panel's "ask the patient" mechanism degenerates when input
  already enumerates the answer (HPO list IS the answer to most "ask"
  questions)
- Panel sometimes emits measurement values as candidates (caught by
  noise filter, but still bad signal)
- Documented in §7.2 + §9 L4

## Known incompatibilities

| Backbone | Issue | Resolution |
|---|---|---|
| GPT-5 (minimal) all modes | Panel orchestration timeout / degenerate output | Documented in §9 L1 as systematic agent-backbone incompat. No fix attempted beyond modes tested (instant / question_only / no_budget max_iter=2). |
| Gemini Flash (HPO-input datasets) | `parser_error` "All ranked predictions filtered as noise / Unable to establish" — pp-store 19, rarebench 20, mimic 25 (2026-05-28 scan). | **Real method behavior, not a bug.** On HPO-list input (no live patient to interrogate) the panel often concludes "Unable to establish diagnosis" or emits only vitals/fragments, which the noise filter strips → empty ranked list. Consistent with §8.2 "MAI-DxO collapses on HPO input". **No retry** (re-running yields the same degeneration). Reported honestly. |

## Run receipts

- Phase 2: `data/round2/phase2/predictions_{deepseek,gpt5}.jsonl`
- GPT-5 mode tests (sanity): logs `/tmp/log_maidxo_{qonly,nb}.log`
- Historical RUN_REPORT: `tasks/stream_E_agent_scouting/agents/maidxo_RUN_REPORT.md`

## Last-updated

- 2026-05-19 — Initial doc; GPT-5 mode-iteration audit complete
