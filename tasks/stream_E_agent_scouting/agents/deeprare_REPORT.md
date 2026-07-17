# DeepRare Scouting Report

## Repo
- **URL**: https://github.com/MAGIC-AI4Med/DeepRare
- **Stars**: 226
- **License**: NOASSERTION on GitHub metadata, but `LICENSE` file in repo + badge in README declare **CC BY-NC 4.0** (academic-use only, non-commercial). Note: the dataset on HF (`Angelakeke/DeepRare`) is also gated/CC BY-NC.
- **Last commit (push)**: 2026-04-14
- **Primary language**: Python (~17.6 MB repo)
- **Paper**: Zhao W. et al., "An agentic system for rare disease diagnosis with traceable reasoning", *Nature*, 2026 (arXiv 2506.20430). Web app: http://deeprare.cn

## Install Complexity
- **Python**: 3.8+ stated in README. requirements.txt pins very recent libs (numpy==2.3.5, torch==2.9.1, transformers==4.57.3, pydantic==2.12.5, openai==2.9.0, anthropic==0.75.0). Practically this implies **Python 3.10+** (numpy 2.3 drops <3.10). Pin set is heavy and brittle.
- **Dependencies summary**: ~150 packages. Notables: `torch + transformers + datasets + huggingface-hub` (downloads BioLORD-2023-C BERT + MedCPT-Cross-Encoder cross-encoder); LangChain ecosystem (langchain-classic 1.0.0, langchain-community 0.4.1, langchain-core 1.1.1); `selenium` + `trio` + `chromedriver` for web scraping; `duckduckgo_search`, `wikipedia`, `arxiv`, `bs4`, `google-api-python-client`; bundles full CUDA 12.8 wheel set (nvidia-cublas-cu12 etc.) — pip install will pull ~5-10 GB even on a CPU box.
- **External data/checkpoint requirements** (significant):
  - HuggingFace `Angelakeke/DeepRare` dataset repo via `huggingface-cli download` into `./database/` — contains ORPHA disorders JSON, phenotype/disease mapping, orpha2omim mapping, orphanet embeddings tensor, similar-case CSVs with precomputed embeddings (`RDS_embeddings.csv`, `xinhua_rag_0331.csv`, `mimic_rag.csv`, `rarebench_rag.csv`, `mygene_rag.csv`, `ddd_rag.csv`). Note: utils.py *hard-codes* loading **all six** of these CSVs in `set_up_data()`. If any is missing the pipeline crashes.
  - `FremyCompany/BioLORD-2023-C` (HF) — disease-name encoder.
  - `ncbi/MedCPT-Cross-Encoder` (HF) — similar-case re-ranker.
  - **Exomiser CLI 14.1.0** (~20 GB hg19 + hg38 + phenotype data zips, Java 21) — only needed for the gene-aware path (`main_gene.py`), HPO-only path does not need it.
  - **ChromeDriver** matching local Chrome — used by `tools/page_fetch.py` and the web/search tools.
  - **Google Custom Search Engine ID + API key** (Bing/DuckDuckGo also supported). Web search is invoked **per case** in `make_diagnosis`.
- **Install difficulty (1-2 sentences)**: Medium-high. The Python deps are fat but standard pip; the hard parts are (a) needing the HF `database` artifacts including five extra RAG CSVs hard-wired in utils.py, (b) needing a working Chrome+ChromeDriver and a web search key inside the inference loop, (c) Exomiser ~20 GB if you ever want VCF input. Expect 1-2 days to stand up cleanly.

## Backbone Configuration
- **Default backbone**: README/paper say DeepSeek-V3 worked best; default `--model` in argparse is `openai` with `--openai_model gpt-4o`. Four wrappers in `api/interface.py`: `Openai_api`, `deepseek_api`, `gemini_api`, `claude_api`.
- **How to swap**: CLI flag `--model {openai,gemini,deepseek,claude}` plus per-provider `--*_apikey` and `--*_model`. Selection happens in `LLM_handler` class in `main.py` lines 14-26.
- **OpenAI-compatible endpoint (OpenRouter) support**: Yes, easy. `Openai_api.__init__` uses `OpenAI(api_key=api_key)` without an explicit `base_url`. The `deepseek_api` wrapper *already* shows the pattern: `OpenAI(api_key=..., base_url="https://api.deepseek.com")`. Adding `base_url=os.environ.get("OPENAI_BASE_URL")` to `Openai_api` (one-line shim) routes everything through OpenRouter. **Caveat**: `main.py` line 48 instantiates a *second*, hard-coded `Openai_api` for `mini_completion` (gpt-4o-mini) and `get_embedding` (text-embedding-3-small) — these are used for summarizing scraped web pages and for retrieving similar cases. To run fully on OpenRouter we need to (a) point this OpenAI client at OpenRouter too, and (b) confirm OpenRouter exposes an embeddings endpoint or substitute a local embedder. This is a known shim point.

## I/O Schema
- **Input format**: per `data.py:RareDataset`, a tuple `(phenotype_text, golden_diagnosis, phenotype_list, phenotype_ids[, vcf_path])`.
  - `phenotype_text`: free-text concatenation of HPO term names ("HP:0000123 → 'Microcephaly', joined by ', '").
  - `phenotype_ids`: list of HPO IDs (`HP:xxxxxxx`).
  - `vcf_path`: optional, only used in gene-aware path.
  - Built-in dataset loaders for: RAMEDIS, MME, HMS, LIRICAL (loaded from HF `chenxz/RareBench`), Xinhua, MIMIC, mygene, DDD, plus a generic `case` CSV. CSV schema for `mygene`/`DDD` requires columns `phenotype`, `rare_disease` (as stringified lists). MIMIC CSV needs columns `HPO`, `orpha`, separator `|`.
  - **Note**: Free-text → HPO is handled out-of-band by `hpo_extractor.py` (script `extract_hpo.sh`) — DeepRare's diagnosis loop **expects HPO already extracted**.
- **Output format**: per-patient JSON in `results_folder/{dataset}/{model}/patient_{i}.json` with keys: `patient_info`, `golden_diagnosis`, `phenotypes`, `phenotype_ids`, `diagnosis_api_response`, `web_diagnosis`, `zero_shot_llm_response`, `similar_cases`, `first_round_result`, `judge_result` (list of 0/1), `judgements`, `final_diagnois` (sic). Final field is a markdown-formatted ranked top-5 with `## **DISEASE NAME** (Rank #X/5)` headers and a numbered References section — i.e. **ranked list embedded in markdown**, not structured JSON. We will need to parse this for Recall@k metrics.
- **Sample case**: input = `"Microcephaly, Seizures, Developmental delay"` plus `["HP:0000252","HP:0001250","HP:0001263"]`; output = markdown with top-5 bolded disease names and citations.

## LLM Call Sites
- `api/interface.py` — every provider wrapper (`get_completion`, `mini_completion`, `openai_summarize`, `get_embedding`).
- `diagnosis.py:make_diagnosis` — the **main loop**, contains:
  1. `handler.get_completion(system_prompt, prompt)` — zero-shot diagnosis (LLM Diagnosis).
  2. `handler.get_completion(system_prompt, memory_1)` — fused-evidence diagnosis (first round result).
  3. `Check_Agent(...)` in `tools/llm_agent.py` — judgment call per candidate disease against patient (loop up to ~5 candidates).
  4. `Check_Patient_Agent(...)` — similar-case filtering (loop up to ~3 cases).
  5. `handler.get_completion(system_prompt, memory_2)` — final synthesized top-5.
  6. `mini_handler` (gpt-4o-mini) called inside every web-search tool (`web_search.py`, `page_fetch.py`, `search_pubmed.py`, `search_arxiv.py`, `search_wiki.py`) for per-page summarization — *many* calls.
  7. `embedding_handler` (text-embedding-3-small) — once per patient for similar-case retrieval.
- `tools/llm_agent.py` — `Check_Agent`, `Check_Patient_Agent`.
- `hpo_extractor.py` (separate preprocessing stage) — uses LLM to convert free-text to HPO terms.
- **LLM calls per case (estimate)**: with `search_depth=1` and reflection loop running once: ~2 main `handler` calls + ~5 `Check_Agent` calls + ~3 `Check_Patient_Agent` calls + ~10-30 `mini_handler` summarization calls + 1 embedding = **~20-40 LLM calls per case** (highly variable; web search return count multiplies the mini calls). The reflection loop can re-run the whole web+LLM stack a second time if all candidate diseases fail `Check_Agent`. **Budget implication**: at this rate, 1000 cases ≈ 20-40k LLM calls, dominated by gpt-4o-mini summarization. We need cost controls.

## Risk: **HIGH** (but worth keeping — it is the headline rare-disease agent)
- (-) Hard dependency on five RAG CSV files plus an ORPHA embeddings tensor that ship via HF — if HF gating or repo changes, the loop refuses to start (`set_up_data` raises). We need to mirror these locally early.
- (-) Many calls per case + mandatory web scraping (selenium+ChromeDriver) makes runs slow and fragile. CI-like reproducibility is hard; rate-limit, captcha and stale URL failure modes are real.
- (-) Two LLM clients instantiated in `main.py` (configurable + hard-coded gpt-4o-mini); the gpt-4o-mini path is wired in deep (every web-summarizer tool takes `mini_handler` as a param), so swapping to OpenRouter is a multi-file edit, not a one-liner. Same for `text-embedding-3-small` — must replace with a local embedder or an OpenRouter-supported embedding model.
- (-) Reflection loop terminates on a heuristic ("any candidate judged correct"); under our holdout cases the LLM judge may consistently say "incorrect" and burn the loop a second time, doubling cost.
- (-) CC BY-NC license on code *and* the released dataset/embeddings — we should declare this in our paper and ensure no commercial-distribution implication.
- (-) Final output is markdown — not structured. Brittle regex parsing required for Recall@k.
- (+) Repo is current (push 2026-04-14), README is unusually detailed for an academic repo, license file present, 226 stars, four LLM providers wrapped, HPO/Orphanet/OMIM/PubMed tools all present. Code matches paper's claims well.

## Next Steps for Benchmark Integration
- **Adapter shim sketch**:
  1. Add `base_url` env var support to `api/interface.py:Openai_api.__init__` (one line: `base_url=os.environ.get("OPENROUTER_BASE_URL")`). Do the same for the second `Openai = Openai_api(...)` in `main.py:46`. Route both via OpenRouter.
  2. Replace `get_embedding` with a local SentenceTransformer (e.g. BGE-small) **or** call OpenRouter embeddings if available. Bench note: similar-case retrieval is *optional* for accuracy — we could disable it for ablation.
  3. Write a thin parser that takes `final_diagnois` markdown and yields a Python list of `(rank, disease_name)` pairs, then map disease_name → Orphanet/OMIM ID using DeepRare's own `disease_mapping.json` + a fuzzy fallback. Reuse this for Recall@1/5.
  4. Write a `runner.py` that wraps `make_diagnosis` and takes our canonical schema (`{case_id, phenotype_ids, phenotype_names, free_text?, vcf?}`) → writes back DeepRare's expected `(phenotype, disease, list, ids[, vcf])` tuple.
  5. Pre-stage `./database/` once, snapshot to local cache, freeze the HF revision in a `requirements-deeprare.txt`.
- **Open questions**:
  - Do we need the gene-aware path? If yes, Exomiser (~20 GB + Java 21) becomes a hard dep. Likely **not** for v1 (HPO-only is enough for the headline pillars).
  - Can we disable web search entirely (Bing/Google/DuckDuckGo) for a "closed-knowledge" comparable run? `make_diagnosis` will need a small monkeypatch to return an empty `web_diagnosis` string — feasible.
  - Cost ceiling: at ~20-40 LLM calls/case, do we cap at e.g. 200 cases per subset for the first pass and scale up only if it's competitive? Recommended.
  - The hard-coded `mini_handler = gpt-4o-mini` path will not work on OpenRouter without renaming to an OpenRouter alias (e.g. `openai/gpt-4o-mini`). One-line edit but must remember.
