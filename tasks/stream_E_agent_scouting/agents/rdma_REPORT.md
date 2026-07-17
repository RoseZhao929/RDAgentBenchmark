# RDMA Scouting Report

## Repo

- **URL**: https://github.com/jhnwu3/RDMA
- **Stars**: 3 (as of 2026-05-11; very young repo)
- **License**: **None declared** (no `LICENSE` file in repo). Implicitly all-rights-reserved by author. We should email John Wu / Adam Cross / Jimeng Sun to clarify — for academic benchmark inclusion this is usually fine, but reviewer might ask.
- **Last pushed**: 2026-05-10 (commit `9c994e4`, "more refactors for bert baselines") — **actively maintained right now**, but with refactors in progress.
- **Language**: Jupyter Notebook (per GitHub) but the actual library code is Python (`rdma/` package with ~12 modules)
- **Paper citation**: John Wu, Adam Cross, Jimeng Sun, "RDMA: Cost Effective Agent-Driven Rare Disease Discovery within Electronic Health Record Systems", arXiv:2507.15867 (submitted July 14, 2025)
- **Community vs official**: This is the **official** repo of the paper authors (jhnwu3 = John Wu, first author). Not a port.
- **Cloned to**: `/Users/yutianzhao/Desktop/RDAgentBenchmark/agents/rdma/`

## Install Complexity

**Medium-High (~3.5/5).**

- 22-line `requirements.txt` includes heavy deps: `faiss_cpu`, `fastembed`, `scispacy`, `spacy==3.8.5`, `sent2vec==0.3.0`, `stanza==1.10.1`, `transformers`, `accelerate`, `bitsandbytes`, `pyhealth`, `sentence_transformers==3.4.1`, `negspacy`.
- **External downloads required**: pre-computed embeddings files served via **Google Drive** (not auto-downloaded): https://drive.google.com/file/d/16wpcexHf2KDZ4w2qBHrTp8dn1oa59ABM/. Must place under `tools/`. This is a **manual step risk** for reproducibility / Docker builds.
- `sent2vec` build often fails on Apple Silicon and modern Linux; may need a forked wheel or a Docker base image with build tools.
- No Dockerfile.
- Several scripts have **hardcoded absolute paths to the author's CS-dept machine** (e.g. `/home/johnwu3/projects/rare_disease/workspace/repos/RDMA`, `/shared/rsaas/jw3/...`) — see `scripts/raredis/run_rdma.py:22,40-50`. Must be edited or symlinked.
- Local-model mode (`--llm_type local`) wants HuggingFace gated models (Llama-3, Qwen, Mistral) → token + GPU required. OpenRouter (`--llm_type openrouter`) is the no-GPU path.

## Backbone Configuration

Supported backends via `--llm_type` flag (`rdma/utils/llm_client.py`):

| Flag | Class | Notes |
|---|---|---|
| `local` | `LocalLLMClient` | HuggingFace transformers; needs GPU + `model_cache` dir |
| `api` | `APILLMClient` | Groq API (rate-limited) |
| `openrouter` | `OpenRouterLLMClient` | OpenAI-compatible, hundreds of models, free tiers |
| `azure` | `AzureOpenAILLMClient` | Azure OpenAI |
| `llama_cpp` | `LlamaCppLLMClient` | GGUF quantized local |

All implement a single abstract method `query(user_input, system_message) -> str` (`benchmark_llm.py:26-31`). Trivial to swap backbones. **No tools/function-calling assumed** — RDMA uses prompt-and-parse-JSON.

- **Default**: per-script via `--model_type qwen_32b` or `nemotron-120b` (OpenRouter free tier).
- **OpenAI-compatible**: yes, via OpenRouter or Azure. DeepSeek available through OpenRouter (`deepseek/deepseek-r1:free` shortcut + raw IDs accepted).
- **GPT-5 access**: scripts at `scripts/test_gpt5_*.py` and `--model_type gpt-5-john` suggest the authors tested GPT-5 via Azure.
- **Environment**: `.env` loaded with `OPENROUTER_API_KEY`, `GROQ_API_KEY`, `HF_API_KEY`, `ACCESS_TOKEN`.

## I/O Schema

**Two ways in:**

### A. Library-level (recommended for our harness)

```python
from rdma.rd.extractor import RDMAExtractor
from rdma.rd.verifier import RDMAVerifier
from rdma.rd.matcher import RDMAMatcher

extractor = RDMAExtractor(
    llm_client,                          # any LLMClient subclass
    extraction_method="retrieval",       # "llm"|"retrieval"|"iterative"|"multi"
    embedding_manager=...,               # required for retrieval
    embedded_documents=...,              # pre-loaded .npy
    top_k=10,
)
entity_contexts = extractor.extract_from_text(clinical_text)
# -> List[{"entity": str, "context": str}]
```

Input: free clinical text (string).
Output: list of `{entity, context}` dicts, after verification stage you get ORPHA-coded predictions.

### B. Script-level (CLI)

```bash
python scripts/run_raredis.py --llm_type openrouter --model_type nemotron-120b \
  --embeddings_file tools/rd_orpha_medembed.npy \
  --use_abbreviations --abbreviations_file tools/abbreviations_medembed_sm.npy \
  --output results/raredis_predictions.jsonl
```

Output JSONL: per-document predictions with extracted entities + ORPHA IDs + confidence.

### Differential diagnosis (DDx) hook

`diff_diagnosis/benchmark_llm.py` provides `benchmark_rare_disease_diagnosis(data, llm_client, ...)` that takes a dict with `matched_phenotypes` (HPO terms) and returns top-10 diseases ranked. **Input format** expects `data[case_id]["matched_phenotypes"] = [{"phenotype": "..."}]`. **Output**: Hits@1/5/10 and a top-10 list per patient. Uses a single LLM call per case with a strict JSON output prompt (no agent loop here — it is a baseline LLM caller, not the multi-agent pipeline).

## Architecture-Specific (Mining Sub-Agents)

RDMA is structured as a **pipeline of mining sub-agents**, not a single multi-agent panel:

| Stage | Module | Role |
|---|---|---|
| Step 1 — Extract | `rdma/rd/extractor.py` → `LLMRDExtractor` / `RetrievalEnhancedRDExtractor` / `IterativeLLMRDExtractor` / `MultiIterativeRDExtractor` | Pull rare disease mentions out of clinical text. 4 extraction strategies. |
| Step 2 — Verify | `rdma/rd/verifier.py` → `RDMAVerifier` (`verifier_type` ∈ `simple`, `multi_stage`, etc.) | Filter false positives. Reduces hallucinated entities. Multi-stage verifier is the key F1-booster. |
| Step 3 — Match | `rdma/rd/matcher.py` → `RDMAMatcher` | Match verified entities to ORPHA codes via embedding retrieval + LLM disambiguation. |
| Step 4 — Supervise | `rdma/rd/supervisor.py` → `RDMASupervisor` | Error correction, FP/FN analysis vs ground truth (eval-time only). |

There are **parallel pipelines for HPO-phenotype mining** under `rdma/hpo/` and `rdma/hporag/`:

- `rdma/hpo/extractor.py` + `matcher.py` + `verifier.py` + `embedding_fuzzy_matcher.py` — phenotype-to-HPO term extraction.
- `rdma/hporag/` — larger HPO retrieval-augmented variant (`pipeline.py`, `verify.py` at 89k LOC, `entity.py` at 57k LOC, `phenogpt.py`).
- `rdma/rdrag/` — RD RAG pipeline (alternative to `rd/`), with `AutoRD.py`, `entity.py`, `rd_match.py`, `supervisor.py`, `verify.py`.

**The "mining sub-agents" are not personas with prompts** (unlike MAI-DxO's 8 doctors). They are **stage-specific Python classes**, each implemented around an LLM call plus retrieval/verification logic. The "agent" framing in the paper refers to specialized prompted extractors and verifiers, not autonomous role-playing agents.

## LLM Call Sites

- `rdma/utils/llm_client.py`: 5 `LLMClient` subclasses, all with `query(user_input, system_message) → str`. **Single chokepoint** — easy to add token-counting wrapper.
- Per extraction stage:
  - **`llm` method**: 1 call per document.
  - **`retrieval` method**: 1 call per document, conditioned on top-k embedding neighbors.
  - **`iterative` method**: up to `max_iterations` (default 3) calls per document.
  - **`multi` method**: 5 calls per document at different temperatures (0.01, 0.1, 0.3, 0.7, 0.9), then aggregated.
- Verifier (multi-stage): adds ~1-3 calls per extracted entity.
- Matcher: 1 call per verified entity for disambiguation.

**Per-case LLM call estimate**: For a typical MIMIC note with 5-10 candidate rare-disease mentions, the multi-stage `retrieval + verify + match` pipeline uses ~10-30 LLM calls total. **An order of magnitude cheaper than MAI-DxO**, consistent with the paper's 10× cost-reduction claim.

## Risk: **MEDIUM**

Reasons:

1. **No LICENSE file** — academic use likely OK, but if reviewers or downstream users care, we need clarification. Recommend opening an issue or emailing John Wu.
2. **Heavy dependency footprint** with `sent2vec` (often build-fails), pinned `scipy==1.15.2`, `spacy==3.8.5`, etc. Probably needs a dedicated conda env.
3. **External Google Drive download** for embeddings files — non-reproducible if the link rots. We should mirror these files in our infrastructure.
4. **Hardcoded absolute paths** to author's machine in scripts; many scripts under `scripts/` have authored-on-his-cluster paths that must be edited.
5. **Repo actively refactoring** — last commit literally **yesterday (2026-05-10)** and message says "more refactors for bert baselines". API may shift under us during the sprint.
6. **3 stars, single-author repo** — bus-factor risk; no community to triage issues.
7. **No tests directory.**

Reasons it is **not high risk**:

- The library code (`rdma/rd/`, `rdma/hpo/`) is well-modularized; we can import only what we need.
- Backbone is fully decoupled (`LLMClient` ABC). Trivial to wrap with our cost tracker.
- The author already wired OpenRouter, Azure, Groq, llama-cpp, local — broad coverage.
- README is detailed with concrete command examples and step-by-step run modes.
- Recent commits mean the author is responsive and we can file issues.

## Next Steps for Benchmark Integration

### Pillar placement

**RDMA is squarely Pillar 1 (phenotype/disease extraction from raw EHR text), with a DDx-style baseline appendix.**

Concretely:
- **Pillar 1 (HPO term extraction from EHR)**: USE `rdma/hpo/` or `rdma/hporag/`. Direct fit — extract HPO terms from MIMIC-IV notes / PMC case reports.
- **Pillar 1 (rare disease mention extraction)**: USE `rdma/rd/` — extract Orphanet-coded disease mentions from EHR. Direct fit for **MIMIC-IV rare disease slice** construction (we can even reuse this as one of our pipelines for building the MIMIC-RD slice).
- **Pillar 2 (HPO-only DDx)**: USE `diff_diagnosis/benchmark_llm.py::benchmark_rare_disease_diagnosis` — this is a thin LLM-call baseline taking HPO phenotypes → top-10 diseases. Not really an "agent" path; more of a baseline-style runner. **Probably the weakest fit** for RDMA's strengths.
- **Pillar 3 (genotype-aware DDx)**: NOT supported. RDMA does not consume variant/gene data.
- **Pillar 4 (family-aware)**: NOT supported.

**Recommendation**: Position RDMA primarily on **Pillar 1** (where it shines and matches the paper's claim). Use it on:
- MIMIC-IV rare disease slice (extraction F1 vs ground-truth ORPHA codes)
- PMC OA cutoff-after holdout (mention extraction)

For **Pillar 2 (DDx)**, optionally include `diff_diagnosis/benchmark_llm.py` as a secondary RDMA-DDx data point, but expect it to underperform DDx-specialized agents like DeepRare and MAI-DxO — that is the *intended* finding (RDMA's contribution is mining, not DDx).

### Adapter wrapper

```python
# Minimal harness wrapper for Pillar 1
from rdma.rd.extractor import RDMAExtractor
from rdma.rd.verifier import RDMAVerifier
from rdma.rd.matcher import RDMAMatcher
from rdma.utils.embedding import EmbeddingsManager
from rdma.utils.llm_client import OpenRouterLLMClient  # or APILLMClient, AzureOpenAILLMClient

llm = OpenRouterLLMClient(api_key=..., model="nvidia/nemotron-3-super-120b-a12b:free")
emb_mgr = EmbeddingsManager.load("tools/rd_orpha_medembed.npy")
extractor = RDMAExtractor(llm, extraction_method="retrieval",
                          embedding_manager=emb_mgr, embedded_documents=docs)
verifier = RDMAVerifier(llm, verifier_type="multi_stage",
                        use_abbreviations=True, abbreviations_file="tools/abbreviations_medembed_sm.npy")
matcher = RDMAMatcher(llm, emb_mgr)

# Per case
ents = extractor.extract_from_text(note)
ents = verifier.verify(ents, note)
orpha = matcher.match(ents)
```

### Pre-sprint checklist

1. **Mirror Google Drive embeddings file** to our project's `data/external/rdma/` directory so we are not Drive-dependent.
2. **Build a clean conda env** for RDMA: pin Python 3.10, install requirements, isolate from MAI-DxO env (different dependency versions). Verify `sent2vec` builds.
3. **Patch hardcoded paths** in `scripts/run_*.py` — make them read from env vars or config.
4. **Email John Wu** to (a) request a LICENSE file for academic use, (b) ask which `rdma/rd/` vs `rdma/rdrag/` is the paper-canonical pipeline (there are two overlapping implementations).
5. **Smoke test**: run `scripts/run_raredis.py --llm_type openrouter --dev --debug` on 2-document subset to verify the full E2E pipeline before the sprint.
6. **Decide on backbone parity**: for fair comparison with MAI-DxO and DeepRare, run with DeepSeek V3.2 + GPT-5 (same two backbones as the rest of the benchmark) via OpenRouter and Azure respectively.
