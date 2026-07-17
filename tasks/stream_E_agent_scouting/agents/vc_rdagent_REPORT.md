# VC-RDAgent Scouting Report

## Repo

- **URL:** https://github.com/cloudna-AI4LS/VC-RDAgent (found via GitHub Search API — *not* surfaced by Google/WebSearch initially, hence the "冷门" worry)
- **Stars:** 4 (new — pushed 2026-02-13, updated 2026-04-29). Org: **cloudna-AI4LS** (Cloudna AI for Life Sciences, the author group).
- **License:** **None declared** (no LICENSE file in repo). **This is a flag for the paper** — see Risk.
- **Language:** Python 3.12.
- **Demo (hosted):** https://rarellm.app.bio-it.tech/rdagent/ (chat UI).
- **Paper:** "VC-RDAgent: An efficient rare disease diagnosis agent via virtual case construction informed by hybrid statistical-metric and hyperbolic-semantic prioritization," bioRxiv 2026.02.09.702153. https://www.biorxiv.org/content/10.64898/2026.02.09.702153v1
- **Cloned to:** `/Users/yutianzhao/Desktop/RDAgentBenchmark/agents/vc_rdagent/`

## Install Complexity

**Low.** Repo is unexpectedly well-engineered:

- `environment.yml` (conda) + `requirements.txt` (uv pip), Python **3.12**, deps: `torch`, `transformers`, `sentence-transformers`, `geoopt` (hyperbolic optim), `openai`, `numpy`, `pandas`, `scipy`, `networkx`, `accelerate`, `safetensors`, `beautifulsoup4`. That's it — 13 packages.
- README install: `uv venv --python 3.12 .venv && uv pip install -r requirements.txt`.
- Optional Docker setup for the chat front-end at `rare-disease-chat/` (FastAPI + LangGraph + MCP server).
- No platform-specific code; should run on macOS / Linux / CUDA.

**Caveats:**
- Sentence-transformer model `FremyCompany/BioLORD-2023` is pulled on first run (~440 MB) — downloads via `transformers` cache.
- If using the local LLM evaluator path (Qwen3-8B), `accelerate` + GPU recommended (~16 GB VRAM); the OpenRouter path (free `qwen/qwen3-8b:free`) is the offline-friendly default in `inference_config.json`.

## Model Checkpoints / External Data

**All key artifacts ship in-tree.** Total repo ~600 MB after clone (depth=1). Notable shipped data:

| Path | Size | What it is |
|---|---|---|
| `hpo_embedding/phe2embedding_recomputed.json` | 50 MB | **Poincaré hyperbolic phenotype embeddings** (ID → vector). Pre-trained. |
| `hpo_embedding/ic_dict_recomputed.json` | 785 KB | Information-content weights per HPO term. |
| `hpo_embedding/poincare_model/trainpoincare.py` | — | Training script (geoopt) — for re-training if HPO updates. |
| `hpo_annotations/hp.obo` | 10 MB | HPO ontology snapshot. |
| `hpo_annotations/phenotype.hpoa` | 33 MB | Disease–phenotype annotations w/ frequency & evidence. |
| `hpo_annotations/genes_to_phenotype.txt`, `phenotype_to_genes.txt`, `genes_to_disease.txt` | ~84 MB | Gene mappings. |
| `hpo_annotations/disease_descriptions_batch.json` | 7.5 MB | Disease descriptions (likely scraped — fine for inference). |
| `mondo_annotations/mondo_parsed_full.json` | ~46 MB | Parsed MONDO. |
| `orphanet_annotations/` | 179 MB | Orphanet Product 1/3/4 XML+JSON. |
| `disease_phenotype_kg/` (8 CSVs) | 72 MB | Pre-built disease–phenotype–gene KG (auto-regen by `--save_case_library_only`). |
| `general_cases/phenotype_disease_case_library.jsonl` | 4.3 MB | **Virtual standardized case library** (one `{Phenotype: [...], RareDisease: [...]}` per line). |
| `general_cases/phenotype_disease_case_database.json` | 23 MB | Disease-aggregated cases w/ frequencies. |
| Test data `data/PUMCH-ADM.json`, `HMS.json`, `LIRICAL.json`, `mygene2.json` | ~450 KB | **RareBench-format** eval sets. |

So the "**离线双曲-语义 HPO embedding**" component is genuinely real and on-disk — `geoopt` Poincaré model + JSON dump. No proprietary checkpoint, no Google Drive link, no email-the-author dance.

**Knowledge base size (from paper):** 16,629 disease entities (12,208 rare) and 252,464 disease–phenotype associations.

## "No paid API" claim — partly true

Re-checking against the actual code: VC-RDAgent decomposes into **two stages**:

1. **VC-Ranker (offline, no API):** ensemble disease ranking via IC-weighted overlap + frequency-aware likelihood ratio + Poincaré hyperbolic similarity. Implemented in `pho2disease/ensemble_disease_ranking.py`. **Zero LLM calls.** Pure numpy/scipy/geoopt math over the local embeddings + KG.
2. **LLM evaluator step (`phenotype_to_disease_prediction_bysteps.py`):** takes Step-1 ranking, builds a 2-step/3-step CoT prompt, then runs **either** local Qwen3-8B **or** OpenRouter API (default config uses `qwen/qwen3-8b:free` on OpenRouter — free tier).

So the "无需付费 API" framing in `agent_methods.md` is correct **for the local-Qwen path**, and for the OpenRouter path it's correct only because the default model (`qwen/qwen3-8b:free`) costs nothing. Some OpenRouter call still happens by default; flip `default_model_name` to `"Qwen/Qwen3-8B"` to be fully offline.

## I/O Schema

Input format is **identical to RareBench**:
```json
[
  [["HP:0000722", "HP:0001319", ...], ["CCRD:93", "OMIM:176270", "ORPHA:739"]],
  ...
]
```
Files in `data/` are drop-in compatible with our Phenopacket-Store + RareBench layer. JSONL variant also provided.

Output: ranked disease list per sample with score, rank, top‑K hits; saved to `pho2disease/result/phenotype_to_disease_results_<timestamp>.json` with similarity-threshold-based accuracy metrics (default threshold 0.80).

## Inference Pipeline

Two entry points (per README "Quick start"):

```
Step 1 — pho2disease/ensemble_disease_ranking.py --config prompt_config.json --prompt_steps 2
   → fuses three rankings via Z-statistics:
     (a) IC-weighted phenotype-overlap similarity
     (b) annotation-frequency-weighted likelihood ratio
     (c) Poincaré hyperbolic embedding cosine-similar-case retrieval
   → produces top-K candidates + 2-step/3-step CoT prompts (saved to ./prompt/xxx.json)

Step 2 — pho2disease/phenotype_to_disease_prediction_bysteps.py
   → runs LLM (Qwen3-8B local OR OpenRouter qwen3-8b:free) on the step-1 prompts
   → outputs final disease prediction + accuracy / top-K
```

Plus a `rare-disease-chat/` subproject (Docker, FastAPI, LangGraph multi-agent + MCP server) that wraps everything as a chat UI — not needed for benchmark.

## Risk

**Risk level: LOW–MEDIUM.**

**Why low:**
- Public repo, all key artifacts (Poincaré embeddings, IC, KG, case library, test data) ship in-tree.
- Modern Python 3.12 stack, only 13 pip deps. Should install cleanly.
- Input format is RareBench-compatible — zero adapter work.
- The "offline" claim is genuine: the **ranking stage is API-free**; only the optional LLM-evaluator step touches OpenRouter (and the default model there is free-tier).
- Code is fresh (Feb 2026 push, still maintained Apr 2026).

**Why not "low":**
- **No LICENSE file.** This is a real problem for an EMNLP submission — without an explicit license, the legal default is "all rights reserved." We should email the authors before relying on it (or at least cite the bioRxiv preprint + GitHub URL and treat it as a research artifact under fair-use, which is the standard practice but worth flagging).
- Only **4 stars** and pushed by a single GitHub user/org we don't recognize (`cloudna-AI4LS`). Bus-factor risk.
- Hidden assumption: the `prompt_config.json` defaults reference a Nebula KG service at `http://192.168.0.9:5008/nebulasearch/` — clearly an internal IP. Set `use_kg: false` (already the default) to disable.
- Several scripts are gigantic single files (`generate_prompts_bysteps.py` = 457 KB, `phenotype_to_disease_prediction_bysteps.py` = 300 KB). Likely contain hard-coded paths/prompts; adapter wrapping will need care but not blocking.

**Recommend keeping in lineup?** **YES — keep.** This was flagged as the highest-risk slot in `agent_methods.md` ("可能装不起来或代码不开源"), but the repo turned out to be the most complete of the four rare-disease agents we will integrate. It is the right "隐私保护对照 / 离线本地推理" pillar member — it actually delivers on that claim (the ranking step is genuinely offline).

**Fallback if it surprises us during integration:** swap to **LA-MARRVEL** (clean Apache-2.0, well-maintained) — but only if we're also adding the gene-prior axis. Otherwise no swap needed.

## Next Steps for Benchmark Integration

1. **Email cloudna-AI4LS to clarify license** (today). Pasting bioRxiv contact email is enough; we need a one-line "this is released under [Apache-2.0|MIT|CC-BY] for academic use" to be safe in the paper.
2. **Smoke test `ensemble_disease_ranking.py`** on the shipped `data/PUMCH-ADM.json` (no LLM needed, no API key). Confirms Poincaré embeddings load and Z-statistic ranking runs in <10 min on CPU. This validates the "VC-Ranker" component end-to-end.
3. **Decide LLM evaluator backbone.** For consistency with the rest of the lineup, replace the default `qwen/qwen3-8b:free` OpenRouter call with our standard backbones (DeepSeek V3.2 cheap / GPT-5 high-end). The `phenotype_to_disease_prediction_bysteps.py` script's OpenAI-compatible OpenRouter client is trivially repointed at any OpenAI-compatible endpoint. Document the swap in method section.
4. **Wrap as benchmark adapter:** take a JSONL `{phenotypes, gold_diseases}` → call Step-1 ranking → call Step-2 LLM (with our chosen backbone) → emit ranked OMIM/ORPHA list. The shipped `data/*.json` files give us a known-good reference output.
5. **Note in paper:** VC-RDAgent's offline component is novel (hyperbolic + IC + frequency fusion) and well worth highlighting in related work; cite the bioRxiv preprint explicitly and note "VC-RDAgent's evaluation step replaced with our standard backbones for fair cross-system comparison."
6. **Cost:** essentially $0 if using free OpenRouter Qwen; ~standard agent cost if swapped to DeepSeek/GPT-5.

---

**Bottom line:** This repo is the *opposite* of what `agent_methods.md` warned about — it is the most install-friendly of the four rare-disease agents, with all data shipped and a clean modern Python stack. The only real worry is the missing LICENSE file.
