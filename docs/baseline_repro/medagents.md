# MedAgents Reproduction Documentation

## Source

- Repo: `https://github.com/gersteinlab/MedAgents` (cloned at `agents/medagents/`)
- Paper: Tang et al., **MedAgents: Large Language Models as Collaborators for
  Zero-shot Medical Reasoning.** ACL 2024 Findings.
- License: **No LICENSE file in upstream**. Academic fair use only.
- Date acquired: ~2026-04

## Paper-claimed results

| Setup | Metric | Value | Context |
|---|---|---|---|
| MedQA-Rare, syn_verif, GPT-3.5 | Acc | 0.32 | Paper Table 2 |
| MedMCQA, syn_verif, GPT-3.5 | Acc | 0.57 | Paper Table 2 |

## How we reproduce

- **Bypass MCQA-locked `run.py`** — directly call
  `api_handler.get_output_multiagent` with paper's "3 domain experts +
  Chief MO synthesis" pipeline
- **Backbone**: openai-compat via OpenRouter (`openai==0.27` Azure-pinned
  upstream; patched ~25 LOC for OpenRouter base_url)
- **Sample**: 50 case (25 PP-Store + 25 RareArena), seed=42

## Endpoint patches (allowed: wiring only)

| File | Change | Behavior-preserving? |
|---|---|---|
| `api_handler.py` | replace Azure-pinned `openai==0.27` calls with OpenRouter base_url + key from env | Yes |
| `api_utils.py` (~6 LOC) | honor `OPENROUTER_REASONING_EFFORT` / `OPENROUTER_REASONING_DISABLE` / `OPENROUTER_MAX_TOKENS_FLOOR` | Yes (config-only) |
| `requirements.txt` | drop `torch==2.0.0` pin (not available on py3.13; not imported in our code path); unpin `nltk/numpy/rouge-score` | Yes (compat only) |

## Behavior-changing patches

**None.** (Reasoning-disable below is a backbone config knob, not an algorithm change.)

## V4-Pro reasoning-disable patch (2026-07-03)

The synthesiser call caps `max_tokens=600` (intermediate stages 50/300).
DeepSeek-V4-Pro's unbounded reasoning consumes the whole budget → empty
synthesiser output → `"No ranked lines"` **parser_error on 34–45% of cells**.
`reasoning_effort=minimal` is ignored by V4-Pro; only `reasoning={"enabled":
false}` works (verified). Propagated via `OPENROUTER_REASONING_DISABLE` from
`harness/agents/medagents.py`; the MedAgents algorithm/prompts are untouched.
Same reasoning-off config as GPT-5-minimal. See `round2_worklog.md`
Retrospective #8.

## Adapter wrapper

- File: `harness/agents/medagents.py`
- Subprocess to `agents/medagents/.venv/bin/python` with `run.py`
  bypassed; directly invokes `get_output_multiagent` with custom prompt
- Output parsing: `parse_ranked_top5` (section-aware + prose filter)
- ID mapping: `map_names_to_ids_with_variants` (tied top-K)

## Observed results vs paper

| Backbone | n_ok | R@1 | R@5 | Paper expected |
|---|---|---|---|---|
| Gemini 3 Flash | 50/50 | **0.36** | — | 0.32 ✅ |
| DeepSeek V3.2 | 50/50 | **0.36** | — | 0.32 ✅ |
| GPT-5 (minimal) | 50/50 | **0.28** | 0.38 | n/a |

GPT-5 -8pp may be `reasoning_effort=minimal` impact (paper used reasoning-on
LLMs by default). Documented in §5.2 methods note.

## Known incompatibilities

### DeepSeek V4-Flash empty-content + timeout on RareBench/MIMIC (2026-05-28)

During the Phase 4c N=500 expansion the `medagents × deepseek-v4-flash` cells
on **RareBench** and **MIMIC** showed a high `parser_error` rate (rarebench
~329, mimic ~598 of the re-attempted records), while the same cell on
**PP-Store** and **RareArena** was clean (<5% errors).

**Root cause (confirmed by re-running failed cases):** the failing records all
had an *empty* `raw_response_excerpt` (`final=""`). The synthesiser
(`api_utils.get_output_multiagent`) returned an HTTP-200 response whose
`content` was the empty string. Upstream only retries on *exceptions*, so an
empty-but-successful response slipped through as `final=""` → parser_error.
This is a transient backbone behaviour: re-running the identical case usually
succeeds.

**Fix (wrapper-only, baseline algorithm untouched):**
`harness/agents/medagents.py` now re-invokes the whole subprocess up to
`_MAX_EMPTY_RETRIES=2` (3 total attempts) **when `final` is empty**. It does
NOT retry when `final` is non-empty but unparseable (that is a genuine format
issue, still logged as `parser_error`). The MedAgents prompts/algorithm are
unchanged.

**Spot-check (5 previously-failed RareBench cases, after fix):** 3/5 → `ok`.
The 2 that stayed failed are genuine method×backbone behaviours, **not** the
empty-content bug:
- `rarebench_LIRICAL_00323` → `timeout` (>300s subprocess cap; long input).
- `rarebench_MME_00024` → `parser_error` "Empty synthesiser output after 3
  attempts" — V4-Flash returns empty even after retries (persistent refusal).

So the retry recovers transient empties (~60% of failures here) without
masking the real timeout / persistent-empty tail, which is reported honestly.

## Run receipts

- Phase 0 V3: `data/round2/phase0/predictions_v3.jsonl`
- Phase 2 (DeepSeek + GPT-5): `data/round2/phase2/predictions_{deepseek,gpt5_v2}.jsonl`
- Historical RUN_REPORT: `tasks/stream_E_agent_scouting/agents/medagents_RUN_REPORT.md`

## Last-updated

- 2026-05-19 — Initial doc; 3-backbone pilot complete
- 2026-05-28 — Added V4-Flash empty-content root-cause + wrapper retry fix
  (`_MAX_EMPTY_RETRIES`); 3/5 spot-check recovery. Re-run of medagents
  V4-Flash RareBench/MIMIC cells pending user decision (slow: retry ×3 on
  ~930 failed cases).
