# RDMA Run Report

**Date:** 2026-05-11
**Repo path:** `/Users/yutianzhao/Desktop/RDAgentBenchmark/agents/rdma/`
**Status:** PASS (Pillar 1 LLM-only extraction path runs end-to-end on OpenRouter; heavy retrieval / vector-DB path skipped per scope)

---

## Install

- **Host:** macOS 25.2.0, Apple Silicon
- **Python:** 3.13.7 (system `python3`), venv at `agents/rdma/.venv/`
  - RDMA `requirements.txt` pins `spacy==3.8.5`, `sent2vec==0.3.0`, `scipy==1.15.2`, `scispacy`, `stanza==1.10.1`, `bitsandbytes`, `pyhealth` — **none of these have Py3.13 wheels** (`spacy` requires `<3.13`; `sent2vec` requires `<3.12`).
  - We installed a **minimal smoke subset** instead, deferring the heavy retrieval/vector deps (see *Patches*).
- **Commands:**
  ```bash
  cd agents/rdma/
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -U pip
  pip install -r requirements_smoke.txt   # NEW (see Patches)
  pip install groq peft                    # transitive imports inside rdma.utils.llm_client / rdma.hporag.phenogpt
  ```
- **Install duration:** ~3 min total. Notable installed: `torch 2.11.0`, `transformers 5.8.0`, `sentence_transformers 5.4.1`, `openai 2.36.0`, `numpy 2.4.4`, `pandas 3.0.2`, `peft 0.19.1`, `groq 1.2.0`.

## Patches (paths, deps fixes, backbone wiring)

### Deps fixes

| File | Action | Reason |
|---|---|---|
| `requirements_smoke.txt` (NEW) | Trimmed requirements list — kept `openai`, `python-dotenv`, `fuzzywuzzy`, `rapidfuzz`, `nltk`, `joblib`, `ratelimit`, `scipy` (unpinned), `tqdm`, `transformers`, `accelerate`, `numpy`, `pandas`, `torch`, `sentence_transformers`. Dropped `spacy==3.8.5`, `sent2vec==0.3.0`, `scispacy`, `negspacy`, `stanza`, `bitsandbytes`, `pyhealth`, `faiss_cpu==1.10.0`, `fastembed==0.6.1`. | `spacy==3.8.5`, `sent2vec==0.3.0`, `faiss_cpu==1.10.0`, and `fastembed==0.6.1` have no Py3.13 wheels and won't build from source on Apple Silicon without significant work; the dropped deps are needed for **retrieval-enhanced extraction** and **negation/abbreviation/context** pipelines, but not for the **plain-LLM** Pillar 1 entry point (`LLMEntityExtractor`). |
| (pip) | `pip install groq peft` separately after seeing import-time errors. | `rdma/utils/llm_client.py:389` does an unconditional `from groq import Groq` for `APILLMClient`; `rdma/hporag/entity.py:1488` imports `from rdma.hporag.phenogpt import PhenoGPT` which in turn does `from peft import PeftModel`. Both `import` even when you only intend to use `OpenRouterLLMClient` / `LLMEntityExtractor`. Installing the two packages is the cheapest fix; trying to monkey-patch import order is more invasive. |

### Hardcoded paths

`grep -rn "/home/johnwu3\|/shared/rsaas"` returned **~25 matches** across the repo, all in either `scripts/` (CLI defaults) or specific subsystems (`rdma/hporag/phenogpt.py`, `rdma/utils/abbreviation_detector.py`, `rdma/utils/llm.py`, `datasets/raredis.py`, etc.). **None of them are on the smoke-test code path** (which only touches `rdma/utils/llm_client.py::OpenRouterLLMClient` + `rdma/hporag/entity.py::LLMEntityExtractor`). Patching them is deferred to the dataset-integration sprint (each one is a CLI `--default` value, so we'll override via flag rather than editing the repo).

A catalogue of the hardcoded paths discovered is recorded as TODOs:

- `/shared/rsaas/jw3/rare_disease/model_cache` — referenced as `default=` in 11 `scripts/` and `*_steps/` files; also default kwarg in `rdma/utils/llm.py:19`, `rdma/utils/llm_client.py:39,1029`. → patch via `--cache_dir <local>` at script invocation time.
- `/home/johnwu3/projects/rare_disease/workspace/repos/RDMA/data/tools/abbreviations_medembed_sm.npy` — in `rdma/utils/abbreviation_detector.py:44,458`. → only used when `use_abbreviations=True`; not needed for smoke test.
- `/home/johnwu3/projects/rare_disease/workspace/repos/PhenoGPT/model/llama2/llama2_lora_weights` — in `rdma/hporag/phenogpt.py:18`; only used if you instantiate `PhenoGPT`, which we don't.
- `/home/johnwu3/projects/rare_disease/workspace/repos/{BioBERT-MRC,CSC,BioLarkGSC,RareDis,RDD_Corpus,RareDiseaseMention}` — in `datasets/*.py` and `tasks/biobert_mrc_*.py`. → dataset-loader concern, handled in Stream A.

### Skipped components (documented for transparency)

- **`spacy 3.8.5` + `scispacy` + `negspacy`** — Negation/abbreviation expansion / scientific-NER. Not loaded by `LLMEntityExtractor`.
- **`sent2vec 0.3.0`** — Sentence-embedding baseline; used only in `rdma/utils/embedding.py` when `model_type="sent2vec"`; we use `fastembed`/`sentence_transformer` path instead (and even that isn't exercised in the smoke test).
- **`faiss_cpu 1.10.0` + `fastembed 0.6.1`** — Required by `RetrievalEnhancedEntityExtractor` and by `RDMAMatcher` (HPO-term embedding lookup). To run the **full Pillar 1 pipeline** (extraction → verification → matching → HPO codes), these need to be made to install. On Py3.13 we'd need a separate Py3.11 venv or to wait for upstream wheels.
- **`stanza 1.10.1`** — used for sentence segmentation in `rdma/hporag/context.py` (alt path). The default `ContextExtractor.__init__` does *not* require stanza; pure regex-based segmentation is used unless explicitly requested.
- **`bitsandbytes`, `pyhealth`** — local-quantized-LLM and EHR-data utilities; not needed when using OpenRouter and pre-prepared inputs.
- **External Google Drive `.npy` embeddings** (`tools/rd_orpha_medembed.npy`, `tools/abbreviations_medembed_sm.npy`) — **not downloaded.** Needed for the matcher / abbreviation expander, both of which are out of scope for the smoke test. `gdown` install attempt deferred.

## Backbone config

- `rdma.utils.llm_client.OpenRouterLLMClient` was instantiated with the **raw OpenRouter model ID**:
  ```python
  llm = OpenRouterLLMClient(model_type="google/gemini-3-flash-preview", temperature=0.1)
  ```
- Works because the client's `MODEL_MAPPING.get(model_type, model_type)` fallback (`llm_client.py:704`) passes unknown keys straight through to the OpenAI-compatible request. No friendly-name registration required.
- API key picked up from `OPENROUTER_API_KEY` env var (loaded by the smoke-test script from project `.env`).
- The client's `_save_config()` writes a small `openrouter_config.json` to CWD on init — **note for benchmark integration**: this includes the api_key in plaintext. Either chdir to a private temp dir before instantiation, or patch `_save_config` to skip / redact. (Filed under "Blockers" below.)

## Smoke test

### `smoke_test.py` — Pillar 1 entity extraction from a clinical vignette

- **Entry point exercised:**
  ```python
  from rdma.utils.llm_client import OpenRouterLLMClient
  from rdma.hporag.entity import LLMEntityExtractor

  llm = OpenRouterLLMClient(model_type="google/gemini-3-flash-preview", temperature=0.1)
  extractor = LLMEntityExtractor(llm_client=llm, negation=True, family_history=True)
  findings = extractor.extract_entities(EHR_TEXT)
  ```
- **Input:** 95-token DMD-style vignette (7yo boy, calf hypertrophy, Gower sign, CK 18500, maternal uncle died at 19).
- **Wall time:** **4.7 s** (one LLM round trip).
- **Output (verbatim, 6 findings):**
  1. `progressive proximal muscle weakness`
  2. `bilateral calf hypertrophy`
  3. `positive Gower sign`
  4. `difficulty climbing stairs`
  5. `frequent falls`
  6. `markedly elevated serum creatine kinase`
- **Quality:** all six are valid HPO-mappable findings. The `family_history=True` flag correctly excluded the maternal-uncle finding (it never appeared in the output). JSON parsing in `_extract_findings_from_response` (entity.py:188-201) worked first try on the model's response (`{"findings": [...]}`).

This validates the **Pillar 1 mining surface end-to-end** with OpenRouter+Gemini: env load → client init → entity extractor init → LLM call → JSON parse → typed Python list. The downstream HPO-term matcher would consume this list, but it requires the Google Drive embeddings and is intentionally out of scope.

## Status: PASS (with deferred heavy-dep path)

PASS for the Pillar 1 LLM-extractor path that the benchmark harness will actually call.
PARTIAL for the full retrieval-augmented pipeline (extraction → verification → matching → ORPHA-code resolution), which is gated on Py-version downgrade or fresh wheels for `faiss_cpu`/`fastembed`/`spacy`/`sent2vec`.

## Blockers

1. **Py3.13 dep wall.** The retrieval-enhanced path (`RetrievalEnhancedEntityExtractor`, `RDMAMatcher`, `RDMAVerifier(multi_stage)`) cannot be loaded on Py3.13 without rebuilding `spacy 3.8.5`, `sent2vec 0.3.0`, `fastembed 0.6.1`, `faiss_cpu 1.10.0` from source. **Recommendation for the integration sprint:** create a parallel `agents/rdma/.venv-py311/` venv with `python3.11` (install via `pyenv` or `uv`), keep the current Py3.13 venv for the LLM-only path. Total extra disk: ~5 GB.
2. **Google Drive embeddings.** `tools/rd_orpha_medembed.npy` and `tools/abbreviations_medembed_sm.npy` were not downloaded. To unblock matcher/verifier the harness either pulls them via `gdown` at setup time or mirrors them to project-private storage.
3. **`OpenRouterLLMClient._save_config()` leaks the API key.** It writes `openrouter_config.json` containing the key in plaintext. Patch before any shared-disk run.
4. **`rdma.__init__.py` eagerly imports `ModelLoader`** (which `from transformers import BitsAndBytesConfig`). This works on import because `transformers 5.8.0` still ships `BitsAndBytesConfig` as a stub even without the `bitsandbytes` package installed, but if a future `transformers` release moves it behind an `if bitsandbytes:` guard, our smoke test will break. Monitor.

## Notes for benchmark integration

### RDMA Pillar 1 interface — what Python function does the harness call?

**Two layers, recommended one:**

- **Per-text (one call per note) — RECOMMENDED for the harness:**
  ```python
  from rdma.utils.llm_client import OpenRouterLLMClient
  from rdma.hporag.entity import LLMEntityExtractor

  llm = OpenRouterLLMClient(model_type="google/gemini-3-flash-preview", temperature=0.1)
  extractor = LLMEntityExtractor(
      llm_client=llm,
      negation=True,
      family_history=True,
      exclude_etiology=True,
  )
  findings = extractor.extract_entities(ehr_text)  # -> List[str]
  ```
  Returns the raw findings list; HPO-code mapping is a separate step. Cost: 1 LLM call per text. **This is the function our adapter should target for Pillar 1 phenotype-mining benchmarks.**

- **Wrapper (multi-text, with optional context+demographics) — for full Pillar 1 with retrieval:**
  ```python
  from rdma.hpo.extractor import PhenotypeExtractor
  extractor = PhenotypeExtractor(
      llm_client=llm,
      extractor_type="simple",          # "simple" => uses LLMEntityExtractor under the hood
      extract_demographics=False,
  )
  results = extractor.extract([ehr_text])  # -> List[Dict[str, Any]]
  ```
  `extractor_type="retrieval"` enables RAG-style extraction but requires `embeddings_file=...` from Google Drive. `"multi"` runs 5 temperatures and aggregates. `"iterative"` does N passes.

### Other Pillar-1 entry points seen but **not exercised** in this smoke test

- `rdma.rd.extractor` — rare-disease (Orphanet) mention extraction. Same shape (`LLMRDExtractor.extract_from_text(text) -> List[{entity, context}]`), one LLM call, no heavy deps required for the simple `extraction_method="llm"` path. Should work analogously once we wire it up.
- `rdma.hporag.entity.IterativeLLMEntityExtractor` / `MultiIterativeExtractor` — both should work without retrieval deps. Available if we want a higher-recall variant.
- `rdma.rd.verifier.RDMAVerifier(verifier_type="simple")` — first-pass verifier with just LLM (no abbreviation expansion). Skippable but useful for FP reduction.

### Files produced

- `agents/rdma/.venv/` — Python 3.13 venv, ~4 GB on disk (torch + transformers dominate).
- `agents/rdma/requirements_smoke.txt` — minimal install list (NEW).
- `agents/rdma/smoke_test.py` — Pillar 1 LLM-extraction smoke test.
- `agents/rdma/openrouter_config.json` — generated by `OpenRouterLLMClient._save_config()` (contains API key — **do not commit**).

### Next steps for the integration sprint

1. Add a Py3.11 sibling venv (`uv venv --python 3.11 .venv-py311`) and install the full `requirements.txt` there for retrieval + verifier + matcher.
2. Download `tools/*.npy` (Google Drive) via `gdown` and place under `agents/rdma/tools/`.
3. Patch `OpenRouterLLMClient._save_config` to skip writing or redact the api_key.
4. Wrap `LLMEntityExtractor.extract_entities` in our `run_rdma_pillar1(text, backbone) -> List[str]` adapter and feed it the canonical MIMIC-IV / PMC OA case text.
5. Once retrieval venv works, evaluate the difference between `simple` and `retrieval` extractors on a 50-case dev subset and pick the default for the main run.

## Adapter Shim

**File:** `harness/agents/rdma.py` → `RDMAAdapter(AgentAdapter)`, `NAME = "rdma"`.

**Design:**
- Pillar scope: **`P1_extraction` only** (`supports_pillar` returns True only for P1). `predict(pillar=P2..P5)` returns `status="skipped"` with an explanatory message.
- Core entry: `extract_phenotypes(case) -> List[HpoTerm]`. Routes `case.free_text_vignette` → `case.synthetic_vignette` → synthesized "Clinical findings: ..." fallback prose, then subprocesses an inline runner inside `agents/rdma/.venv/bin/python` that imports `rdma.utils.llm_client.OpenRouterLLMClient` + `rdma.hporag.entity.LLMEntityExtractor` and calls `extract_entities(text)`.
- The runner chdir's to a private tempdir before instantiating `OpenRouterLLMClient` to neutralize its `_save_config()` API-key leak (per Blocker #3 in this report). The runner also loads `.env` for `OPENROUTER_API_KEY`.
- `backbone_id` is passed to `OpenRouterLLMClient(model_type=...)` after stripping an optional `"openrouter/"` prefix. The smoke-test-verified raw OpenRouter ID `google/gemini-3-flash-preview` works via the `MODEL_MAPPING` fallback.
- Defaults: `negation=True`, `family_history=True`, `exclude_etiology=True`, `timeout_sec=120`.

**HPO-ID resolution choice:** RDMA's `LLMEntityExtractor.extract_entities` returns **natural-language finding strings** (e.g., `"black tarry stools"`), NOT `HP:\d{7}` IDs. The downstream HPO-code matcher (`rdma/hpo/matcher.py`) requires the deferred Google-Drive embeddings + faiss/fastembed. Per the user instruction, our adapter wraps each phrase as `HpoTerm(id="HP:0000000", label=<phrase>)` — the placeholder ID signals to a downstream normalization step that resolution is pending. Raw phrases are also preserved in `PredictionLog.raw_response_excerpt` as a JSON-encoded list for the normalizer.

**Verification:**
```python
case = next(ingest_rarearena("data/rarearena/benchmark_data/RDS_benchmark.jsonl", "RDS", limit=1))
adapter = RDMAAdapter(backbone_id="openrouter/google/gemini-3-flash-preview")
hpos = adapter.extract_phenotypes(case)
# 8 phrases, all with id=HP:0000000 (placeholder), label = NL phrase:
#   "upper abdominal pain", "black tarry stools", "easy fatigability",
#   "breathlessness", "palpitations", "severe anemia", "pallor",
#   "hemoglobin level of 5.7 g/dL"
log = adapter.predict(case, pillar="P1_extraction", eval_mode="end_to_end")
# status=ok, latency_ms=6514, extracted_hpo_terms all "HP:0000000",
# raw_response_excerpt holds the original phrases as JSON.

# Non-P1 routing:
log2 = adapter.predict(case, pillar="P2_phenotype_ddx", eval_mode="gold_hpo")
# status="skipped", error_message="RDMA adapter only supports P1_extraction; got P2_phenotype_ddx"
```


---

## Bug Fix 2026-05-15 (Phase-0 retro)

**Bug D2** (round2_plan.md § 复盘 ①): `cost.cost_usd` was 0 across the
50-case Mini Phase 0 sample despite valid `prompt_tokens` /
`completion_tokens` counts (estimated via char-count heuristic).

**Fix** in `harness/agents/rdma.py`:
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
`RDMAAdapter(backbone_id="openrouter/google/gemini-3-flash-preview")`
→ `log.cost.cost_usd > 0` on a single PP-Store case.
