# MDAgents Run Report

## Install

- **venv path**: `/Users/yutianzhao/Desktop/RDAgentBenchmark/agents/mdagents/.venv` (Python 3.13.7)
- **Install command sequence**:
  ```bash
  cd /Users/yutianzhao/Desktop/RDAgentBenchmark/agents/mdagents
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -U pip
  pip install -r requirements.txt
  # SDK fix: openai 1.14.2 is incompatible with httpx>=0.28 (httpx removed `proxies`
  # kwarg). Upgrade to a recent openai SDK.
  pip install -U "openai>=1.40,<2"
  ```
- **Resolved dependency issues / build problems**:
  - `openai==1.14.2` from requirements.txt fails at runtime with
    `TypeError: Client.__init__() got an unexpected keyword argument 'proxies'` because
    httpx 0.28+ dropped that kwarg. Upgraded to `openai==1.109.1`.
  - `google.generativeai` is imported unconditionally in `utils.py` but is not in
    `requirements.txt` (known scouting issue). Worked around with a try/except import
    that sets `genai = None` when missing — no install needed since we use OpenRouter.
- **Wheels built**: `pptree` builds from source on macOS / Python 3.13.

## Patches applied

All edits in `utils.py` and `main.py`:

1. **`utils.py` — Guarded `google.generativeai` import.** Wrapped in try/except so the
   module loads even without `google-generativeai` installed.
2. **`utils.py` — Added `_openai_kwargs()` helper.** Builds OpenAI client kwargs with an
   optional `base_url` taken from `OPENAI_BASE_URL` / `OPENROUTER_BASE_URL`, and reads the
   API key from `openai_api_key` / `OPENAI_API_KEY` / `OPENROUTER_API_KEY`.
3. **`utils.py:Agent.__init__`** — Replaced the closed allow-list
   `if self.model_info in ['gpt-3.5', 'gpt-4', 'gpt-4o', 'gpt-4o-mini']` with an open
   `else` branch that accepts arbitrary model ids (including `google/gemini-3-flash-preview`).
   Uses `_openai_kwargs()` instead of `OpenAI(api_key=os.environ['openai_api_key'])`.
4. **`utils.py:Agent.chat`** — Fixed hard-coded `model_name = "gpt-4o-mini"` (line 51 in
   the original). Now uses `self.model_info` so `--model` is actually honoured.
5. **`utils.py:Agent.temp_responses`** — Same fix for the second hard-coded `gpt-4o-mini`
   (line 72 in the original).
6. **`utils.py:Group.__init__`** — Added a `model_info` parameter so internally-recruited
   experts use the configured backbone instead of the hard-coded `'gpt-4o-mini'`.
7. **`utils.py:determine_difficulty`** — Added a `model_info` parameter; previously the
   adaptive-difficulty classifier was hard-coded to `'gpt-3.5'`.
8. **`utils.py:process_intermediate_query`** — Recruiter agent now uses `model` instead of
   the hard-coded `'gpt-3.5'`.
9. **`utils.py:process_advanced_query`** — MDT recruiter now uses `model` instead of
   `'gpt-4o-mini'`. `Group(...)` call now passes `model_info=model`.
10. **`utils.py:setup_model`** — Native genai path now only triggers for
    `'gemini'` substring without `'/'` (so OpenRouter ids like `google/gemini-3-flash-preview`
    route through the OpenAI-compatible client).
11. **`utils.py:load_data`** — Fixed the `../data/{dataset}` → `./data/{dataset}` path bug
    (with fallback search: `./data/`, `../data/`, `<module-dir>/data/`, or env
    `MDAGENTS_DATA_ROOT`). `train.jsonl` is now optional (smoke datasets may not have it).
12. **`main.py`** — `determine_difficulty` called with `model_info=args.model`. Output
    filename now sanitises `/` in model ids (`google/gemini-3-flash-preview` →
    `google__gemini-3-flash-preview`). Non-`medqa` datasets now also get persisted.

## Backbone config

- **OpenRouter, OpenAI-compatible.** Set:
  - `OPENAI_BASE_URL=https://openrouter.ai/api/v1`
  - `openai_api_key=$OPENROUTER_API_KEY` (MDAgents reads `openai_api_key`, lowercase, from env)
  - `--model google/gemini-3-flash-preview` (passed via CLI; honoured by the
    patched `Agent.chat` / `Agent.temp_responses`)
- `MDAGENTS_MODEL` env var optionally provides a fallback model id for the
  legacy helper agents (recruiter, difficulty classifier, intermediate refs).
- No API key is committed; key is read from `.env` at run time.

## Smoke test

- **Smoke dataset**: `agents/mdagents/data/raredx_smoke/test.jsonl` (1 case, single line).
  Question: "A pediatric patient presents with HPO terms Microcephaly (HP:0000252),
  Seizures (HP:0001250), Developmental delay (HP:0001263). Please list the top 5 most
  likely rare-disease differential diagnoses…" (free-text, no MCQ options).

### Run 1 — Basic path

- **Command**:
  ```bash
  cd agents/mdagents && source .venv/bin/activate
  export OPENROUTER_API_KEY=...           # from .env
  export OPENAI_BASE_URL=https://openrouter.ai/api/v1
  export openai_api_key="$OPENROUTER_API_KEY"
  export MDAGENTS_MODEL="google/gemini-3-flash-preview"
  python main.py --dataset raredx_smoke --model google/gemini-3-flash-preview \
                 --difficulty basic --num_samples 1
  ```
- **Output**: `output/google__gemini-3-flash-preview_raredx_smoke_basic.json`
- **Top-5 returned (`response["0.0"]`)**:
  1. Angelman Syndrome
  2. Rett Syndrome
  3. ASPM-Related Primary Microcephaly (MCPH5)
  4. FoxG1 Syndrome
  5. Maternal PKU Embryopathy
- **Wall-clock**: ~6.5 s
- **LLM calls**: ~2 (single-agent + temp_responses).

### Run 2 — Intermediate (multi-agent debate) path

- **Command**: same as Run 1 with `--difficulty intermediate`.
- **Output**: `output/google__gemini-3-flash-preview_raredx_smoke_intermediate.json`
- **Pipeline**: recruiter agent recruited 5 experts (medical geneticist, pediatric
  neurologist, neurodevelopmental pediatrician, metabolic specialist, dysmorphologist);
  ran 1 round / 2 turns of participatory debate; moderator synthesised final top-5.
- **Top-5 from moderator (majority vote)**:
  1. Angelman Syndrome
  2. Rett Syndrome
  3. FoxG1 Syndrome
  4. Maternal Phenylketonuria Embryopathy
  5. Pitt-Hopkins Syndrome
- **Wall-clock**: 2 min 22 s
- **Approx LLM calls**: ~30–50 (recruiter + 5 init opinions + 5 round-summaries +
  5 participate + chosen-expert + opinion-deliver per turn for ~2 turns + 5 finals +
  moderator).
- **Note**: Without the `medqa` few-shot branch, the intermediate path runs in
  "open-ended differential" mode, which is exactly what we need for rare-disease cases.

## Status: ✅ runs cleanly

Both basic and intermediate code paths execute end-to-end against OpenRouter Gemini 3 Flash
on a rare-disease HPO-triad input. Output is a free-text ranked top-5; a regex parser will
be needed downstream for Recall@k scoring (no structured JSON inside `response`).

## Blockers

None for the smoke test. Caveats for benchmark integration:

- **Advanced path** (`process_advanced_query`) not smoke-tested in this run — it triggers
  a different recruiter prompt template and group-of-groups MDT logic. Should be exercised
  before relying on adaptive routing.
- **`google.generativeai`** is still listed in module-top imports (guarded). If we ever
  want true native Gemini (non-OpenRouter), we will need to add it to requirements.txt.
- Free-text response parsing is on us (no structured output schema in MDAgents).

## Notes for benchmark integration

- The runner can pass any OpenRouter model id via `--model`. Set
  `OPENAI_BASE_URL` and `openai_api_key` once and the same wiring serves Gemini, Claude,
  GPT-4o, DeepSeek, etc.
- Add an LLM-call budget cap before running on long-tail cases — the intermediate path can
  inflate to several hundred calls in the worst case (5 rounds × 5 turns × 5 agents).
  For the smoke run with `google/gemini-3-flash-preview`, the second round terminated early
  because all agents said "no" (`num_yes == 0`), which kept the cost low.
- Suggest adding a `--rare_disease` dataset type to `create_question` that bypasses MCQ
  formatting and constructs a structured prompt
  `"Patient phenotypes: <HPO_names>. Phenotype IDs: <HPO IDs>. Please list the top 5
  rare diseases, one per line in '1. <Name (ORPHA:XXX)>' format."` — currently we
  smuggle this through `sample['question']`.
- Output schema: `final_decision["majority"]["0.0"]` is the moderator's free-text final
  answer. A regex `^\d+\.\s*(.+?)$` pulls out the ranked names.

## Adapter Shim

- **File**: `/Users/yutianzhao/Desktop/RDAgentBenchmark/harness/agents/mdagents.py`
- **Class**: `MDAgentsAdapter(AgentAdapter)`, `NAME = "mdagents"`
- **Pillars supported**: P2 (phenotype DDx), P5 (reasoning trace surfaced via `extra`)
- **Design**: subprocess call to `agents/mdagents/.venv/bin/python main.py` against a
  one-line synthetic dataset written into `agents/mdagents/data/<harness_run_id>/test.jsonl`
  (cleaned up after each call). Reads the resulting JSON output, extracts the moderator's
  free-text top-5 from `record["response"]`, regex-parses the `1. <Name>` lines, then
  maps each name to an ORPHA ID via `harness.pmc_oa.orphanet.map_diagnosis`.
- **Backbone wiring**: `OPENAI_BASE_URL=https://openrouter.ai/api/v1`,
  `openai_api_key=$OPENROUTER_API_KEY`, `--model google/gemini-3-flash-preview`.
- **Test result** (`python -m harness.agents.mdagents`):
  - Case: `rarebench_RAMEDIS_00000` (4 HPO terms)
  - Status: `ok`, latency ~6–8 s, tokens (estimated) ~116 prompt + ~400 completion
  - Top-5 ORPHA: `['ORPHA:79243', 'ORPHA:506', 'ORPHA:35696', 'ORPHA:254905', 'ORPHA:726']`
    (Pyruvate dehydrogenase E1-α deficiency, Leigh syndrome, COXPD1, Cytochrome c oxidase
    deficiency, Alpers-Huttenlocher syndrome — all metabolic / mitochondrial, consistent
    with RAMEDIS).
- **Known caveats**:
  - **No usage stats** — `main.py` doesn't surface OpenAI usage; cost is estimated from
    text length (chars/4 heuristic). Provider field set to `openrouter`.
  - **Difficulty path** defaults to `basic`. Override with
    `MDAgentsAdapter(agent_extra={"difficulty": "intermediate"})` for the multi-expert
    debate path (≈30–50 calls/case, ~2 min wall-clock).
  - Subprocess **timeout** default 300 s — bump via `agent_extra={"timeout_s": ...}`
    when running the intermediate path on long HPO lists.
  - Each call creates+deletes a uniquely-named dataset under `agents/mdagents/data/` —
    safe for concurrent calls but leaves orphan dirs on crash.


---

## Bug Fix 2026-05-15 (Phase-0 retro)

**Bug D2** (round2_plan.md § 复盘 ①): `cost.cost_usd` was 0 across the
50-case Mini Phase 0 sample despite valid `prompt_tokens` /
`completion_tokens` counts (estimated via char-count heuristic).

**Fix** in `harness/agents/mdagents.py`:
- After the existing `CostBreakdown` is built, call
  `fill_cost_from_tokens(log.cost, self.backbone_id)` (new helper in
  `harness.agents._adapter_utils`). This looks up the per-1M price for
  the backbone from `harness.logging.openrouter_wrapper.get_price` (which
  strips the `openrouter/` prefix automatically) and computes
  `cost_usd = (pt * p_in + ct * p_out) / 1_000_000`.

For multi-LLM-call agents (DeepRare) the token floor is the entire
reasoning trace — under-estimates the true OpenAI cost but is non-zero.
A proper usage-callback wrapper is deferred.

Verified by a fresh smoke test:
`MDAgentsAdapter(backbone_id="openrouter/google/gemini-3-flash-preview")`
→ `log.cost.cost_usd > 0` on a single PP-Store case.
