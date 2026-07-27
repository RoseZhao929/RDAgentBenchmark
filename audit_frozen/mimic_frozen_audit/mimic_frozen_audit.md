# MIMIC-IV Rare-Disease Slice — Frozen Audit

- **Frozen commit:** `9babd833618936b6b29942baba130638e212921d`
- **Audit timestamp (UTC):** 2026-07-23 09:34:30
- **Checkout:** `/home/research/RDAgentBenchmark` (full 785M slim recompute set)
- **Scope:** READ-ONLY re-aggregation of the MIMIC-IV `mimic_diverse` slice. No LLM/model was called; no existing results, manifests, or paper text were modified.

## FINAL STATUS: `NOT_REPRODUCIBLE`

MIMIC is, at best, `DATASET_ONLY` **in intent** but `NOT_REPRODUCIBLE` **in evidence**: neither the cohort that defines n=956 nor a single prediction receipt nor any gold label survives in the frozen tree. Every MIMIC number in the paper traces only to legacy pre-computed aggregate tables that (a) cannot be reconciled to raw artifacts because none exist, and (b) disagree with each other.

## What was searched

Whole-repo grep/glob/find for `mimic`, `MIMIC`, `956`, `mimic_diverse`; the phase4a predictions directory; both aggregate summaries; the frozen manifest; git history (`git log --all`, deletion filter); on-disk data dirs vs `.gitignore`; and all paper sources under `paper_build/acl/tex/` and `paper_sections/`.

## What exists vs what is absent (frozen facts)

ABSENT on disk (all MIMIC evidence):
- `data/mimic-iv-3.1/` — raw PhysioNet source. Absent. `data/` is git-ignored (`.gitignore` lines 2, 31) and MIMIC weights/data were never committed ("init benchmark repo ... ignore huge data folder", "Wipe large model weights from git history").
- `data/mimic_iv_rd_slice/cases.jsonl` and `cases_filtered_diverse.jsonl` — the raw and canonical (956/239-disease) slices. **Absent.** These are the only artifacts that could confirm n=956. Neither is on disk anywhere on the machine (checked `find /`).
- `data/round2/phase4a/predictions_mimic_diverse_*.jsonl` — **zero MIMIC prediction receipts.** All 5 other datasets have receipts (83 files); MIMIC has none.
- MIMIC gold labels — stripped. `recompute_engine.py::load_gold()` hardcodes `mimic_diverse = {n_gold_cases: 0, ... note: "gold stripped from slim recompute commit; not recomputable"}`.

PRESENT but non-evidentiary:
- Cohort scripts `harness/ingest/mimic_iv.py`, `harness/ingest/mimic_iv_filter.py`, pilot `scripts/mimic_rd_detection_pilot.py` — logic only; unrunnable without the absent raw data.
- Legacy aggregate tables `data/round2/phase4a_receipts.csv`, `data/round2/phase4a_summary.json`, `data/round2/phase4a_REPORT.md`, `leaderboard/phase4a_summary.json`, and (other checkout) `new_version_paper/headline_results.csv` — each carries 22 `mimic_diverse` rows. These are **pre-computed numbers, not evidence**, and they are mutually inconsistent (see below).
- `audit_frozen/frozen_main_manifest.csv` — **confirmed 0 MIMIC rows** (datasets: phenopacket_store, rarearena_rds, rarebench, pmc_oa_holdout, pmc_precutoff). MIMIC was excluded from the frozen recomputed matrix.

Unrelated (do not conflate): `agents/rdma/results/mimic3_rd_mining/` is **MIMIC-III** text-mining for RDMA's P1 phenotype-extraction pillar — a different dataset and pillar from the n=956 MIMIC-IV DDx slice.

## The two surviving aggregates DISAGREE (cannot both be frozen truth)

Same cell `mimic_diverse | llm_control | DS V4-Pro`:
- `data/round2/phase4a_receipts.csv`: n_ok=**956**, R@1_variants=**0.248**
- `leaderboard/phase4a_summary.json`: ok=**395**, err=7 (n≈402), h1v=106 → R@1≈0.264
- `new_version_paper/headline_results.csv`: attempted=**402**, ok=395, R@1_variant=**0.2637**

Multiple cells differ (agentclinic/DS-Flash 951 vs 956; llm_control/DS-Pro 956 vs 402; mdagents/DS-Pro 956 vs 225; medagents/DS-Pro 956 vs 220). The `data/round2/phase4a_receipts.csv` table appears to be an older/interpolated "full-N 956" version, while the leaderboard + new-paper CSV reflect the actual (partial) attempted counts. Neither can be checked against receipts because receipts are gone. This inconsistency alone disqualifies MIMIC from any headline claim.

## Meaning of n=956 — UNVERIFIABLE from frozen evidence

Documentary intent (from `round1_worklog.md`, not evidence): 956 = cases in `cases_filtered_diverse.jsonl`, produced from the raw ICD-derived slice by (1) dropping Orphadata "NON RARE IN EUROPE" labels, (2) keeping only Exact ICD↔Orphanet relations, (3) capping 5 cases per disease → 956 cases across 239 diseases. So 956 is the **deduped, cap-limited cohort size (the attempted denominator)**, NOT raw candidates and NOT cases-with-confirmed-gold.

However: **no artifact on disk yields 956.** The cohort file is absent, the filter script cannot run without raw MIMIC, and gold is stripped. Per the brief: the number is **unverifiable from frozen evidence.** Note further that even the aggregates that survive mostly did NOT attempt 956 cases (many cells 100–500), so "956" is a cohort-size claim, not an evaluated-N for most cells.

## MIMIC version / inclusion / label source / dedup / exclusions (from scripts only)

- **Version:** MIMIC-IV-3.1 (worklog + tex). Only hosp+icu; **no MIMIC-IV-Note (`discharge.csv.gz`)** → no real free text.
- **Inclusion:** ICD-10 codes cross-referenced to Orphanet via Orphadata (2,173 ICD↔Orphanet mappings claimed).
- **Diagnosis label source:** Orphanet ID mapped from ICD-10 long title (structured), not clinician DDx.
- **Dedup unit:** per case row, capped 5 per Orphanet disease.
- **Exclusions:** Orphadata "NON RARE IN EUROPE" prefix; non-Exact relations.
- All of the above are **script-documented, not artifact-verified** (raw data absent).

## Capability pillar MIMIC actually serves

Nominally **P2 Phenotype-only DDx** (tex labels it L2 "Real EHR Noise"). In reality it is an **ICD-title → named-disease identification** task fed **synthetic vignettes built from ICD long titles** (round1_worklog: "no free-text vignette, only synthetic vignette from ICD titles"). The team itself reframed it (`scripts/mimic_rd_detection_pilot.py`, 2026-05-19) as "pick the rare disease from a comorbidity list" because standard DDx prompts mismatch the input. So the "Real EHR Noise / free-text EHR" framing in `4_benchmark_design.tex` and the abstract is **not supported** by the data as built. Regardless, it is an **unrun/irreproducible component** in the frozen tree.

## Reconciliation of the 6-point verification checklist

- dataset/system/backbone/eval-pass grid: **no receipts** → nothing to verify.
- n_planned/attempted/successful/failures: only from unreconcilable legacy aggregates; two sources disagree.
- primary metric numerator/denominator: **not recomputable** (no gold, no receipts).
- receipts↔aggregate reconciliation: **impossible** (receipts absent).
- same scoring / attempted-denominator / ontology-normalization as frozen main audit: **not applied to MIMIC** — MIMIC is absent from `frozen_main_manifest.csv`; the audit engine explicitly zeroes MIMIC gold.
- unified comparable matrix across systems: **does not exist** for MIMIC in the frozen set.

## Completed vs missing cells (dataset × system × backbone × capability)

- Frozen recomputed matrix (`frozen_main_manifest.csv`): MIMIC = **0 completed cells**.
- Legacy aggregates list up to 22 mimic_diverse cells, but these are **not reproducible or reconcilable** and are internally inconsistent → treated as **missing** for audit purposes.
- **Every MIMIC cell is missing** from a defensible frozen standpoint.

## Recommended paper handling

**Demote MIMIC out of the main experimental matrix.** Options in order of preference:
1. **Dataset-description-only** (Benchmark Design): describe the self-built MIMIC-IV-3.1 slice pipeline and the 956/239 cohort as a *constructed resource / future evaluation layer*, explicitly stating it uses ICD-derived synthetic vignettes (no discharge notes) and that per-case results are not part of the frozen release.
2. If any MIMIC result is retained at all, move it to an **appendix pilot** clearly labeled "not reproducible from the released frozen set; numbers from legacy run logs, cohort and receipts not redistributable under PhysioNet DUA," and drop it from every main table/figure.
3. **Cleanest: remove MIMIC numbers** from Abstract, Results heatmap, capability radar, and cost table until receipts + gold + cohort are restored and re-scored under the same audit rules as the other layers.

**Licensing note:** MIMIC-IV is credentialed PhysioNet data under a DUA that prohibits transmitting identifiable EHR to external LLM APIs and redistributing raw notes. Even if restored, only de-identified case IDs / aggregate counts / provenance may be emitted. This audit emitted none of the restricted raw text.

## `mimic_frozen_manifest.csv` — intentionally OMITTED

Not written. A frozen manifest requires per-cell recomputation from receipts under the audit's attempted-denominator + ontology-normalization rules. MIMIC has **no receipts and no gold**, so any manifest would be fabricated from unreconcilable legacy aggregates. Per the brief, it is omitted rather than invented.

## `mimic_case_level_results.csv` — intentionally OMITTED

Not written. No per-case receipts and no gold labels exist, so no per-case correctness is computable.
