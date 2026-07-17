# MedAgents Scouting Report

## Repo
- URL: https://github.com/gersteinlab/MedAgents
- Stars: 344
- License: **None declared** (no LICENSE file in repo; GitHub `license` field returns `null`) — this is a real risk for redistribution / paper artefact requirements. May need to email Xiangru Tang / Mark Gerstein for explicit permission.
- Last commit: 2024-05-27 (no commits in >18 months as of 2026-05; effectively unmaintained)
- Primary language: Python
- Paper: Tang et al., "MedAgents: Large Language Models as Collaborators for Zero-shot Medical Reasoning", ACL 2024 Findings. arXiv:2311.10537.
- Local clone: `/Users/yutianzhao/Desktop/RDAgentBenchmark/agents/medagents/`

## Install Complexity
- Python: not pinned in repo; deps suggest Python 3.9–3.10 era.
- `requirements.txt` (9 packages, all old):
  - `openai==0.27.4` (pre-1.0 SDK — `openai.ChatCompletion.create(...)` style; incompatible with current `openai>=1.0`)
  - `torch==2.0.0`, `nltk==3.8.1`, `numpy==1.23.3`, `rouge-score==0.1.2`, `wrapt==1.15.0`, `wrapt-timeout-decorator==1.4.0`, `jsonlines==4.0.0`, `tqdm==4.65.0`
- External data: MedQA test set ships with the repo (`datasets/MedQA/test.jsonl`); MedMCQA / PubMedQA / MMLU subsets must be downloaded from a Google Drive link in README (`drive.google.com/file/d/11qNzDYI...`). No HPO / Orphanet resources — this is a pure MCQA framework.
- Difficulty: **medium-low to install, but medium-high to modernise**. The framework itself is ~500 LOC of plain Python with no DB/server/embedding artefacts, so the dependency surface is tiny. The real work is rewriting `api_utils.py` for the modern OpenAI SDK + non-OpenAI backbones — see below.

## Backbone Configuration
- **Default**: Azure OpenAI deployment (`openai.api_type = "azure"`, hardcoded in `api_utils.py` lines 6–9; `engine=` parameter is an Azure *deployment* name, not a model id).
- **Built-in choices** (`api_handler.__init__`, lines 80–103): `chatgpt` → `gpt-35-turbo-16k`, `gpt4` → `gpt-4`, plus several legacy `text-davinci-*` engines. Hardcoded; no Gemini / Claude / DeepSeek path.
- **OpenAI-compatible base_url support**: **NO**, not as shipped. The code uses module-level Azure globals (`openai.api_type`, `openai.api_base`, `openai.api_version`) instead of a client object with `base_url`. To swap in DeepSeek / GPT-5 / Gemini we must rewrite `api_utils.py` end-to-end:
  1. Migrate from `openai.ChatCompletion.create(engine=...)` → `openai.OpenAI(base_url=..., api_key=...).chat.completions.create(model=...)` (OpenAI SDK >=1.0).
  2. Replace the `engine` switch with a model-name pass-through plus per-provider routing (DeepSeek and Gemini both expose OpenAI-compatible endpoints; Claude needs Anthropic SDK).
  3. Touch points: only `generate_response_multiagent`, `generate_response`, `generate_response_ins`, and `api_handler.__init__` — roughly 30 LOC. Plus one `--model_name` whitelist in `run.py` line 26.
- Estimated rework: half a day of careful refactoring to get a single unified backend that takes `(provider, model, base_url, api_key)`. Easy to wrap.

## I/O Schema
- **Input**: a JSONL file at `datasets/<DATASET>/test.jsonl`. Each line is a MCQA item, e.g.:
  ```json
  {"question": "A junior orthopaedic surgery resident ...",
   "options": {"A": "...", "B": "...", "C": "...", "D": "..."},
   "answer": "Tell the attending that he cannot fail to disclose this mistake",
   "answer_idx": "C",
   "meta_info": "step1"}
  ```
- **Output**: appended JSONL at `<output_files_folder>/<model_name>-<method>`. Per-case keys: `question`, `options`, `pred_answer` (one letter), `gold_answer`, `question_domains` (5 strings), `option_domains` (2 strings), `question_analyses` (dict domain→text), `option_analyses` (dict), `syn_report` (str), `vote_history` (list of dicts), `revision_history`, `syn_repo_history`, `raw_output`.
- **Important for benchmark**: framework is **multiple-choice-only**. To use for rare-disease open-ended DDx we must either (a) cast diagnosis options as MCQA (top-N candidate list per case — feasible for RareBench-style data but contaminates the "open-ended" claim), or (b) substantially rewrite the final-answer prompts to emit free-text diagnoses. Choice (a) is the lower-risk path.

## LLM Call Sites
All LLM calls go through `api_handler.get_output_multiagent` in `api_utils.py`. The orchestrator is `fully_decode()` in `utils.py`. Per case (method `syn_verif`, the paper's default), the call graph is:

| Step | File / function | # calls |
|---|---|---|
| Question domain classification | `utils.py` `fully_decode` line 21–25 | 1 |
| Option domain classification | line 28–32 | 1 |
| Per-domain question analysis | line 35–40 (loop over `NUM_QD=5`) | 5 |
| Per-domain option analysis | line 43–48 (loop over `NUM_OD=2`) | 2 |
| Synthesised report | line 58–60 | 1 |
| Consensus voting (per round) | line 83–86 (loop over `NUM_QD+NUM_OD=7` domains) | 7 |
| Revision advice (when disagreement) | line 88–91 | up to 7 |
| Report revision | line 94–96 | 1 per round |
| Final answer | line 102–104 | 1 |

**Estimated cost per case**: ~17 calls if every expert agrees in round 1; up to ~17 + (7 + 7 + 1) × (`max_attempt_vote`=3 − 1) ≈ 47 calls in worst case. With 60k cases this is **~1–3M LLM calls**, so backbone choice and prompt cache are critical.

Prompts live in `prompt_generator.py` (144 lines, 10 small functions, very readable). All prompts in English, MCQA-shaped.

## Multi-agent Architecture
Five-stage "Multi-disciplinary Collaboration":
1. **Expert gathering** — one LLM call classifies the question into `NUM_QD=5` medical domains (free-text role names, e.g. "Cardiology", "Endocrinology") and a second call classifies the options into `NUM_OD=2` domains. Roles are *generated per case*, not fixed.
2. **Analysis proposition** — 7 independent LLM calls, one per (synthetic) expert, each with a system prompt like `"You are a medical expert in the domain of {domain}..."`.
3. **Report summarisation** — one LLM call with a "synthesiser" persona.
4. **Collaborative consultation** — voting loop over all 7 expert roles; each casts YES/NO on the synthesised report; on NO they emit revision advice; up to 3 rounds.
5. **Decision making** — one final LLM call returns the letter answer.

**Communication protocol**: pure text concatenation through `transform_dict2text()`. There is no message bus, no tool use, no retrieval. All "agents" are independent stateless LLM calls; the only state is the synthesised report and the running vote history. This is the simplest possible multi-agent baseline — exactly the use case the project plan calls out for H4 ("是否真的需要多 agent").

## Risk: **medium**
Reasons:
- **License is missing** — biggest single risk. Must be resolved before public release of any benchmark artefact that reproduces MedAgents results. Email the authors.
- **openai==0.27.4** is incompatible with anything newer than 2023; cannot coexist in the same Python env as DeepRare / AgentClinic etc. Must wrap or rewrite the LLM client. Maintainability is poor (repo has been quiet for 18+ months).
- **MCQA-only design** is a structural mismatch with the rare-disease open-ended DDx setting. Adapting it costs prompt-engineering time, and a re-implementation deviates from the published method — may need to caveat in the paper ("MedAgents adapted to free-text DDx").
- Upside: the framework is tiny (~500 LOC), prompts are clean and well factored, no external services / DBs / vector stores. Low integration surface area.

## Next Steps for Benchmark Integration
1. **License**: email Xiangru Tang (xiangru.tang@yale.edu) requesting explicit redistribution permission, or pick a successor (`gersteinlab/MedAgents-2`, Apache-2.0, last updated 2025-10) and validate it reproduces the ACL-24 method.
2. **Refactor `api_utils.py`** into a single `LLMClient(provider, model, base_url, api_key)` class that supports OpenAI-compatible endpoints (DeepSeek V3.2, GPT-5, Gemini via OpenAI-compat shim) and Anthropic. ~30 LOC change. Add a `temperature` / `max_tokens` config dict per backbone.
3. **MCQA adapter** for rare-disease data: feed each case as `(vignette, top-K candidate diseases as options A–E)`. Top-K candidate list can come from (a) gold + 4 hard negatives sampled by HPO similarity (RareBench style) or (b) a retrieval pre-pass over Orphanet. Document this in the paper.
4. **Lock `max_attempt_vote=1` or `2`** for cost control; the 3-round default could 3x token spend.
5. **Reproduce ACL-24 numbers on MedQA** before claiming the wrapper is faithful — single sanity-check run on ~50 cases.
6. **Wrap output JSONL** in a harness-compatible adapter (the project's evaluation harness expects rare-disease DDx schema; MedAgents emits `pred_answer` as a letter — map back to diagnosis text via the options dict).
