# AgentClinic Scouting Report

## Repo
- URL: https://github.com/SamuelSchmidgall/AgentClinic
- Stars: 304
- License: **MIT** (`LICENSE.txt`, Copyright 2024 Samuel Schmidgall) — clean for academic + commercial use.
- Last commit: 2024-12-31 (last activity 17 months ago as of 2026-05; effectively unmaintained, but stable for a research baseline)
- Primary language: Python
- Paper: Schmidgall, Ziaei, Harris, Reis, Jopling, Moor, "AgentClinic: a multimodal agent benchmark to evaluate AI in simulated clinical environments", arXiv:2405.07960 (2024). Project page: https://agentclinic.github.io
- Local clone: `/Users/yutianzhao/Desktop/RDAgentBenchmark/agents/agentclinic/`

## Install Complexity
- Python: not pinned, but `openai==0.28.0` + `anthropic` (unpinned) + `transformers` + `replicate` + `datasets` suggests Python 3.9–3.11.
- `requirements.txt`: `regex==2023.12.25`, `openai==0.28.0`, `replicate==0.23.1`, `argparse`, `transformers`, `datasets`, `anthropic`.
- External data: **all four scenario files ship with the repo** (`agentclinic_medqa.jsonl` 215 cases, `agentclinic_medqa_extended.jsonl`, `agentclinic_nejm.jsonl` 120 cases, `agentclinic_nejm_extended.jsonl`). The MIMIC-IV scenario file (`agentclinic_mimiciv.jsonl`) is **not in the repo** — README says it requires separate PhysioNet credentialed approval; loader code references the file but you must generate / obtain it yourself.
- NEJM cases embed live image URLs (`csvc.nejm.org`) — requires network at runtime for vision models. For text-only rare-disease use, image fetch can be disabled.
- Difficulty: **medium**. Same `openai==0.28` pre-1.0 SDK issue as MedAgents; framework is single-file (`agentclinic.py`, 681 LOC); no DB / vector store / RAG infrastructure.

## Backbone Configuration
- **Default**: `gpt4` for all 4 agents (doctor / patient / measurement / moderator). Hardcoded model strings in `query_model()`, agentclinic.py line 21.
- **Built-in choices**: `gpt4`, `gpt3.5`, `gpt4o`, `gpt4v`, `gpt-4o-mini`, `o1-preview`, `claude3.5sonnet` (Anthropic SDK), `llama-2-70b-chat` / `llama-3-70b-instruct` / `mixtral-8x7b` (all via Replicate), plus a `HF_<model_path>` prefix for HuggingFace local pipelines (note: at line 172 this branch raises `"Sorry, fixing TODO :3"` — **HF support is broken in current main**).
- **OpenAI-compatible base_url support**: **NO out of the box**. `openai.api_key` is set globally in `main()` line 571 with no `api_base` / `base_url`; everywhere a model is called the OpenAI SDK is invoked against the public `api.openai.com` endpoint. However, **per-agent backbone selection is already first-class** (`--doctor_llm`, `--patient_llm`, `--measurement_llm`, `--moderator_llm` are separate CLI args) — the architecture is much better than MedAgents for swap experiments. We only need to:
  1. Replace each `openai.ChatCompletion.create(model=..., messages=..., ...)` block with a single `LLMClient.chat(provider, model, ...)` helper. There are ~10 nearly-identical blocks in `query_model()` (lines 39–167) — almost mechanical to refactor.
  2. Add `base_url` plumbing so DeepSeek V3.2 / Gemini (via OpenAI-compat) / GPT-5 can be selected by `--doctor_llm deepseek-v3.2` etc.
  3. The Claude path already uses the `anthropic` Python SDK correctly.
- Estimated rework: **roughly half a day** to consolidate `query_model()` and wire `base_url`. Significantly easier than MedAgents because of the per-agent CLI surface.

## I/O Schema
- **Input**: per-case JSONL row. NEJM schema (the one most relevant for rare disease):
  ```json
  {"image_url": "https://csvc.nejm.org/.../IC20240111...",
   "question": "A 55-year-old woman ... What is the most likely diagnosis?",
   "patient_info": "For your role as a patient, you are a 55-year-old woman ...",
   "physical_exams": "Dermoscopy findings: ... Skin biopsy results: ...",
   "answers": [{"text": "Contact dermatitis", "correct": false}, ..., {"text": "Exogenous ochronosis", "correct": true}, ...]}
  ```
  MedQA schema is richer: nested `OSCE_Examination` dict with `Test_Results`, `Correct_Diagnosis`, `Patient_Actor`, `Objective_for_Doctor`, `Physical_Examination_Findings`.
- **Output**: **streamed to stdout only** in current main (`print("Doctor [{}%]:")` etc.). No JSON dump file. For benchmarking we must add output redirection / capture (each case logs the full dialogue + final diagnosis verdict from the moderator). The moderator's correct/incorrect verdict is at agentclinic.py line 643.
- **Sample interaction**: doctor agent asks the patient up to `total_inferences=20` turns of dialogue, can issue `REQUEST TEST: [test]` to the measurement agent (returns test results from `physical_exams`), and finally emits `DIAGNOSIS READY: [diagnosis]`. The moderator LLM then judges if that diagnosis matches the gold via a 1-call yes/no comparison.

## LLM Call Sites
All LLM calls funnel through `query_model()` (agentclinic.py lines 20–178). Three agent classes (`PatientAgent`, `DoctorAgent`, `MeasurementAgent`) each have an `inference_*` method, plus a free function `compare_results()` for the moderator.

| Caller | File / function | When |
|---|---|---|
| Doctor turn | `DoctorAgent.inference_doctor` (line 512) | up to `total_inferences=20` per case |
| Patient turn | `PatientAgent.inference_patient` (line 434) | up to `total_inferences=20` per case |
| Measurement turn | `MeasurementAgent.inference_measurement` (line 546) | only on `REQUEST TEST` |
| Moderator verdict | `compare_results` (line 565) | exactly 1 per case at diagnosis time |

**Estimated cost per case**: 20 dialogue turns × 2 agents (doctor + patient) ≈ **40 calls** worst case + ~2-5 measurement calls + 1 moderator call ≈ **~45 LLM calls per case**. At 60k cases this is ~2.7M calls — by far the heaviest of the agent zoo. **Cost-control levers**: lower `--total_inferences` (e.g. 8 or 10 — many cases naturally finish in fewer turns) and route patient + measurement agents to a cheap backbone (DeepSeek) while keeping the doctor on the expensive one. The per-agent CLI flags make this trivial.

## Multi-agent Architecture
Four fixed roles communicating through a turn-based simulated clinical visit:
- **DoctorAgent** (`agentclinic.py` line 455) — drives the conversation, can issue `REQUEST TEST: ...`, eventually emits `DIAGNOSIS READY: ...`. Optional cognitive bias prompt (12 types: recency, frequency, confirmation, etc.).
- **PatientAgent** (line 381) — answers in 1–3 sentence dialogue, never reveals the disease, has its own bias options (11 types including self_diagnosis).
- **MeasurementAgent** (line 533) — returns test results from the scenario's `physical_exams` dict; falls back to `NORMAL READINGS` if not present.
- **Moderator** (free function `compare_results`, line 565) — single-call LLM judge: "are these the same disease? Yes/No".

**Communication protocol**: text-only dialogue passed by string concatenation (`self.agent_hist += question + "\n\n" + answer`). The main control loop (line 622) routes based on `REQUEST TEST` / `DIAGNOSIS READY` / `REQUEST IMAGES` substring detection in the doctor's last utterance. No structured messages, no tool API; this is a "string protocol" multi-agent system. There is also a `human_doctor` / `human_patient` `inf_type` for hybrid runs (line 666).

Vision support exists (`gpt4v`, `gpt4o`) — sends the NEJM image URL in the OpenAI vision message format. **Rare-disease benchmark caveat**: most of the published rare-disease cases we use (Phenopacket-Store, RareBench, RareArena) are text-only, so the multimodal capability is not really exercised; AgentClinic's NEJM image-based reasoning is the only multimodal path.

## Risk: **medium**
Reasons:
- **MIT license, per-agent backbone CLI, single-file 681-LOC codebase** — the cleanest of the two agents in this stream from an integration standpoint.
- **`openai==0.28` pre-1.0 SDK** is the main code-level hazard — need to rewrite `query_model()` for the modern client + `base_url`. Mechanical change but touches ~10 near-duplicated blocks.
- **Output is print-only** — must add structured logging (JSONL per case with full dialogue + verdict) before any large-scale run. Reviewer would want raw transcripts in supplement.
- **Up to ~45 LLM calls per case** is the highest per-case cost in the agent zoo. Need to (a) cap `--total_inferences`, (b) route patient/measurement to cheap backbone, (c) consider batching cases at the moderator step.
- **Moderator-as-judge concern**: gold-standard verdict comes from a single LLM call ("Yes/No, same disease?"). This is a known weakness — we should additionally extract `DIAGNOSIS READY: [text]` and apply a deterministic exact / fuzzy match against the gold diagnosis as a robustness check.
- **HuggingFace path is broken** (line 172, explicit `raise`). If we want a local-model fallback we must finish that branch ourselves.
- **NEJM cases hit a live NEJM CDN for images** — if cases are rate-limited / take down the CDN, runs stall. Pre-cache images locally.

## Next Steps for Benchmark Integration
1. **Refactor `query_model()`** into a thin `LLMClient(provider, model, base_url, api_key, temperature, max_tokens)` wrapper. Use the same wrapper across all four agents (`PatientAgent`, `DoctorAgent`, `MeasurementAgent`, moderator). ~half a day. This buys us DeepSeek + Gemini + GPT-5 via OpenAI-compatible endpoints.
2. **Add structured output**: instead of `print(...)`, append `{"case_id", "scenario_idx", "doctor_dialogue", "patient_dialogue", "measurement_dialogue", "final_diagnosis", "gold_diagnosis", "moderator_verdict", "n_turns", "tokens_in", "tokens_out"}` to a per-run JSONL. Required for downstream eval + paper supplement.
3. **Plug in rare-disease data**: write a `ScenarioLoaderRareDisease` class (mirroring `ScenarioLoaderNEJM`) that maps Phenopacket-Store / RareBench / RareArena cases to AgentClinic's `(question, patient_info, physical_exams, gold_diagnosis)` schema. Phenopackets give HPO terms — render these as a "Patient_Actor" persona via a one-time templating pass.
4. **Cost cap**: default to `--total_inferences=10` for the rare-disease benchmark; route `--patient_llm` and `--measurement_llm` to DeepSeek V3.2 (cheap), keep `--doctor_llm` and `--moderator_llm` on GPT-5 / Claude Sonnet 4.5.
5. **Dual judging**: alongside the existing moderator yes/no, add a deterministic match (Orphanet/OMIM ID match against gold) to defuse the "LLM-as-judge" critique.
6. **Pre-cache NEJM images locally** if the multimodal stream is used; otherwise run text-only by setting `--doctor_image_request False`.
