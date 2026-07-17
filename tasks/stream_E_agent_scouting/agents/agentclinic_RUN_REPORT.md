# AgentClinic Run Report

## Install

- venv: `/Users/yutianzhao/Desktop/RDAgentBenchmark/agents/agentclinic/.venv`
- Host Python: 3.13.7 (system `/usr/local/bin/python3`)
- Commands (run from `agents/agentclinic/`):
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -U pip
  # Skip transformers / replicate / datasets — neither is needed for the
  # OpenRouter smoke-test path; transformers is huge and the HF code path
  # is broken upstream anyway.
  pip install "openai==0.28.0" "regex==2023.12.25" "anthropic"
  ```

### Conflicts resolved
- **`transformers`, `replicate`, `datasets`** dropped from the install. The scouting report flagged the HF branch as broken (explicit `raise Exception("Sorry, fixing TODO :3")` at line 172) and we don't need Replicate or HuggingFace datasets for the OpenRouter test. Lazy-imported `transformers` inside `load_huggingface_model` so the rest of the module still loads. Saves ~2 GB of wheels.
- **`openai==0.28.0`** imports fine on Python 3.13. `openai.ChatCompletion.create(...)` still works against an OpenAI-compatible endpoint.
- **Image fall-through bug** in `query_model()`: when `image_requested=True` and the model isn't `gpt4v/gpt4o/gpt-4o-mini/gpt4`, the inner `answer = response["choices"][0]["message"]["content"]` references an undefined `response`. Triggers on NEJM scenarios when the doctor agent says "REQUEST IMAGES" (and `--doctor_image_request False` makes images implicit, so `imgs=True`). Worked around by force-disabling `image_requested` whenever `model_str == "openrouter"`. Documented below.

## Patches

**File: `agents/agentclinic/agentclinic.py`** (only file touched; ~30 LOC delta)

Diff summary:
1. Top of file — remove eager import of `transformers` (lazy now), add OpenRouter config:
   ```python
   # before
   from transformers import pipeline
   import openai, re, random, time, json, replicate, os
   # after
   import os
   import openai, re, random, time, json
   OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
   OPENROUTER_MODEL = os.environ.get("CANARY_BACKBONE_MODEL", "google/gemini-3-flash-preview")
   ```
   `load_huggingface_model` now imports `transformers` lazily.
2. `query_model()` whitelist — added `"openrouter"` as a valid `model_str`, and force `image_requested = False` for that model (text-only smoke-test path):
   ```python
   if model_str == "openrouter":
       image_requested = False
   ```
3. `query_model()` text branch — inserted a new `if model_str == "openrouter"` block ahead of the `if model_str == "gpt4"` chain. The block temporarily redirects the module-global `openai.api_base` and `openai.api_key` to OpenRouter, calls `openai.ChatCompletion.create(model=OPENROUTER_MODEL, ...)`, then restores. Wrapped in `try/finally` so other concurrent backbones (e.g. the OpenAI public endpoint) still see their original config.

The patch deliberately **does not** touch the 9 existing `openai.ChatCompletion.create(...)` blocks (gpt4 / gpt4o / gpt-3.5 / etc.). They stay as-is for future per-agent backbone swaps. AgentClinic's per-agent `--doctor_llm` / `--patient_llm` / `--measurement_llm` / `--moderator_llm` CLI is preserved — just pass `openrouter` to any of them.

No API keys are written into the file.

## Backbone config

| Field | Value |
|---|---|
| Provider | OpenRouter (OpenAI-compatible) |
| `base_url` | `https://openrouter.ai/api/v1` |
| `api_key` | `$OPENROUTER_API_KEY` (env, also passed via `--openai_api_key` to satisfy the CLI's required-ish flag) |
| Model | `google/gemini-3-flash-preview` (from `$CANARY_BACKBONE_MODEL`) |
| Temperature | 0.05 (unchanged from upstream's defaults) |
| Max tokens | 200 per call (unchanged) |
| All 4 agents | `--doctor_llm openrouter --patient_llm openrouter --measurement_llm openrouter --moderator_llm openrouter` |

## Smoke test

- Cmd:
  ```bash
  python agentclinic.py \
      --openai_api_key "$OPENROUTER_API_KEY" \
      --doctor_llm openrouter --patient_llm openrouter \
      --measurement_llm openrouter --moderator_llm openrouter \
      --agent_dataset NEJM --doctor_image_request False \
      --num_scenarios 1 --total_inferences 6
  ```
- Input: `agentclinic_nejm.jsonl` case 0 — 55-year-old woman with 1-year history of facial skin darkening after long-term skin-lightening cream use. Gold diagnosis: **Exogenous ochronosis**.
- Conversation trace (excerpt from stdout):
  - **Doctor [16%]**: "Hello, I am Dr. Agent... could you please describe your main symptoms... REQUEST IMAGES."
  - **Patient [16%]**: "my skin getting much darker and turning a strange bluish-brown color over the last year ... applied a lightening cream every day about two years ago..."
  - **Doctor [33%]**: "...visible blood vessels is a key detail. Have you noticed if these patches get darker or more irritated after sun exposure? ... REQUEST TEST: Skin_Biopsy"
  - **Measurement [33%]**: "RESULTS: Extracellular deposition of yellow-brown, banana-shaped bodies in the dermis (Hematoxylin and Eosin stain)."
  - **Doctor [50%]**: "The biopsy results showing banana-shaped bodies are very characteristic... DIAGNOSIS READY: Exogenous Ochronosis"
- Moderator (5th LLM call): `Yes` → verdict **CORRECT**.
- Wall clock: **15.8 s** end-to-end including OpenRouter cold start.
- LLM call count for this case: ~5 (Doctor×3, Patient×1, Measurement×1, Moderator×1). Under the `--total_inferences 6` cap the doctor finished in 3 turns.
- Token cost: not pulled from OpenRouter dashboard; Gemini 3 Flash preview is $0.50/$3 per 1 M in/out. With ~200-token responses this case cost <$0.01.

## Status: PASSED

- All 4 agents (Doctor / Patient / Measurement / Moderator) ran through OpenRouter without code-side touch beyond the single 30-LOC patch.
- Doctor arrived at the correct diagnosis on a real NEJM rare-disease-adjacent case, and the moderator's LLM-as-judge correctly verified it.
- Per-agent backbone CLI is intact — we can route each role to a different model for the main experiment.

## Blockers

None for smoke test.

## Notes for benchmark integration

- **Image branch is patched-out, not fixed**. For multimodal rare-disease cases (NEJM has image URLs), we'd need to extend the `openrouter` block to forward the OpenAI vision `messages` schema. OpenRouter does proxy multimodal for Gemini 3 Flash, but the smoke test was text-only by design.
- **Output is print-only**. As flagged in `agentclinic_REPORT.md`, the moderator's verdict and full dialogue only go to stdout. Before the main run, wrap with JSONL logging: per-case `{case_id, doctor_dialogue, patient_dialogue, measurement_dialogue, final_diagnosis, gold_diagnosis, moderator_verdict, n_turns}`.
- **Per-agent cost routing**: the per-agent CLI lets us assign cheap backbones (Gemini 3 Flash) to Patient / Measurement and reserve expensive ones (GPT-5 / Claude 4.7) for Doctor and Moderator. This is the cleanest cost-control lever in our agent zoo.
- **Retry behavior**: `query_model` retries up to **30** times with `time.sleep(20.0)` between attempts on **any** Exception. A single bad model id silently blackholes for 10 minutes. Lower `tries` (e.g. to 3) and narrow the `except` clause before the main run.
- **`SyntaxWarning: invalid escape sequence '\s'`** appears 9x at import on Python 3.13 — cosmetic; old `"\s+"` strings should be raw strings. Doesn't affect behavior.
- **NEJM image-URL CDN dependency** (`csvc.nejm.org`) — pre-cache locally before any large-scale run.
- **`--openai_api_key` CLI flag is awkward** when using OpenRouter — we pass `$OPENROUTER_API_KEY` into it as a no-op (the openrouter branch re-sets `openai.api_key` from env anyway). A clean refactor would add `--openrouter_api_key` and route per-model.

## Adapter Shim

- **File**: `/Users/yutianzhao/Desktop/RDAgentBenchmark/harness/agents/agentclinic.py`
- **Class**: `AgentClinicAdapter(AgentAdapter)`, `NAME = "agentclinic"`
- **Pillars supported**: P2 (phenotype DDx), P5 (reasoning trace = full doctor /
  patient / measurement dialogue, in `reasoning_trace`)
- **Design**: projects a `CanonicalCase` to a synthetic AgentClinic
  **MedQA-style OSCE scenario** (Patient_Actor.Symptoms = HPO labels, History = free
  text or HPO render, Correct_Diagnosis = gold disease name), writes it to a temp
  `agentclinic_medqa.jsonl` in a fresh cwd, then invokes
  `agents/agentclinic/.venv/bin/python agentclinic.py --doctor_llm openrouter ...
  --agent_dataset MedQA --num_scenarios 1`. Stdout is parsed with regexes
  (`Doctor [X%]:`, `Patient [X%]:`, `Measurement [X%]:`, `DIAGNOSIS READY: ...`,
  `The diagnosis was CORRECT|INCORRECT`) to recover the dialogue + the Doctor's
  single final diagnosis + the moderator's verdict. A **second** subprocess call
  (`agentclinic.py -c "<follow-up driver>"`) reuses `query_model("openrouter", …)`
  to ask for a ranked top-5 given the dialogue — that gives ranks 2..5; the
  Doctor's stated diagnosis seats rank 1 (if missing from the top-5 it gets
  prepended).
- **Backbone wiring**: identical to the smoke test (`OPENROUTER_BASE_URL`,
  `CANARY_BACKBONE_MODEL`, all four `--*_llm openrouter`).
- **Test result** (`python -m harness.agents.agentclinic`):
  - Case: `rarebench_RAMEDIS_00000` (4 HPO terms; gold = isovaleric acidemia /
    glutaric aciduria territory)
  - Status: `ok`, wall-clock ~36 s, ~7 doctor inferences, +1 follow-up call
  - Doctor final dx: `Dermatomyositis` (incorrect on this metabolic case — the
    HPO terms happened to look myositic to the LLM) → moderator returned
    `CORRECT` against a synthetic match anyway; this is parser-confidence, not
    accuracy
  - Top-5 ORPHA: `['ORPHA:221', 'ORPHA:93672', 'ORPHA:81', 'ORPHA:206569',
    'ORPHA:611']` (Dermatomyositis, Juvenile dermatomyositis, Anti-synthetase
    syndrome, Immune-mediated necrotizing myopathy, Inclusion body myositis)
- **Known caveats**:
  - **Synthetic OSCE scenario** — Patient agent is told the HPO labels and
    nothing else, so the dialogue is shallow vs. real NEJM cases. The Doctor
    typically converges in 3–7 turns; bump `agent_extra={"total_inferences": 12}`
    for richer dialogue.
  - **Follow-up call is required** for top-5 — AgentClinic only ever emits one
    final diagnosis. We elicit ranks 2..5 from a one-shot LLM call given the
    dialogue + Doctor's dx. This means the top-5 is partially decoupled from the
    multi-turn OSCE simulation.
  - **`max_tokens=200`** hardcoded in `query_model` truncates the follow-up
    output into a one-line `1. X 2. Y` format; the parser handles that with an
    inline-numbering fallback.
  - **No usage stats** — cost estimated from text length.
  - **Moderator's CORRECT/INCORRECT verdict is captured** in
    `extra["agentclinic_verdict"]` but is NOT used to short-circuit harness
    scoring — the harness re-evaluates against `gold_label` via ORPHA mapping.


---

## Bug Fix 2026-05-15 (Phase-0 retro)

**Bug D2** (round2_plan.md § 复盘 ①): `cost.cost_usd` was 0 across the
50-case Mini Phase 0 sample despite valid `prompt_tokens` /
`completion_tokens` counts (estimated via char-count heuristic).

**Fix** in `harness/agents/agentclinic.py`:
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
`AgentClinicAdapter(backbone_id="openrouter/google/gemini-3-flash-preview")`
→ `log.cost.cost_usd > 0` on a single PP-Store case.
