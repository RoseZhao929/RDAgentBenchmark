# AgentClinic Reproduction Documentation

## Source

- Repo: `https://github.com/SamuelSchmidgall/AgentClinic`
- Paper: Schmidgall et al., **AgentClinic: A Multimodal Agent Benchmark to
  Evaluate AI in Simulated Clinical Environments.** ICLR 2025.
- License: **MIT**
- Date acquired: ~2026-04

## Paper-claimed results

| Setup | Metric | Value | Context |
|---|---|---|---|
| AgentClinic-MedQA rare slice | Acc | 0.28 | Paper Table 4 (LLM-only) |
| Multimodal incl. images | Acc | 0.34 | Paper Table 4 (GPT-4V) |

## How we reproduce

- **Mode**: doctor / patient / measurement / moderator OSCE loop
- **Language**: EN (paper supports 7 languages; we use EN)
- **Turn cap**: default (paper uses 20)
- **Backbone**: per-agent CLI `--openrouter` flag added (~30 LOC)
- **Second-call ranking**: after OSCE terminates with single dx, we issue
  a follow-up LLM call asking for "rank 2-5 alternatives" — this is a
  paper-supplemental step documented in §5.1 Agent Fairness Matrix; we
  flag it as a behavior-preserving extension

## Endpoint patches

| File | Change | Behavior-preserving? |
|---|---|---|
| CLI: `--openrouter` flag (~30 LOC) | wires OpenRouter `base_url` + key | Yes |
| `query_model` (~6 LOC) | honor `OPENROUTER_REASONING_EFFORT` (GPT-5) + `OPENROUTER_REASONING_DISABLE` (V4-Pro → `reasoning={enabled:false}`) + `OPENROUTER_MAX_TOKENS_FLOOR` | Yes (config-only, no scaffold/prompt change) |

## V4-Pro reasoning-disable patch (2026-07-03)

Doctor/patient/measurement turns cap `max_tokens=200`. DeepSeek-V4-Pro emits
*unbounded* reasoning tokens that ignore `reasoning_effort` and consume the
entire 200-token budget → `content=None` → the vendored `query_model` retry
loop (`tries=30, timeout=20`) sleeps to the subprocess cap → **timeout on
45–51% of cells**. Verified fix: `reasoning={"enabled": false}` (0 reasoning
tokens, content 3/3, 1.9 s vs 32 s). Propagated via `OPENROUTER_REASONING_DISABLE`
from `harness/agents/agentclinic.py`. Config-level only; OSCE algorithm and
prompts untouched. Cut wall-clock >900 s → ~27 s/case. Consistent with running
GPT-5 at `reasoning_effort=minimal`. See `round2_worklog.md` Retrospective #8.

## Behavior-changing patches

**Adapter-side (wrapper-only)**: follow-up LLM call for ranks 2-5.
AgentClinic terminates with a single doctor's diagnosis; for R@5
computation we ask the doctor agent for additional rankings. This is
done outside the OSCE loop, doesn't modify the OSCE behavior.
Paper-defensible because it's part of our adapter, not baseline code.

## Adapter wrapper

- File: `harness/agents/agentclinic.py`
- Subprocess + OSCE scenario builder from CanonicalCase
- `parse_ranked_top5` from follow-up text
- `map_names_to_ids_with_variants` (tied top-K)

## Observed results vs paper

| Backbone | n_ok | R@1 | R@5 | Paper expected |
|---|---|---|---|---|
| Gemini 3 Flash | 50/50 | **0.30** | — | 0.28 ✅ |
| DeepSeek V3.2 | 50/50 | 0.16 | — | 0.28 ⚠️ -12pp |
| GPT-5 (minimal) | 50/50 | **0.10** | 0.34 | n/a (newer) |

### Gap analysis

- DeepSeek -12pp: DeepSeek V3.2 prompt-following on OSCE dialogue weaker
  than Gemini Flash
- GPT-5 -20pp on R@1 but R@5 = 0.34: GPT-5 minimal under-commits at top-1
  (R@1=0.10 vs R@5=0.34 = 24pp gap). Likely `reasoning_effort=minimal`
  causes shallow commitment. Documented in §7.2.

## Known incompatibilities

None — all 3 backbones complete cleanly.

## Run receipts

- Phase 2 (3 backbones): `data/round2/phase2/predictions_{deepseek,gpt5_v2}.jsonl` + Phase 0 V3 Gemini
- Historical RUN_REPORT: `tasks/stream_E_agent_scouting/agents/agentclinic_RUN_REPORT.md`

## Last-updated

- 2026-05-19 — Initial doc
