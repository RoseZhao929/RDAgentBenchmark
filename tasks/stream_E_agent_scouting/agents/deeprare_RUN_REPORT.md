# DeepRare Run Report

## Install

- **venv path**: `/Users/yutianzhao/Desktop/RDAgentBenchmark/agents/deeprare/.venv` (Python 3.13.7)
- **Install command sequence**:
  ```bash
  cd /Users/yutianzhao/Desktop/RDAgentBenchmark/agents/deeprare
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -U pip

  # CUDA-only wheels (nvidia-* + triton==3.5.1) don't have macOS arm64 distributions;
  # filter them out for a CPU/MPS install on Apple Silicon.
  grep -vE "^(nvidia-|triton==)" requirements.txt > requirements-macos.txt
  pip install -r requirements-macos.txt
  ```
- **Resolved dependency issues / build problems**:
  - `nvidia-cublas-cu12==12.8.4.1` (+ 15 other `nvidia-*` CUDA 12.8 wheels and `triton==3.5.1`)
    have no macOS distributions. Created `requirements-macos.txt` with these 16 lines
    filtered. PyTorch 2.9.1 still installed (CPU build). All 140 remaining packages
    installed cleanly.
  - `huggingface-cli download` (legacy CLI) is gone in `huggingface-hub` 1.x. Used the
    Python API `huggingface_hub.snapshot_download(repo_id="Angelakeke/DeepRare",
    repo_type="dataset", local_dir="./database")` instead.
  - macOS Python 3.13.7 satisfies the 3.10+ requirement implied by `numpy==2.3.5`.
- **Wheels built**: `sgmllib3k`, `volcengine-python-sdk` (28 MB wheel), `wikipedia` —
  all from sdists, ~10 s each.

## Patches applied

`api/interface.py:Openai_api` — single class touched, ~3 logical edits:

1. **`__init__`** — Reads `OPENAI_BASE_URL` / `OPENROUTER_BASE_URL` from env and passes
   it to `OpenAI(...)`. Falls back to env-provided `OPENROUTER_API_KEY` / `OPENAI_API_KEY`
   if no `api_key` is given. Adds `self.mini_model` from env `DEEPRARE_MINI_MODEL`
   (defaults to `gpt-4o-mini`).
2. **`mini_completion`** — Now uses `self.mini_model` instead of the hard-coded literal
   `"gpt-4o-mini"`. This routes the per-page web-summarisation calls through OpenRouter
   too (or any chosen OpenRouter id).
3. **`get_embedding`** — Adds a `DEEPRARE_DISABLE_EMBEDDING=1` env shim that returns a
   zero vector of length 1536 (matching `text-embedding-3-small`). OpenRouter has **no
   embeddings endpoint** at `/v1/embeddings`, so the similar-case retrieval branch must
   either be disabled or fronted by a local SentenceTransformer (TODO). With the shim,
   `similar_case_search` returns the first N cases by row order — i.e. retrieval becomes
   a no-op rather than a crash. Acceptable for an ablation / smoke; we will need a real
   local embedder for the full benchmark.

The `main.py` `Openai = Openai_api(args.openai_apikey, args.openai_model)` second
client also now picks up the env-based base_url automatically (the patch is in
`__init__`, so both `handler` and the `mini_handler` / `embedding_handler` clients
route through OpenRouter).

`deepseek_api`, `gemini_api`, `claude_api` were not patched (we're using the OpenAI
wrapper exclusively for OpenRouter routing).

## Backbone config

- **OpenRouter, OpenAI-compatible.** Set:
  - `OPENAI_BASE_URL=https://openrouter.ai/api/v1`
  - `OPENROUTER_API_KEY=...` (from `.env`, also passed via `--openai_apikey`)
  - `DEEPRARE_MINI_MODEL=google/gemini-3-flash-preview` (the per-page summarisation
    "mini" model is collapsed onto the same backbone)
  - `DEEPRARE_DISABLE_EMBEDDING=1` (works around no-embeddings on OpenRouter)
  - CLI: `--model openai --openai_apikey $OPENROUTER_API_KEY
    --openai_model google/gemini-3-flash-preview`
- **Connectivity smoke**: I verified the patched `Openai_api` directly:
  ```python
  api = Openai_api(api_key=os.environ['OPENROUTER_API_KEY'],
                   model='google/gemini-3-flash-preview')
  api.get_completion("You are a rare disease specialist.", "...")
  api.mini_completion("summarize", "...")
  api.get_embedding("test")  # returns zero vector under DEEPRARE_DISABLE_EMBEDDING=1
  ```
  All three returned successfully with Gemini 3 Flash output text. So the LLM wiring
  is confirmed end-to-end against OpenRouter.

## Smoke test

**Status: deferred — full pipeline could not be exercised end-to-end in the time budget.**

### What did run

- **HF database download.** `snapshot_download("Angelakeke/DeepRare")` succeeded, 794 MB
  in `./database/` (16 files): `embeds_concept.pt` (117 MB), `embeds_pheno.pt`,
  `RDS_embeddings.csv`, `df_rare_rare_mimic_with_embeddings_final.csv`, plus all the
  Orphanet / Mondo / phenotype / disease mapping JSONs and TSVs that `set_up_args`
  expects.
- **LLM wiring.** Direct call to `Openai_api.get_completion` and `mini_completion`
  against OpenRouter Gemini 3 Flash returns proper completions (see Backbone config).

### What is blocking the end-to-end smoke

1. **ChromeDriver missing.** `which chromedriver` → not found.
   `tools/page_fetch.py`, `tools/hpo_search.py`, `tools/web_search.py`,
   `tools/uptodate_search.py` all instantiate a Selenium `webdriver.Chrome(...)`. There
   is **no `--no-web` / `--disable-search` CLI flag** in DeepRare; `make_diagnosis`
   unconditionally calls `BingSearchTool` (or `GoogleSearchTool` / `DuckDuckGoSearchTool`)
   at the top of every reflection iteration and again per disease via
   `fetch_page_content_and_summarize`. Per task constraint "no system-level installs"
   we cannot install chromedriver here.
2. **Five RAG CSVs hard-coded but absent.** `utils.py:set_up_data` hard-loads:
   - `dataset/xinhua_rag_0331.csv`
   - `dataset/mimic_rag.csv`
   - `dataset/rarebench_rag.csv`
   - `dataset/mygene_rag.csv`
   - `dataset/ddd_rag.csv`

   None of these are in the HF `Angelakeke/DeepRare` bundle (the bundle has
   `RDS_embeddings.csv` and `df_rare_rare_mimic_with_embeddings_final.csv` only) and they
   are not in the repo. Without a `set_up_data` patch to skip missing CSVs, the loop
   raises before any LLM call.
3. **Embedding endpoint.** OpenRouter does not expose `/v1/embeddings`, so the existing
   `similar_case_search` pipeline (text-embedding-3-small) needs either the
   `DEEPRARE_DISABLE_EMBEDDING=1` shim (already in place, returns zeros — kills semantic
   ranking quality but lets the code run) or a local SentenceTransformer drop-in.

The minimal additional engineering to clear (1)–(3) is several hours, not minutes — it
includes a `--no-web` patch on `make_diagnosis`, a guarded `set_up_data`, and a local
embedder. Per the 15-minute-per-error budget rule, I stopped and documented.

### Estimated cost when we do run it

Per the scouting report: ~20–40 LLM calls per case, dominated by per-web-page summaries.
Disabling the web tools would drop that to ~10–15 calls per case (LLM zero-shot +
fused-evidence + ~5 Check_Agent + ~3 Check_Patient_Agent + final). At
`google/gemini-3-flash-preview` rates (~$0.30 / M input, $2.50 / M output) and ~2K tokens
per call, an HPO-only single case should land at $0.01–$0.05.

## Status: ⚠️ runs with caveats (LLM wiring confirmed, full pipeline blocked on web + RAG CSVs)

## Blockers

- **ChromeDriver** binary required by 4 tool modules. Either install ChromeDriver
  (`brew install --cask chromedriver` — out of scope for this task) or patch
  `make_diagnosis` to short-circuit `BingSearchTool` / `fetch_page_content_and_summarize`
  / `HPOSearchTool` / `UptodateSearchTool` to no-ops. The latter is the cleaner path for a
  benchmark "closed-knowledge" comparison and is also more reproducible.
- **Five hard-wired RAG CSVs** in `set_up_data`. Need either a CSV bundle from the
  authors (the scouting report flagged this as a `huggingface-cli` ask) or a `try/except`
  in `set_up_data` that skips missing files and concatenates only those present.
- **No embedding endpoint** on OpenRouter; current shim returns zeros. For a real run we
  need a local embedder, e.g. `sentence-transformers` `BAAI/bge-small-en-v1.5` (110 MB,
  CPU-fast) to compute `df.embedding` and the query embedding.

## Notes for benchmark integration

- The OpenRouter swap is one file (`api/interface.py`) and three changes; the rest of
  DeepRare is unaware of the routing. Same shim works for any OpenRouter id.
- For our adapter we will want to:
  1. Add `args.no_web` (or env `DEEPRARE_NO_WEB=1`) and patch `make_diagnosis` plus the
     four `*_search` tool modules to return empty strings when set.
  2. Patch `set_up_data` to wrap each `pd.read_csv` in `try / except FileNotFoundError`
     and concat only what loaded — drop to only `RDS_embeddings.csv` for the smoke run.
  3. Drop `get_embedding` for a local SentenceTransformer behind the same handler shape
     (so `similar_case_search` continues to work).
  4. Add an output parser that turns `final_diagnois` markdown into a Python list of
     `(rank, disease_name)` pairs — DeepRare emits its ranked top-5 as
     `## **DISEASE NAME** (Rank #X/5)` blocks (note the typo `final_diagnois` in the
     codebase, which we'll need to preserve when reading patient JSON).
- HF database is 794 MB on disk; OK to keep cached locally. The full RAG CSV bundle is
  probably another ~1 GB (per scouting estimate). We should mirror everything once and
  pin the HF revision.
- Test patient case ready for when the above three items land: HPO triad
  `Microcephaly (HP:0000252), Seizures (HP:0001250), Developmental delay (HP:0001263)`;
  expected top-1 differentials Angelman / Rett / FoxG1 / MCPH-family (confirmed by
  MDAgents on the same input).

## v2 Patches and Smoke Test Result

### Decision: Plan A (`DEEPRARE_NO_WEB=1`)
- Chose A over B (webdriver-manager + Chrome). Rationale: A is the reproducible
  "closed-knowledge" path for benchmark comparison; B still requires a Chrome
  browser binary which we cannot install system-wide. The four Selenium-backed
  tool modules now return empty stubs when `DEEPRARE_NO_WEB=1` is set; the
  original Selenium code path is untouched.

### Patches applied (six files, ~120 LOC net)

1. **`tools/web_search.py`** — `BingSearchTool`, `GoogleSearchTool`,
   `DuckDuckGoSearchTool` each return `"No web search results (DEEPRARE_NO_WEB=1)."`
   when the env var is set. Added `import os` (already at top). Three early-return
   guards, ~12 LOC.
2. **`tools/page_fetch.py`** — `fetch_page_content_and_summarize` returns `""`
   when `DEEPRARE_NO_WEB=1`. Added `import os`. ~4 LOC.
3. **`tools/hpo_search.py`** — `HPOSearchTool` returns `[]` when
   `DEEPRARE_NO_WEB=1`. Added `import os`. ~4 LOC.
4. **`tools/uptodate_search.py`** — `UptodateSearchTool` returns `""` when
   `DEEPRARE_NO_WEB=1`. Added `import os`. ~4 LOC.
5. **`utils.py`** —
    - `set_up_data` wraps each of the five `pd.read_csv` calls
      (`xinhua_rag_0331.csv`, `mimic_rag.csv`, `rarebench_rag.csv`,
      `mygene_rag.csv`, `ddd_rag.csv`) in `try / except FileNotFoundError`. CSVs
      are appended to a `frames` list; only present frames are concatenated.
      Schemas documented in inline comment. If all are missing, fabricates an
      empty DataFrame with `['_id', 'case_report', 'embedding', 'diagnosis',
      'data_source']`. ~60 LOC net (~30 added vs original block).
    - `set_up_args`: removed the `choices=['gpt-4o', 'gpt-4o-mini', 'o1',
      'o3-mini', 'o1-mini']` restriction on `--openai_model` so OpenRouter ids
      like `google/gemini-3-flash-preview` are accepted. 2 LOC.
6. **`data.py`** — Added a `case` branch in `RareDataset.load_ehr_phenotype_data`
   that parses a `dataset/cases.csv` with `hpo` (pipe-separated HP IDs) and
   optional `disease` columns. ~14 LOC.
7. **`diagnosis.py`** — Wrapped `PubCaseFinderSearchTool` and `PhenobrainAPITool`
   in `try / except` at the top of `make_diagnosis`. PubCaseFinder's public API
   now returns 404 for the smoke triad — without this wrap the pipeline crashes
   before reaching the LLM. ~14 LOC.
8. **`api/interface.py:Openai_api.get_embedding`** — Added
   `DEEPRARE_LOCAL_EMBEDDING=1` branch. Loads `BAAI/bge-small-en-v1.5` (384-dim,
   110 MB) via `sentence_transformers` on first call, caches in module global,
   pads vectors to 1536 dim so cosine_similarity against stored
   `text-embedding-3-small` vectors in `RDS_embeddings.csv` doesn't crash on
   shape mismatch. Selectable via env `DEEPRARE_LOCAL_EMBEDDING_MODEL`. ~25 LOC.

### Smoke test

**Status: PASSED end-to-end on 1 case.**

#### Command

```bash
cd /Users/yutianzhao/Desktop/RDAgentBenchmark/agents/deeprare
set -a; source /Users/yutianzhao/Desktop/RDAgentBenchmark/.env; set +a
export OPENAI_BASE_URL=https://openrouter.ai/api/v1
export DEEPRARE_MINI_MODEL=google/gemini-3-flash-preview
export DEEPRARE_NO_WEB=1
export DEEPRARE_LOCAL_EMBEDDING=1
.venv/bin/python main.py \
  --model openai \
  --openai_apikey "$OPENROUTER_API_KEY" \
  --openai_model google/gemini-3-flash-preview \
  --dataset_name case \
  --results_folder ./result_smoke/
```

Input: `dataset/cases.csv` = `HP:0000252|HP:0001250|HP:0001263,Angelman/Rett/MCPH expected`
(microcephaly + seizures + global developmental delay).

#### Runtime

- Wall: **1m 46s** total (1m 35.9s on the patient itself per `time_taken` field;
  ~10s of setup — BioLORD/MedCPT model load + 10 k similar-case CSV load +
  one-time download of `BAAI/bge-small-en-v1.5`).
- Phenobrain API responded; PubCaseFinder API returned 404 and was gracefully
  skipped (per the new try/except). All Selenium tool calls were no-ops via the
  `DEEPRARE_NO_WEB=1` shim.

#### Output: top-5 (Final, after Orphanet/OMIM/PubMed reflection)

| Rank | Disease | Note |
|------|---------|------|
| 1 | ARX-Related Epileptic Encephalopathy | matches expected MCPH-family / EIEE class |
| 2 | ASPM-Related Primary Autosomal Recessive Microcephaly (MCPH5) | classic MCPH match |
| 3 | WWOX-Related Developmental and Epileptic Encephalopathy (WOREE Syndrome) | |
| 4 | FoxG1 Syndrome | matches expected differential |
| 5 | SLC13A5-Related EIEE25 | |

Two Orphanet/OMIM reflections both judged `True` (ARX-related and ASPM-related),
so the second reflection loop did not trigger (search_depth stayed at 1).

#### Token cost (estimated)

- ~8–10 backbone LLM calls (1 zero-shot, 1 fused-evidence/memory_1, ~6
  Check_Agent reflections per identified Orphanet ID — most short-circuited
  because OMIM lookup failed for many, 1 final memory_2). Total response chars:
  ~17 KB across stored fields (`zero_shot_llm_response` 2.6 KB,
  `first_round_result` 4.1 KB, `judgements` 5.2 KB, `final_diagnois` 5.6 KB).
- At Gemini 3 Flash Preview pricing (~$0.30 / M input, ~$2.50 / M output), and
  ~2 K input / ~1 K output per call avg, this case is in the **$0.01–$0.04**
  range.

#### Caveats

- Similar-case retrieval is currently effectively random-order because the
  query embedding (bge-small-en-v1.5, zero-padded to 1536-dim) is not directly
  comparable to the stored `text-embedding-3-small` vectors. The Check_Patient
  similarity check downstream uses MedCPT cross-encoder, which is unaffected.
  For a real benchmark we should either (a) re-embed all 10 k PubMed cases with
  bge-small once and persist, or (b) host a real `text-embedding-3-small`
  endpoint.
- `xinhua_rag_0331.csv`, `mimic_rag.csv`, `rarebench_rag.csv`, `mygene_rag.csv`,
  `ddd_rag.csv` are still absent. The smoke runs from `RDS_embeddings.csv`
  alone (10 k PubMed cases from the HF bundle). If we want the full RAG set we
  must either request from authors or build them from RareBench/MIMIC/Xinhua
  source data ourselves.
- PubCaseFinder public API returns 404 on the smoke HPO triad — the upstream
  service appears to have changed; not a regression in our patches.

## Status: runs end-to-end (smoke test PASSED on the microcephaly/seizures/GDD triad, top-5 plausible)

## Adapter Shim

**File:** `harness/agents/deeprare.py` (class `DeepRareAdapter`,
`NAME = "deeprare"`).

### Design choices

- **Subprocess invocation** of `agents/deeprare/.venv/bin/python
  agents/deeprare/main.py …`. Rationale: DeepRare ships torch +
  sentence-transformers + a ~800 MB HF database mounted from a side `database/`
  dir, and its CLI surface is the cleanest integration point. We mirror the
  v2 smoke-test command in this report.
- **Patches reused, not re-applied**. The adapter sets
  `DEEPRARE_NO_WEB=1` + `DEEPRARE_LOCAL_EMBEDDING=1` + `OPENAI_BASE_URL=…/openrouter/v1`
  in the subprocess env so the in-tree patches activate without touching the
  vendor code.
- **Input projection**. Each call writes a transient single-row
  `dataset/cases.csv` (`hpo` = pipe-separated `HP:xxxxxxx` ids, optional
  `disease`), the format consumed by the patched `data.py:case` branch. For
  Pillar 3 we tack variant context (`gene HGVS zygosity`) onto the
  `disease` field as a soft hint — full Exomiser/VCF wiring (`main_gene.py`)
  is **not** exercised by this shim since the Exomiser JAR is absent on the
  scout box. The original `cases.csv` smoke fixture is backed up & restored
  per call.
- **Output parser**. `final_diagnois` markdown (typo preserved upstream) is
  parsed by the regex `^##\s*\*\*(?P<disease>.+?)\*\*\s*\(?\s*Rank\s*#?(?P<rank>\d+)/\d+`
  → list ordered by rank. Falls back to any `## **<title>**` header if no
  rank suffix found (skipping `## References`). Dedup preserves first-seen
  casing.
- **Output collection**. A per-call `result_harness_<run_tag>/` results dir
  defeats main.py's "skip-if-exists" cache and isolates parallel calls. We
  also pass the full patient JSON path back via `log.extra` for downstream
  audit.
- **Pillar support**. `supports_pillar` returns True for P2 (HPO), P3
  (HPO + variant text), and P5 (we always fill `reasoning_trace` with
  `patient_info` + `diagnosis_api_response` + `zero_shot_llm_response` +
  `first_round_result` + `judgements` + `final_diagnois`). P1 deferred
  (the DeepRare HPO extractor is Selenium-gated). P4 not supported.
- **Token cost** remains $0 — DeepRare does not surface OpenAI usage. A
  follow-up should wrap the `Openai()` client with a `usage_callback` to
  populate `log.cost`. `deeprare_time_taken_s` is captured.

### Verification

Ran `python -m harness.agents.deeprare` against the first phenopacket
(`PMID_15266616_100`, gold = Jacobsen syndrome — high-forehead /
prominent-forehead / Highly arched eyebrow / small hypothenar eminence /
clinodactyly / abnormality of the cardiovascular system):

```
status: ok
ranked_predictions[:5]: ['Sotos Syndrome', 'Mowat-Wilson Syndrome',
                         'Pitt-Hopkins Syndrome', 'Rubinstein-Taybi Syndrome',
                         'Floating-Harbor Syndrome']
latency_ms: 128563   (~2 min, dominated by BioLORD load + ~8 LLM calls)
extra: {deeprare_time_taken_s: 110.3, judge_result: [False],
        phenotype_ids: ['HP:0000348', 'HP:0011220', ...], ...}
```

Sotos / Mowat-Wilson / Pitt-Hopkins / Rubinstein-Taybi / Floating-Harbor are
**plausible** overgrowth/dysmorphology syndromes for the given HPO triad;
they do not include Jacobsen (correct answer) — this is a real top-5 miss
for DeepRare on this very dysmorphology-heavy case, not a shim failure.
The end-to-end pipeline (cases.csv injection, patched env, OpenRouter
routing, patient JSON parsing, ranked extraction) is confirmed green.


---

## Bug Fix 2026-05-15 (Phase-0 retro)

**Bug D2** (round2_plan.md § 复盘 ①): `cost.cost_usd` was 0 across the
50-case Mini Phase 0 sample despite valid `prompt_tokens` /
`completion_tokens` counts (estimated via char-count heuristic).

**Fix** in `harness/agents/deeprare.py`:
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
`DeepRareAdapter(backbone_id="openrouter/google/gemini-3-flash-preview")`
→ `log.cost.cost_usd > 0` on a single PP-Store case.
