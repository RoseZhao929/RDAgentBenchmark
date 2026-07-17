# MDAgents Scouting Report

## Repo
- **URL**: https://github.com/mitmedialab/MDAgents
- **Stars**: 261
- **License**: **None declared** in the repository (GitHub API returns null). README does not state a license. This is a meaningful issue — we should email Yubin Kim (ybkim95@mit.edu) before depending on it for a paper, or treat the code as "for research reference" and re-implement the core logic in our own harness.
- **Last commit (push)**: 2024-11-10 — *not maintained since release*. ~18 months stale at our cutoff.
- **Primary language**: Python (~15 MB repo)
- **Paper**: Kim Y. et al., "MDAgents: An Adaptive Collaboration of LLMs for Medical Decision-Making", *NeurIPS 2024 Oral* (arXiv 2404.15155). Plus a demo paper arXiv 2411.00248.

## Install Complexity
- **Python**: README says `python>=3.9`. Code uses f-string `{'\U0001F468‍⚖️'}` inside an f-string at utils.py line 454 which is a Python 3.12+ feature — practically **needs Python 3.12+** or a tiny edit.
- **Dependencies summary**: 7 packages only. `openai==1.14.2`, `tqdm`, `requests`, `prettytable`, `termcolor`, `pptree`, `climage`. No torch, no transformers, no datasets, no langchain. Lightweight.
- **Hidden import**: `utils.py` imports `google.generativeai as genai` unconditionally at module top — **must add `google-generativeai` to requirements** or stub the import out, otherwise even an OpenAI-only run fails.
- **External data/checkpoint requirements**: **None for the framework itself**. But it expects datasets to live at `../data/{dataset}/test.jsonl` (note: relative path going up one directory — README says `./data/` but `load_data` does `../data/...`, a bug). Datasets are the public medical QA sets MedQA, MedMCQA, PubMedQA, DDXPlus, SymCat, JAMA/Medbullets, PMC-VQA, Path-VQA, MIMIC-CXR, MedVidQA. **None of these are rare-disease focused** — this is generic medical QA. For our benchmark we will be feeding **our own** rare-disease cases through the MDAgents *scaffolding*, not the bundled benchmark.
- **Install difficulty**: Low. `pip install -r requirements.txt` + add `google-generativeai` works in minutes. The real work is wiring our cases into MDAgents' `create_question` and substituting an MCQ-free answer format.

## Backbone Configuration
- **Default backbone**: argparse default `gpt-4o-mini`. README mentions GPT-3.5/4/4v/4o, Gemini-Pro, Gemini-Pro-Vision.
- **How to swap**: CLI flag `--model`, then `setup_model()` in `utils.py:203-211` branches on substring "gemini" vs "gpt". Selection logic is **string-substring based** ("gpt" in name → OpenAI client; "gemini" → genai). Claude/DeepSeek/OpenRouter are **not supported out of the box**.
- **OpenAI-compatible endpoint (OpenRouter) support**: Requires a code edit, but it is a small one. Specifically:
  - In `utils.py:208`, `OpenAI(api_key=os.environ['openai_api_key'])` must take `base_url=os.environ.get('OPENAI_BASE_URL')`.
  - In every `Agent.__init__` (utils.py:23), same patch — note the model selection inside `Agent.chat` is **hard-coded** to either `gpt-3.5-turbo` or `gpt-4o-mini` (utils.py:48-51 and 69-72) regardless of the `model_info` argument! This is a real bug/limitation: passing `--model gpt-4` actually runs gpt-4o-mini internally. Must edit the hard-coded `model_name = "gpt-4o-mini"` to `model_name = self.model_info` to honour the flag.
  - Same fix for `temp_responses` at utils.py:69-72.
- After these edits, pointing `OPENAI_BASE_URL=https://openrouter.ai/api/v1` plus matching model strings (e.g. `openai/gpt-4o-mini`, `anthropic/claude-3.7-sonnet`, `deepseek/deepseek-v3`) gives us multi-backbone via one client. This is the cleanest path.

## I/O Schema
- **Input format**: JSONL-per-line, dataset-specific. `load_data` expects `test.jsonl` + `train.jsonl` per dataset. `create_question` builds a question string:
  - MedQA-style: `sample['question'] + " Options: (A) ... (B) ..."` — i.e. **multiple-choice question with options**.
  - Other datasets fall through to just `sample['question']`. **No HPO list / no VCF / no structured phenotype** support. The framework is built around free-text MCQ-style medical questions.
- **Output format**: Per-case dict written to `output/{model}_{dataset}_{difficulty}.json` with keys `question`, `label`, `answer`, `options`, `response`, `difficulty`. `response` is the moderator's final dict (e.g. `{'majority': {0.0: "Answer: (C) ..."}}`) — i.e. a free-text final answer string, originally designed for MCQ scoring via substring matching on `(A)/(B)/(C)/(D)`.
- **Three solve paths**: `process_basic_query` (single agent, few-shot), `process_intermediate_query` (5 specialists with hierarchy, multi-round debate, moderator votes), `process_advanced_query` (multiple MDT groups: IAT/DET/PHT/FRDT etc., nested groups). Path picked by `determine_difficulty` — itself one LLM call to a `gpt-3.5` (sic) agent that classifies the question as basic/intermediate/advanced.
- **Sample case**: input = MedQA-style MCQ; output = `{ majority: { 0.0: "Answer: (C) Adenocarcinoma" } }`.
- **For rare-disease use**: we need to (a) convert our (HPO list + free text) input into a free-text "Question: ..." prompt with **no answer options**, asking for top-5 differential diagnoses; (b) parse a textual top-5 list from the moderator's response; (c) skip MCQ-specific code paths (`if args.dataset == 'medqa'` branches in `process_intermediate_query` line 330+).

## LLM Call Sites
- `utils.py:Agent.chat` and `Agent.temp_responses` — every model call.
- `utils.py:setup_model` — instantiates the global OpenAI/genai client.
- `utils.py:determine_difficulty` — 1 call.
- `utils.py:process_basic_query` — 1 single-agent call + few-shot reason generation (5 calls if dataset=medqa).
- `utils.py:process_intermediate_query` — *very* call-heavy:
  - 1 recruiter call to design the team
  - 5 specialist instructions
  - 5 initial opinions
  - per round (up to 5 rounds × 5 turns × 5 agents): ~25 participate-or-not + chosen-expert + opinion-deliver calls × turns × rounds → can easily reach **hundreds of LLM calls per "intermediate" case** in the worst case.
  - 5 final answers + 1 moderator decision
- `utils.py:process_advanced_query` — 1 MDT recruiter + 3 groups × (1 lead delivery + 3 investigations + 1 final) per group + cross-team review + final review team. ~20-40 calls per case.
- **LLM calls per case (estimate)**:
  - basic: ~2-10 calls (cheap)
  - intermediate: ~50-500 calls depending on early stopping (`num_yes==0` breaks the round loop)
  - advanced: ~30-60 calls
  - **This is the main risk vector for budget**. Caching is non-existent; every call hits the API.

## Risk: **MEDIUM**
- (-) **No license** — biggest issue. Code is on GitHub but not legally OSI-licensed. For an EMNLP paper we should either (a) get written permission from Kim to redistribute / fork; (b) only run it in-place and cite, not redistribute; or (c) re-implement the core "solo↔group + moderator" scaffold in our own code and just credit the design.
- (-) Stale since 2024-11-10. `openai==1.14.2` is well behind current SDK; needs a small adapter for current API.
- (-) Hard-coded model name override in `Agent.chat` defeats the `--model` flag. Must fix before swapping in Claude/DeepSeek/OpenRouter — otherwise we silently always run gpt-4o-mini.
- (-) Designed for MCQ, not open-ended differential diagnosis. We must build the prompt + parser ourselves; the bundled `create_question`/dataset path is not reusable for rare disease.
- (-) Path `../data/...` mismatch with README's `./data/...` — one-line fix.
- (-) Intermediate path can balloon to hundreds of calls; budget control is on us.
- (+) Tiny dep set (~7 packages), 261 stars, NeurIPS oral pedigree, clear separation of basic/intermediate/advanced scaffolds that map 1:1 to our H4 hypothesis test (solo vs group vs MDT).
- (+) Backbone-agnostic by design (one `setup_model` + one `Agent` class). Once the hard-coded model names are removed, an OpenRouter base_url shim is genuinely a few lines.

## Next Steps for Benchmark Integration
- **Adapter shim sketch**:
  1. Fork repo into our `agents/mdagents/`. Add `google-generativeai` to requirements (or guard the import). Fix `../data/` → `./data/`.
  2. Replace hard-coded `model_name = "gpt-4o-mini"` (utils.py:51, 72) with `model_name = self.model_info`. Same for the gpt-3.5 fallback.
  3. Patch `Agent.__init__` + `setup_model` to accept `base_url=os.environ.get("OPENAI_BASE_URL")`, allowing OpenRouter.
  4. Add a `rare_disease` dataset path to `load_data` that ingests our canonical schema and emits questions of the form: `"Patient phenotypes: ... Free text: ... Please list the top 5 most likely rare disease diagnoses, ranked from most to least likely, one per line in the format '1. <Disease Name (ORPHA:XXX)>'."` — no options.
  5. Disable the MCQ-specific code branches (`if args.dataset == 'medqa'` etc.) and replace with a no-fewshot path; or supply minimal rare-disease fewshot examples.
  6. Write a regex parser for the moderator's free-text response to extract a ranked list of disease names; map to Orphanet/OMIM IDs for scoring.
  7. Add an LLM-call budget guard: hard-cap rounds (`num_rounds=2`) and turns (`num_turns=2`) for the intermediate path, otherwise costs blow up on long-tail cases.
- **Open questions**:
  - Do we use all three paths (basic/intermediate/advanced) under the adaptive complexity router, or pin to one for H4? Recommend **all three with the adaptive router** since that *is* MDAgents' contribution — using a single path turns it into a generic multi-agent debate baseline.
  - License clarification — email Yubin Kim. If they confirm permissive use, we can fork and cite; otherwise we re-implement.
  - Should the difficulty classifier see the *full* free-text case or only the chief-complaint summary? README/paper use full question — same here.
  - Embedding/RAG: none in MDAgents by default. Should we add a simple retrieval step (e.g. "look up the 5 nearest HPO-matched cases") for fair comparison with DeepRare? Probably no — keep MDAgents as the "no scaffolding-knowledge" multi-agent baseline.
