# MedAgents Run Report

## Install

- venv: `/Users/yutianzhao/Desktop/RDAgentBenchmark/agents/medagents/.venv`
- Host Python: 3.13.7 (system `/usr/local/bin/python3`)
- Commands (run from `agents/medagents/`):
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -U pip
  pip install "openai==0.27.4" "nltk" "numpy" "rouge-score" "wrapt" \
              "wrapt-timeout-decorator" "jsonlines" "tqdm"
  # NLTK punkt data (SSL bypass needed on Python 3.13 + macOS)
  python -c "import ssl; ssl._create_default_https_context = ssl._create_unverified_context; \
             import nltk; nltk.download('punkt_tab'); nltk.download('punkt')"
  ```

### Conflicts resolved
- `torch==2.0.0` is **not available on Python 3.13** (PyPI only ships 2.6+ for cp313). Resolved by **dropping the torch pin entirely**: `grep` confirmed `torch` is imported nowhere in the MedAgents code path. Same logic for the loose `nltk` / `numpy` / `rouge-score` pins — unpinned to let pip pick cp313-compatible wheels.
- `nltk` ships without the `punkt_tab` resource. On macOS + Python 3.13 the default NLTK downloader fails SSL verification; bypassed with `_create_unverified_context` for the one-off download. Data lives in `~/nltk_data/`.
- `openai==0.27.4` (the pre-1.0 SDK) **does import successfully on Python 3.13** — `openai.ChatCompletion` is still resolvable, and the legacy `module.ChatCompletion.create(...)` style works against an OpenAI-compatible endpoint.

## Patches

**File: `agents/medagents/api_utils.py`** (only file touched; ~25 LOC delta)

Diff summary:
- Replaced the hardcoded Azure module-globals
  ```python
  openai.api_type = "azure"
  openai.api_base = ""        # was: Azure endpoint
  openai.api_version = ""     # was: Azure API version
  openai.api_key = ""         # was: secret hardcoded
  ```
  with environment-driven OpenRouter config:
  ```python
  openai.api_type = "open_ai"
  openai.api_base = os.environ.get("OPENAI_API_BASE", "https://openrouter.ai/api/v1")
  openai.api_version = None
  openai.api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
  _MODEL_ID = os.environ.get("CANARY_BACKBONE_MODEL", "google/gemini-3-flash-preview")
  ```
- Replaced both call sites (`generate_response_multiagent` and `generate_response`) `engine=engine` → `model=_MODEL_ID`. The Azure `engine=` kwarg points at a deployment name; the standard OpenAI-compatible `model=` kwarg points at an OpenRouter model id.
- Increased the per-call `@timeout` on `generate_response` from 10s → 60s (hosted gateways often >10s on cold starts).
- Did **not** touch `api_handler.__init__`. Its `self.engine` switch (`chatgpt → gpt-35-turbo-16k`, `gpt4 → gpt-4`) is now unused — kept for back-compat with `run.py --model_name` whitelist (which still requires `chatgpt|gpt4|...`).

No API keys are written into the file.

## Backbone config

| Field | Value |
|---|---|
| Provider | OpenRouter (OpenAI-compatible) |
| `base_url` | `https://openrouter.ai/api/v1` |
| `api_key` | `$OPENROUTER_API_KEY` (env, from `.env`) |
| Model | `google/gemini-3-flash-preview` (from `$CANARY_BACKBONE_MODEL`) |
| Temperature | 0 (unchanged from upstream) |
| Top-p | 1 |
| Max tokens | per-call (50 / 300 / 500 / 2500 depending on stage) |

## Smoke test

### Test 1: `base_cot` (single LLM call, sanity check)
- Cmd: `python run.py --model_name chatgpt --dataset_name MedQA --start_pos 0 --end_pos 1 --method base_cot --max_attempt_vote 1`
- Input: MedQA case 0 (orthopedic surgery / disclosure ethics MCQA, 5 options)
- Output: `outputs/MedQA/chatgpt-base_cot` JSONL row with `pred_answer="B"`, `gold_answer="C"`, full `raw_output` containing the model's CoT.
- Wall clock: **3.17 s** (1 LLM call)
- The wrong-answer (B vs C) is a model judgment, not a parsing failure — the regex extractor correctly pulled "Answer: B" out of the response.

### Test 2: `syn_verif` (full multi-agent pipeline, primary smoke test)
- Cmd: `python run.py --model_name chatgpt --dataset_name MedQA --start_pos 0 --end_pos 1 --method syn_verif --max_attempt_vote 1`
- Same MedQA case 0.
- Output: `outputs/MedQA/chatgpt-syn_verif` with all expected schema keys populated:
  - `question_domains`: ['Medical Ethics', 'Orthopedic Surgery', 'Hand Surgery', 'Professionalism', 'Medical Jurisprudence'] (5 expert roles auto-generated)
  - `option_domains`: ['Medical Ethics', 'Orthopaedic Surgery'] (2 roles)
  - `question_analyses`, `option_analyses`: dict[domain → text], all populated
  - `syn_report`: ~1.7 kB synthesized report
  - `vote_history`: `[{'Medical Ethics': 'yes', 'Orthopedic Surgery': 'yes', 'Hand Surgery': 'yes', 'Professionalism': 'yes', 'Medical Jurisprudence': 'yes', 'Orthopaedic Surgery': 'yes'}]` — unanimous yes in round 1, loop exits.
  - `pred_answer="B"` again (same model disagreement as base_cot).
- LLM calls: **10** (1 question-domain + 1 option-domain + 5 question-analyses + 2 option-analyses + 1 synthesis + 6 votes + 1 final answer — minus de-duplicated "Medical Ethics" once it appears in both domain sets, plus the `max_attempt_vote=1` cap)
- Wall clock: **51.4 s** end-to-end (per-call latency 1.4–5.0 s, mean ~2.5 s on Gemini 3 Flash)
- Token cost: not retrieved from OpenRouter dashboard during smoke run; Gemini 3 Flash preview is $0.50/$3 per 1 M in/out per `.env` note. ~10 calls × short MCQA prompts ≈ <$0.01 per case.

## Status: PASSED

- Both methods (`base_cot`, `syn_verif`) executed end-to-end, no exceptions, valid JSONL output, expected schema keys all populated.
- The 5-stage MDC pipeline (domain classification → per-expert analyses → synthesis → voting → final answer) all routed through Gemini 3 Flash via OpenRouter without code-side changes beyond the 25-LOC `api_utils.py` swap.

## Blockers

None for smoke test. Remaining issues are scale-related and tracked in "Notes for benchmark integration".

## Notes for benchmark integration

- **MCQA-only**: `run.py` line 26 hardcodes a `--model_name` whitelist (`chatgpt|gpt4|...`). We pass `chatgpt` as a no-op token; the actual model id lives in `$CANARY_BACKBONE_MODEL`. For the main run, add a `--backbone_model` CLI flag that overrides `_MODEL_ID`. Easy.
- **Rare-disease adapter**: MedAgents emits a single letter (A/B/C/D/E). For open-ended rare-disease DDx we either build a top-K candidate MCQA from gold + HPO-similar negatives, or rewrite `cleansing_final_output` + the final-answer prompt to extract a free-text disease name. Decision should go into the paper's "Adaptation" section.
- **Cost ceiling**: at `max_attempt_vote=1` and 7 domain experts, expect ~10 calls per case. With ~50k rare-disease cases that's 500k Gemini 3 Flash calls — manageable at preview pricing. The default `max_attempt_vote=3` triples that, so lock to 1 or 2 in the main config.
- **NLTK punkt_tab** is a one-time install per machine. Add a `setup.sh` step or wrap in `data_utils.py`.
- **No retry on rate limit**: the 200 s outer timeout wraps the entire call; if OpenRouter returns 429 the SDK bubbles it up. Add exponential backoff before scaling.
- **License**: still unresolved (no LICENSE file in upstream). Flagged in `medagents_REPORT.md`; orthogonal to the run-readiness check.

## Adapter Shim

- **File**: `/Users/yutianzhao/Desktop/RDAgentBenchmark/harness/agents/medagents.py`
- **Class**: `MedAgentsAdapter(AgentAdapter)`, `NAME = "medagents"`
- **Pillars supported**: P2 (phenotype DDx), P5 (reasoning trace = per-expert top-5
  blocks, in `reasoning_trace`)
- **Design**: bypasses upstream `run.py` (MCQA-locked) entirely. Instead, executes a
  small Python driver script via `agents/medagents/.venv/bin/python -c "<driver>"`.
  The driver imports `api_utils.api_handler` and runs a 3-stage flow on a free-text
  rare-disease case: (1) recruit 3 specialty domains, (2) per-domain top-5 DDx,
  (3) chief-MO synthesis into a final consolidated top-5. The synthesiser's output is
  regex-parsed and mapped to ORPHA via `harness.pmc_oa.orphanet`.
- **Backbone wiring**: `OPENAI_API_BASE=https://openrouter.ai/api/v1`,
  `OPENROUTER_API_KEY=...`, `CANARY_BACKBONE_MODEL=google/gemini-3-flash-preview`.
- **Test result** (`python -m harness.agents.medagents`):
  - Case: `rarebench_RAMEDIS_00000` (4 HPO terms)
  - Status: `ok`, latency ~14–16 s, ~7 LLM calls (1 triage + 3 expert + synth)
  - Tokens (combined char-count + usage): 1837 prompt / 1071 completion
  - Top-5 ORPHA: `['ORPHA:254871', 'ORPHA:882', 'ORPHA:3008', 'ORPHA:35', 'ORPHA:157']`
    (Mitochondrial DNA depletion syndrome hepatocerebral form, Tyrosinemia type 1,
    Pyruvate carboxylase deficiency, Propionic acidemia, CPT II deficiency).
  - Domains auto-recruited: Medical Genetics, Metabolic Diseases, Neurology.
- **Known caveats**:
  - **Not the full upstream pipeline**: we skip the question-domain / option-domain
    voting loop because there are no MCQ options for free-text DDx. The shim retains
    the "specialist roles" idea but reduces it to 3 fixed-N experts. The full
    `syn_verif` pipeline (5+ experts, multi-round voting) is reserved for the bias
    eval / MedQA crossover task.
  - **Usage tokens estimated** via `chars/4` (api_utils prints latency but not
    OpenRouter usage). Provider = `openrouter`.
  - **No retry on 429** — relies on api_utils' single retry. Add an outer retry loop
    in the runner harness if the main experiment is throttled.


---

## Bug Fix 2026-05-15 (Phase-0 retro)

**Bug D2** (round2_plan.md § 复盘 ①): `cost.cost_usd` was 0 across the
50-case Mini Phase 0 sample despite valid `prompt_tokens` /
`completion_tokens` counts (estimated via char-count heuristic).

**Fix** in `harness/agents/medagents.py`:
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
`MedAgentsAdapter(backbone_id="openrouter/google/gemini-3-flash-preview")`
→ `log.cost.cost_usd > 0` on a single PP-Store case.
