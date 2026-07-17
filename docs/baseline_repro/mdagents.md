# MDAgents Reproduction Documentation

## Source

- Repo: `https://github.com/mitmedialab/MDAgents` (cloned at `agents/mdagents/`)
- Paper: Kim et al., **MDAgents: An Adaptive Collaboration of LLMs for Medical
  Decision-Making.** NeurIPS 2024.
- License: **No LICENSE file in upstream**. We comply with academic fair
  use (run + report numbers); we do not redistribute the code.
- Date acquired: ~2026-04

## Paper-claimed results (targets within ±5pp)

| Setup | Metric | Value | Context |
|---|---|---|---|
| MedQA-Rare, intermediate mode, GPT-4 | R@1 | 0.31–0.39 | Paper §5 |
| MedMCQA (general MC), GPT-4 | Acc | 0.71 | Paper Table 2 |

## How we reproduce

- **Mode**: `--difficulty intermediate` — 3-domain experts + Chief MO synthesis,
  matches paper §3.2 "moderate" path
- **Backbone**: openai client → OpenRouter (`OPENAI_BASE_URL`)
- **Prompt**: reformulated as "rank top-5 rare disease candidates"
  (paper assumes MCQA; for DDx we provide free-form prompt — documented
  as setup-mismatch since DDx is the eval task)
- **Sample**: 50 case (25 PP-Store + 25 RareArena), seed=42

## Endpoint patches (allowed: OpenRouter wiring)

| File | Lines | Purpose | Behavior-preserving? |
|---|---|---|---|
| `utils.py:_openai_kwargs` helper | ~10 LOC | builds OpenAI client kwargs with `base_url` from env | Yes (wiring only) |
| `utils.py:Agent.__init__` | open `else` to accept any model_info string | accepts OpenRouter model ids | Yes |
| `utils.py:Agent.chat` + `Agent.temp_responses` | replace hard-coded `gpt-4o-mini` with `self.model_info` | honour `--model` flag | Yes (bug fix in upstream) |
| `utils.py:Group / determine_difficulty / process_intermediate / process_advanced` | accept `model_info` param instead of hard-coded models | propagate backbone choice | Yes (bug fix) |
| `utils.py:setup_model` | gemini path gated by `'/'` absence | OpenRouter ids use openai-compat path | Yes |
| `utils.py:load_data` | `../data` → `./data` + fallback search | fix path bug for our run layout | Yes (bug fix) |
| `main.py` | filename sanitises `/` in model ids | filesystem compat | Yes |
| `requirements.txt`: openai upgraded 1.14.2 → 1.40+ | httpx 0.28 dropped `proxies` kwarg in old openai | runtime compat | Yes |
| `utils.py:`top-level `import google.generativeai` | guarded try/except | optional dependency | Yes |
| `utils.py:Agent.chat` + `Agent.temp_responses` (~4 LOC) | honor `OPENROUTER_REASONING_DISABLE` → `extra_body={reasoning:{enabled:false}}` | Yes (config-only) |

**All patches are wiring/bug-fix; no algorithmic modification.**

## Behavior-changing patches

**None.** (Reasoning-disable below is a backbone config knob.)

## V4-Pro reasoning-disable patch (2026-07-03)

MDAgents sets no `max_tokens`, so it does not suffer the empty-content
starvation that hit AgentClinic/MedAgents. But DeepSeek-V4-Pro's unbounded
reasoning makes each of the 7–10 debate calls 15–32 s → the multi-agent debate
blows the timeout cap on **17–32% of cells**. Disabling reasoning
(`reasoning={"enabled": false}`, propagated via `OPENROUTER_REASONING_DISABLE`)
drops per-call latency to ~1.9 s. Consistent with the reasoning-off config used
for all backbones (§5.2). Algorithm/prompts untouched. See `round2_worklog.md`
Retrospective #8.

## Adapter wrapper

- File: `harness/agents/mdagents.py`
- Subprocess to `agents/mdagents/.venv/bin/python main.py
  --dataset <smoke> --model <or-model> --difficulty intermediate
  --num_samples 1`
- Output parsing: `parse_ranked_top5` (in `harness/agents/_adapter_utils.py`)
  reads `1. <name>` lines from response, with:
  - Section-aware: prefer numbered list after "differential diagnosis" /
    "candidate" / "top-N" / "ranked" headers (2026-05-19 fix —
    catches DeepSeek output where feature-triad was misread as
    differential)
  - Prose / clinical-feature filter (rejects `Laboratory evidence...`
    style strings — 2026-05-19 fix)
- ID mapping: `map_names_to_ids_with_variants` returns top-K tied
  ORPHA candidates per name; evaluator checks any (2026-05-19 fix for
  fuzzy-tie issue, see `memory/feedback_strict_baseline_repro.md`)

## Observed results vs paper

| Backbone | n_ok | R@1 | R@5 | Paper expected |
|---|---|---|---|---|
| Gemini 3 Flash | 50/50 | **0.34** | 0.42 | 0.31–0.39 ✅ |
| DeepSeek V3.2 v1 (no parser fix) | 50/50 | 0.24 | 0.34 | 0.31–0.39 ⚠️ -7 to -15 pp |
| DeepSeek V3.2 v3 (parser fix) | 50/50 | **0.30** | 0.36 | 0.31–0.39 ✅ |
| GPT-5 (minimal) | 50/50 | **0.30** | 0.42 | n/a (newer than paper) |

### Gap analysis (DeepSeek V3.2 v1 → v3)

The -10 pp gap in v1 was caused by the **parser bug** (not the LLM):
DeepSeek output multi-section reasoning where the first `1./2./3.` block
was a clinical-feature triad, not a differential — parser captured those.
Parser fix (section-aware) recovered +6 pp.

## Known incompatibilities

None observed across 3 backbones × 50 cases.

## Run receipts

- Phase 0 V3 (Gemini): `data/round2/phase0/predictions_v3.jsonl`
- Phase 2 DeepSeek v1: `data/round2/phase2/predictions_deepseek.jsonl`
- Phase 2 GPT-5: `data/round2/phase2/predictions_gpt5_v2.jsonl`
- Phase 2 fix DeepSeek v3 (parser fix): `data/round2/phase2_fix/predictions_mdagents_ds_v3.jsonl`
- Phase 2 fix DeepSeek v4 (with variants logger): in-flight,
  `data/round2/phase2_fix/predictions_mdagents_ds_v4_variants.jsonl`
- Historical RUN_REPORT: `tasks/stream_E_agent_scouting/agents/mdagents_RUN_REPORT.md`

## Last-updated

- 2026-05-19 — Initial doc; parser-fix audit (v3) + variants logger (v4)
