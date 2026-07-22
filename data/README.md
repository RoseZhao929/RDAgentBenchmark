# `data/` — experiment data for RareAgentBench

This directory is **not** the full 19 GB working tree. It is a curated subset
containing exactly what is needed to **recompute the paper's §4–§7 numbers**
(the manifest referenced in the reproducibility appendix). Raw licensed corpora
and model weights are intentionally excluded.

## What is included (tracked in git)

| Path | Purpose |
|------|---------|
| `round2/phase4a/predictions_*.jsonl` | Per-cell agent×backbone predictions (main matrix, §6). **MIMIC cells excluded** — see below. |
| `round2/phase4a_summary.json`, `phase4a_with_ci.json`, `phase4a_canonical_2000.json`, `phase4a_receipts.csv` | Aggregated Table 1 / cost / CI source. |
| `round2/phase1/` | P1 extraction, P5 faithfulness (silver-gold, judge scores, reasoning traces). |
| `round2/phase3/` | P3 genotype-aware DDx, H2 full-N paired. |
| `pmc_oa_holdout/`, `pmc_precutoff/` | Temporal holdout (§5): candidate pools, gold, raw PMC XML for overlap detection. |
| `hpo/hp.obo`, `orphadata/en_product*.xml` | Evaluator ontologies (ORPHA/HPO normalization). |
| `rarearena/benchmark_data/RDS_benchmark.jsonl`, `rarebench_hf/data_unzipped/data/{RAMEDIS,LIRICAL,MME,HMS}.jsonl` | Gold sources needed to score R@1. |
| `phenopacket_store/notebooks/` | Phenopacket-Store gold cases. |

## What is **excluded** (do not commit)

- **MIMIC-IV and all MIMIC-derived files** (`mimic-iv-3.1/`, `mimic_iv_rd_slice/`,
  `round2/phase4a/predictions_mimic_diverse_*.jsonl`). Under the PhysioNet
  Credentialed Health Data License — obtain from a credentialed collaborator, do
  not redistribute.
- **Model weights / checkpoints** (`phenobrain_checkpoints/`, `*.safetensors`, etc.).
- Third-party dataset repos are included as **plain files** (their nested `.git`
  was removed); re-download originals from their upstreams if you need the full sets.

Everything under `data/` is gitignored by default; tracked files were added with
`git add -f`. To add more, force-add explicitly and keep MIMIC-derived data out.
