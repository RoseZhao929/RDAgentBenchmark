# VC-RDAgent Run Report (v1 Smoke Test)

**Date:** 2026-05-11
**Repo path:** `/Users/yutianzhao/Desktop/RDAgentBenchmark/agents/vc_rdagent/`
**Status:** **SMOKE TEST PASSED (Plan A — offline, no LLM)**

---

## Environment

- **Host:** macOS 25.2.0, Apple Silicon
- **Python:** 3.13.7 (system python3) in venv at `agents/vc_rdagent/.venv/`
  - Note: README recommends 3.12, but 3.13.7 worked without issues. All deps installed cleanly.
- **Install command run:**
  ```bash
  cd agents/vc_rdagent/
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -U pip
  pip install -r requirements.txt
  ```
- **Install duration:** ~5 min (one-time, includes torch 2.11.0, transformers 5.8.0, sentence-transformers, geoopt, etc.)
- **Final installed packages:** 13 top-level + ~50 transitive, no compile errors.

## Configuration Changes

Edited `pho2disease/prompt_config.json`:
- `base_path`: `"path/to/VCAP-RDAgent"` -> `"/Users/yutianzhao/Desktop/RDAgentBenchmark/agents/vc_rdagent"`

No other config changes required. `use_kg: false` was already the default (avoids the internal Nebula KG IP).

## Smoke Test — Plan A (Stage 1, Offline, No LLM)

**Command (from `agents/vc_rdagent/`):**
```bash
source .venv/bin/activate
cd pho2disease
python ensemble_disease_ranking.py \
    --config prompt_config.json \
    --prompt_steps 2 \
    --no_prompt \
    --num_samples 2 \
    --output_file /tmp/vc_smoke_ranking.json
```

**Input:** Default from config = `data/PUMCH-ADM.json` (RareBench-format `[[HPO IDs], [disease IDs]]`).

**Behavior:**
- Loaded HPO ontology (`hp.obo`, 10 MB), HPOA annotations (33 MB), Orphanet JSON (179 MB), MONDO parsed (46 MB), Poincaré phenotype embeddings (50 MB), IC dict (785 KB), case library (4.3 MB) — **all from local disk, no downloads**.
- Ran the **three** ranking strategies and Z-statistic fusion:
  - IC-weighted phenotype-overlap similarity
  - Annotation-frequency-weighted likelihood ratio
  - Poincaré hyperbolic embedding similar-case retrieval
- **Zero LLM API calls**, **zero network egress** during inference itself (HuggingFace cache check did pass through, but no model download needed for Stage 1 — the `FremyCompany/BioLORD-2023` SentenceTransformer is only used in Stage 2).
- Total wall time for 2 samples: ~3 min (most of that is one-time ontology load).

**Output (`/tmp/vc_smoke_ranking.json`):**
- 113 KB JSON.
- Top-level keys: `metadata`, `disease_matching_summary`, `samples` (len=2).
- Per-sample top-50 candidates with Z-scores.

**Result quality (validation against shipped gold labels):**
- Total samples: 2
- Hit rate (any rank): 100% (2/2)
- Top-1: 50% (1/2)
- Top-3: 100% (2/2)
- Top-5: 100% (2/2)
- Average rank of gold disease: 3.5

This matches the order-of-magnitude expected from the paper for the ranker-only stage.

## Answer to the Key Question

> **"VC-RDAgent is whether the 'no-LLM-can-still-run' claim is real?"**

**YES — fully confirmed.** The `--no_prompt` flag bypasses prompt generation entirely; `ensemble_disease_ranking.py` runs the three-strategy fusion (IC-overlap + frequency-LR + Poincaré-embedding) purely on `numpy`/`scipy`/`geoopt` over the shipped local artifacts (`phe2embedding_recomputed.json`, `ic_dict_recomputed.json`, `phenotype.hpoa`, etc.). Output is a complete ranked disease list with Z-statistic scores and hit-rate metrics — no OpenRouter call ever made.

This makes the agent's **VC-Ranker** sub-component a genuine "fully offline / privacy-preserving" baseline, fit for the same slot as Exomiser/LIRICAL/PhenoBrain in the benchmark lineup.

## Stage 2 (LLM evaluator) — Not Run This Round

Stage 2 (`phenotype_to_disease_prediction_bysteps.py`) was **not exercised** in this smoke test because Plan A already validated the harder claim. For Stage 2 with OpenRouter:

1. Edit `pho2disease/inference_config.json`:
   - `base_paths.base_path` -> `/Users/yutianzhao/Desktop/RDAgentBenchmark/agents/vc_rdagent`
   - `openrouter_config.api_key` -> use env var `$OPENROUTER_API_KEY` (do NOT hard-code; the script reads from config but you can also pass `--openrouter_api_key`)
   - `openrouter_config.model_name` -> `"google/gemini-3-flash-preview"` (project canary backbone)
2. First regenerate prompts via `ensemble_disease_ranking.py` *without* `--no_prompt` (defaults to `./prompt/<timestamp>.json`).
3. Run:
   ```bash
   python phenotype_to_disease_prediction_bysteps.py \
       --prompts_file ./prompt/<timestamp>.json \
       --model_name openrouter \
       --api_model google/gemini-3-flash-preview \
       --num_samples 2
   ```

Estimated cost for full PUMCH-ADM (~75 samples, 2-step CoT): well under $0.20 with Gemini 3 Flash Preview.

## Risk Assessment after Smoke Test

**Risk: LOW.** All the scouting-report claims held up:
- Repo is install-friendly (13 deps, 5 min on a clean macOS venv).
- All artifacts on-disk; no Google Drive / Zenodo dance.
- Input format is RareBench-compatible (drop-in for our Phenopacket-Store outputs).
- Offline-only path produces meaningful, evaluatable rankings.

**Open issues (not blockers):**
- No LICENSE file in repo — same as scouting report flagged. Need author email before paper submission.
- Default `prompt_config.json` references internal IP `192.168.0.9:5008` for KG; `use_kg: false` is the default so we are unaffected.
- The `FremyCompany/BioLORD-2023` SentenceTransformer (~440 MB) is *not* needed for Stage 1 but will be downloaded on first Stage 2 run. Set `sentence_transformer_cache_dir` to a controlled location for reproducibility.

## Files Produced

- `/tmp/vc_smoke_ranking.json` — 113 KB, 2-sample ranking output (kept for reference).
- `agents/vc_rdagent/.venv/` — Python 3.13 venv, ~3 GB on disk.
- `agents/vc_rdagent/pho2disease/prompt_config.json` — `base_path` patched.

## Next Steps

1. Wrap `ensemble_disease_ranking.py` as a benchmark adapter that takes our standard `{phenotypes, gold_diseases}` JSONL and emits a ranked-disease JSONL.
2. Run Stage 2 with `google/gemini-3-flash-preview` over all 4 shipped eval sets (PUMCH-ADM, HMS, LIRICAL, mygene2) to get a full reference scoreline.
3. Plug into the Stream E adapter harness alongside DeepRare / RDMA / MAIDxO.

## Adapter Shim

**File:** `harness/agents/vc_rdagent.py` → `VCRDAgentAdapter(AgentAdapter)`, `NAME = "vc_rdagent"`.

**Design:**
- Defaults to **Stage 1 (offline ensemble ranker)**. `backbone_id` is a no-op marker (default `"offline/none"`); the adapter never makes an LLM call in Stage 1, so `cost.cost_usd = 0.0` by construction and latency is the only operational metric.
- Stage 2 hook (`agent_extra={"use_llm_refine": True}`) is **stubbed** — returns `status="skipped"` with an explanatory error message. Stage 2 wiring deferred per the RUN_REPORT plan.
- Pillar support: **P2_phenotype_ddx only** (`supports_pillar` returns True only for P2).
- Projects `CanonicalCase.gold_hpo_terms` → VC-RDAgent's native `[[hpo_ids], [disease_ids]]` per-sample JSON. Uses sentinel disease ID `OMIM:000000` (not in any annotation) to keep VC-RDAgent's main-loop alive without leaking gold to the ranker.
- Subprocess invocation: `agents/vc_rdagent/.venv/bin/python pho2disease/ensemble_disease_ranking.py --config prompt_config.json --input_file <tmp> --prompt_steps 2 --no_prompt --num_samples 1 --final_top_k <K> --output_file <tmp_out>`, run with `cwd=pho2disease/` (script uses relative imports).
- Output parsing: reads `samples[0].final_rankings[].disease_id`; `disease_id` may be `str` or `List[str]` (RareBench parallel-ID format) — `_flatten_disease_id` normalizes, `_pick_primary_id` picks OMIM > ORPHA > else.
- Confidence: `-z_statistic` (VC-RDAgent's z is smaller-is-better; we flip).
- Status mapping: `ok` / `timeout` / `agent_error` / `parser_error` / `skipped`.

**Verification:**
```python
case = next(ingest_rarebench("data/rarebench_hf/data_unzipped/data/LIRICAL.jsonl", "LIRICAL", limit=1))
adapter = VCRDAgentAdapter()
log = adapter.predict(case, pillar="P2_phenotype_ddx", eval_mode="gold_hpo")
# status=ok, latency_ms=77320, cost=0
# Gold = OMIM:191900 / ORPHA:575
# top5 preds: ['OMIM:191900', 'OMIM:607115', 'OMIM:260920', 'OMIM:620376', 'OMIM:109650']  (top-1 hit)
```

The ~77 s latency is dominated by one-time ontology load inside the subprocess (`hp.obo` 10 MB + HPOA 33 MB + Orphanet JSON 179 MB + MONDO 46 MB + Poincaré 50 MB). For batch runs, hosting the ranker as a long-lived daemon would amortize this; the per-sample compute is sub-second once loaded.

---

## Bug Fix 2026-05-15 (Phase-0 retro)

**Bug D3** (round2_plan.md § 复盘 ①): RareArena RDS cases ship only
free-text vignettes. VC-RDAgent Stage 1 requires structured `HP:*` IDs as
input, so the adapter raised `ValueError(... no usable gold_hpo_terms ...)`
for 25/50 cases in the Mini Phase 0 sample.

**Fix** in `harness/agents/vc_rdagent.py`:
- New `_extract_hpo_for_end_to_end(case)` helper. When `eval_mode="end_to_end"`
  AND the case has no gold HPO BUT does have a free-text vignette, build
  an `LLMControlAdapter` (Gemini Flash by default) and run
  `extract_phenotypes()`, then `phrase_to_hp_id` (from
  `harness.metrics.hpo_phrase_to_id`, rapidfuzz threshold 90) to normalise
  each phrase.
- The resolved HPO IDs are projected onto a shallow `case.model_copy()`
  before Stage 1 invocation. `gold_hpo` mode is unchanged.
- `log.extracted_hpo_terms` + `log.extra.hpo_extraction_*` carry
  audit info.

**Bug D2 (cost)**: Stage 1 is offline / no LLM call — `cost_usd=0` is
correct.

Verified by re-run on the same 50-case sample — `vc_rdagent` went from
25/50 ok → 50/50 ok (target). See `data/round2/phase0/REPORT_v2.md`.
