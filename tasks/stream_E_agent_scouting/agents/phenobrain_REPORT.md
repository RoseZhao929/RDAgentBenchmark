# PhenoBrain Scouting Report

## Repo

- **URL:** https://github.com/xiaohaomao/timgroup_disease_diagnosis
- **Stars / activity:** small repo, **last commit 2024-11-28** ("add training dataset of PBTagger"). Authors: Tsinghua TimGroup (xiaohaomao).
- **License:** Apache-2.0 (LICENSE file in repo).
- **Language:** Python 3.6.12 + TensorFlow 1.14 (legacy stack).
- **Hosted public service:** http://www.phenobrain.cs.tsinghua.edu.cn/pc with REST API documented in `PhenoBrain_Web_API/README.md`.
- **Paper:** Mao et al., "A phenotype-based AI pipeline outperforms human experts in differentially diagnosing rare diseases using EHRs," *npj Digital Medicine* 8:67 (2025). https://www.nature.com/articles/s41746-025-01452-1
- **Public test set:** `Public_Test_set.json` ships in repo (HPO list -> OMIM/ORPHA id pairs); larger datasets on Zenodo https://zenodo.org/records/10774650
- **Cloned to:** `/Users/yutianzhao/Desktop/RDAgentBenchmark/agents/phenobrain/`

## Install Complexity

**Medium-high.** Two pain points:

1. **Legacy stack pinned to Python 3.6.12 + TF 1.14 + transformers 4.18 + scikit-learn 0.21.3.** README explicitly says "Python version 3.6.12 needs to be installed to avoid potential conflicts." Will not run on modern CUDA / Apple silicon without massaging. Docker image provided (`Docker/Dockerfile`, base `continuumio/anaconda3:2024.02-1`, conda env `phenobrain`) but uses Tsinghua mirrors for conda channels — needs swap if outside China.
2. **Java OpenJDK 1.8 required** (only for the BOQA baseline; can be skipped if BOQA not used).

Conda env file: `codes/requirements.txt` (63 pinned packages, TF 1.14, transformers 4.18, scikit-learn 0.21.3, etc.).

For benchmark purposes the Docker route is the cleanest path. Build is ~10–15 min on first run.

## Model Checkpoints / External Data (critical — none ship in repo)

This is the biggest risk. Per README Module 2:

- **All trained model parameters are external (Google Drive), ~14 GB total.** Link: https://drive.google.com/drive/folders/1cVApHHw5yLLoLRYZht9Qx52AienJlgWN
- The **5 ensemble models** are: `ICTODQAcrossModel`, `HPOICCalculator`, `HPOProbMNBNModel`, `LRNeuronModel`, `CNBModel` (~4 GB subset). Bullet 4 of the README states you can grab just these if you don't care about the 12 baselines.
- **ALBERT base checkpoints for phenotype extraction** are also external — must be placed manually at:
  - `bert_syn_project/model/bert` (Google BERT)
  - `bert_syn_project/model/albert_google` (Google ALBERT)
  - `bert_syn_project/model/albert_brightmart` (Chinese ALBERT by brightmart)
- HPO/CHPO ontology files are referenced via `core/core/reader/hpo_reader.py` — must be supplied separately; CHPO source file path is hard-coded.

**Risk note:** Google Drive shared folders disappear without notice. We should mirror the 4 GB subset to local storage at the start of the project.

## I/O Schema

Two clean entry points:

### A. REST API (Tsinghua-hosted, no install needed)
- `GET /predict?model=Ensemble&hpoList[]=HP:0001913&hpoList[]=HP:0008513&topk=20`
  - `model` ∈ {Ensemble, ICTO (A), ICTO (U), PPO, CNB, MLP (M), MinIC, Res, BOQA, GDDP, RBP, Lin, JC, SimUI, TO, Cosine, RDD}
  - returns `TASK_ID`; results polled via `/query-predict-result?TASK_ID=...` → ranked disease list with `DIS_CODE` (OMIM:/ORPHA:/CCRD:), score, rank.
- `GET /extract-hpo?text=...` → async task → list of HPO IDs (with `HPO/CHPO`, `CHPO-UMLS`, or `CText2Hpo` extractor choice).

Plus auxiliary endpoints for HPO tree browsing and disease/phenotype detail lookups.

### B. Local Python entry point
- `codes/core/core/script/test/test_optimal_model.py` — main reproduction script.
- Input data path: `codes/core/data/preprocess/patient/` (patient HPO-list JSONs).
- Datasets toggled via list in `get_data_names()` (LIRICAL, RAMEDIS validation subset, Multi-country-test, PUMCH-MDT, Case_101_less_3_phenotype, etc.).
- Output: 7 result folders (`CaseResult`, `csv`, `delete`, `DisCategoryResult`, `Metric-test`, `RawResults`, `table`).

**Shape match to RareBench / Phenopacket-Store:** input is `[[HPO IDs], [OMIM/ORPHA IDs]]` (see `Public_Test_set.json`), **identical to RareBench**. Drop-in compatible.

## Inference Pipeline

Two modules:

1. **Phenotype Extraction (Pillar 1 — only used if input is free text):**
   - TopWords keyword mining → ALBERT/BERT-based **HPO-linker** (twin/DDML structure, trained via `bert_syn/script/run_bert_ddml_sim.py`).
   - Three matching algorithms surfaced: `HPO/CHPO`, `CHPO-UMLS`, `CText2Hpo` (a.k.a. PBTagger).

2. **Differential Diagnosis Ensemble (Pillar 2 — main contribution):**
   - 5 ensemble component models (paths under `codes/core/core/predict/`):
     - `sim_model/ICTODQAcrossModel` — IC-weighted term-overlap (best single similarity model)
     - `prob_model/HPOProbMNBNModel` — HPO-prior Multinomial-NB (PPO)
     - `prob_model/CNBModel` — Complement Naïve Bayes (CNB)
     - `ml_model/LRNeuronModel` — Logistic-Regression neuron (MLP-M)
     - `predict/calculator/HPOICCalculator` — IC weights used by ICTO
   - **Ensemble fusion:** order-statistics-based Z-statistic combination (recursive formula; see README Module 3). Implementation in `codes/core/core/predict/ensemble/ordered_multi_model.py`.
   - Total disease vocabulary: **9,260 diseases** (OMIM + ORPHA + CCRD).

Plus 12 baselines (MICA, Lin, JC, SimGIC, BOQA, GDDP, RBP, RDD, etc.) — already implemented for comparison.

## Risk

**Risk level: MEDIUM.**

Reasons:
- **Pros:** code is complete, public, Apache-2.0; both a hosted REST API and a Docker recipe exist; output format matches our benchmark; the 5-model ensemble is well-defined; ALBERT + Chinese coverage is unique among baselines (good for PUMCH-ADM Chinese layer).
- **Cons:**
  - **Legacy Python 3.6 + TF 1.14 stack** — fragile on Apple silicon / new CUDA. Docker is essentially mandatory.
  - **~14 GB external Google Drive checkpoints** — single point of failure; mirror immediately.
  - **Last commit Nov 2024**, no responses to issues since. If a model file silently disappears, we are stuck.
  - **Java dependency** for one baseline (BOQA); skippable.
  - The hosted REST API is a viable shortcut (no install needed) but introduces network dependency, rate-limit risk, and we cannot evaluate on cutoff-after data privately.

**Recommend keeping in lineup?** **Yes — keep as the designated non-LLM/classic-NLP baseline.** Its role in `agent_methods.md` is "经典 NLP baseline 对照" (equivalent slot to SHEPHERD / Exomiser / LIRICAL), and it is one of the few systems with explicit Chinese clinical-text capability — useful for PUMCH-ADM. Drop only if Docker build + checkpoint mirroring fails after 2 days.

**Fallback if PhenoBrain doesn't install:** swap to LIRICAL (Java, very robust, already integrated as a RareBench baseline) or Phenomizer.

## Next Steps for Benchmark Integration

1. **Mirror checkpoints today.** Download the 4 GB "5-model" subset from Google Drive + the three ALBERT/BERT base models → push to lab S3 / internal store. Document SHA-256.
2. **Build Docker image** locally (`docker build -t phenobrain:1.0 Docker/`); swap Tsinghua conda mirrors to default channels if outside China; verify `test_optimal_model.py` runs on the shipped `Public_Test_set.json`.
3. **Wrap as a CLI adapter** matching our benchmark's harness: take JSONL `{phenotypes:[HP:...], diseases:[OMIM:.../ORPHA:...]}` (RareBench format — already identical) → emit ranked disease list per case. Use `ICTODQAcrossModel` + ensemble by default; expose ensemble vs. ICTO-only as a flag for ablation.
4. **Decide LLM-extraction split.** PhenoBrain has its own ALBERT HPO extractor. For our Pillar 1 evaluation, we should run it side-by-side with LLM extractors (this is one of its main selling points). For Pillar 2/3 (gold HPO already supplied), bypass extraction entirely.
5. **Note in paper:** PhenoBrain is **not** an LLM agent — it is a non-LLM ensemble baseline, occupying the same slot as Exomiser/LIRICAL/SHEPHERD. Frame it explicitly as such in method section.
6. **Cost:** essentially zero ($0 API), but ~14 GB disk + 1 GPU recommended.
