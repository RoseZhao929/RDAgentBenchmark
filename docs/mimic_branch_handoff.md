# Branch handoff: MIMIC structured-EHR repair

Branch: `experiment/mimic-structured-ehr-best-design`  
Base: `main` at `e85cb3ca`

## Why this branch exists

`main` excludes MIMIC from the frozen recompute but still contains old MIMIC
point estimates and language describing the cohort as real free-text EHR. Local
inspection recovered the credentialed 956-case cohort, 22 historical prediction
files and gold labels, but also established that the cohort has no clinical
notes or HPO terms: all old prose is deterministically rendered from ICD titles.

This branch repairs both the experiment definition and the paper-wide
construct-validity mismatch.

## Main differences from `main`

### Experiment

- Adds `scripts/build_mimic_early_structured_snapshots.py`.
  - Joins the frozen 956-admission cohort to timestamped labs, prescriptions,
    procedures and services.
  - Produces paired 24 h / 48 h structured snapshots.
  - Excludes diagnosis codes/titles, notes, post-window events, provider IDs and
    raw dates from model input.
  - Separates `model_input` from `evaluation_only.gold_label`.
  - Hashes patient IDs into a grouping key for patient-clustered splitting.
- Adds `scripts/mimic_structured_ehr_ablation.py`.
  - Builds `title_selection`, `code_selection` and `context_only` arms.
  - Links target-bearing entries by ORPHA ID rather than fuzzy text.
- Adds dependency-free unit tests for the leakage-arm builder.

### Paper

- Changes the benchmark description from “four diagnostic layers / Real EHR
  Noise” to “three diagnostic layers + one separately reported structured-EHR
  probe.”
- Removes legacy MIMIC cells from the diagnostic headline table and recomputes
  its three-dataset averages.
- Removes old MIMIC rows from the diagnostic cost appendix and leaderboard.
- Removes claims that MIMIC is free text, a structured note, HPO-only, or
  evidence of phenotype extraction.
- Adds a dedicated construct-validity limitation covering code-derived gold,
  absence of notes, leakage, DUA and separate reporting.
- Marks the replacement MIMIC protocol as an amended exploratory analysis in
  the preregistration draft.

### Reproducibility and review

- Adds `docs/mimic_structured_ehr_experiment.md`, the full statistical and paper
  integration protocol.
- Adds `docs/mimic_full_paper_consistency_audit.md`, the mandatory final review
  gate covering source text, generated TeX, tables, figures, references,
  receipts, leaderboard and rendered PDF.
- Protected MIMIC outputs remain under gitignored `data/`; only code, aggregate
  counts and hashes are committed.

### Figure, caption and numerical consistency pass

- Figure 2 now states why only three of the five dataset resources appear:
  only Phenopacket-Store and RareBench have paired LLM/classical results;
  RareArena is LLM-only, PMC has no matched classical run, and MIMIC is a
  separate pending task.
- The judge-swap panel no longer labels Gemini-to-Claude as a causal
  self-preference estimate. Judge identity and family relation change together;
  `mdagents` additionally changes trace completeness and is dashed.
- The appendix capability matrix marks MIMIC P2/P5 amber/pending rather than
  “evaluated in v1.”
- All active figure captions now explain scope, N/denominator, missing marks and
  important confounds. Observational HPO-density, prevalence, contamination and
  specialty plots were stripped of causal wording.
- Cost language is standardized to receipt-weighted diagnostic means:
  GPT-5 $7.91 vs V4-Flash $0.33 per 1,000 cases (about 24×).
- The headline table was reconciled row by row to
  `audit_frozen/frozen_main_manifest.csv`; bracketed values are attempted N.
  This corrected stale success-denominator Ns and several stale point estimates,
  including the V4-Flash RareArena cells.
- Stale claims that no backbone wins universally were removed: Gemini is the
  observed PP-Store winner for every listed agent in the frozen manifest, with
  smaller unequal DeepRare denominators disclosed.
- The temporal PMC and literature-frequency analyses are framed as sensitivity
  analyses, not proof against memorisation; exact PMCID overlap with RareArena
  is disclosed. The matched-pipeline table is no longer mislabeled
  “difficulty-matched”; the separate HPO-count/prevalence-balanced result
  (0.479 vs 0.541, 728 attempts per era) is reported explicitly.
- `paper_figures_tables.md` is now an inventory of the current PDF rather than
  the obsolete pre-Phase-4 figure wish list.
- The paper no longer claims formal OSF pre-registration. The bundled file has
  placeholder metadata and is explicitly labelled an unregistered historical
  draft; H1--H11 and A1--A12 are described as a repository-defined analysis
  family with Holm multiplicity control.
- Reproducibility wording now distinguishes the 93-row legacy receipt (including
  22 obsolete MIMIC rows), the 83-row frozen evidence manifest, and the 71
  diagnostic cells in the headline/cost matrix.
- The central classical claim is now dataset-specific rather than universal:
  classical/offline systems lead decisively on Phenopacket-Store and the
  super-rare tail, while RareBench is near parity.
- The same-trace Gemini/Claude judge check now reports the recomputed
  unweighted Cohen's κ = 0.477 over 160 binned axis labels; the earlier
  unsupported κ value and causal “family effect” language were removed.
- Literal placeholder citations were replaced with resolved bibliography
  calls. MIMIC-IV, MIMIC-IV-Note, MIMIC-RD, RareArena, Phenopacket-Store,
  DeepRare, PhenoBrain, the rare-disease systematic review and judge-bias
  references were checked against primary publication metadata.
- `scripts/build_leaderboard.py` now reads the attempted-denominator frozen
  manifest directly and publishes a diagnostic-only manifest. Its former
  success-denominator values and obsolete sample-size banner no longer diverge
  from Table 1.
- `scripts/phase4a_report_gen.py` is explicitly a legacy three-diagnostic-
  dataset aggregator. It neither loads protected MIMIC gold nor merges the old
  ICD-title task into diagnostic summaries.

## Validation completed on 2026-07-24

- Rebuilt every paper figure, all generated TeX, the 41-page ACL PDF and the
  Overleaf upload bundle.
- PDF log: no fatal errors, undefined citations/references, or overfull boxes.
- Visual review covered the architecture overview, all main result figures,
  M1 scope caption, M5 judge-swap table/figure, design matrix, schema,
  contamination/specialty plots, references and final appendix pages.
- Reconciled all 61 comparable Table 1 value/N fields against
  `audit_frozen/frozen_main_manifest.csv` with zero mismatches.
- `test_mimic_structured_ehr_ablation.py`: 4/4 tests passed.
- `scripts/sanity_check_evaluator.py`: 17/17 checks passed.

## Locally generated evidence

These files are not tracked:

- `data/mimic_iv_rd_slice/structured_ablation_v1.jsonl`
- `data/mimic_iv_rd_slice/early_structured_v1.jsonl`

Observed feasibility:

- cohort: 956 admissions, 239 ORPHA labels;
- patient groups: 709;
- leakage audit: 2,868 rows (956 × 3 arms);
- context-only empty after target removal: 340/956;
- early structured snapshots: 1,912 rows (24 h + 48 h);
- non-empty: 954/956 at 24 h and 956/956 at 48 h.
- exact gold disease-name occurrences in serialized model input: 0 at both
  windows;
- early snapshot output SHA-256:
  `8692ce58cde89f51755b780e62d9ec092e0405a03b582dea88e821627a27a452`.

Re-run locally:

```bash
python3 scripts/mimic_structured_ehr_ablation.py \
  --output data/mimic_iv_rd_slice/structured_ablation_v1.jsonl
python3 scripts/build_mimic_early_structured_snapshots.py
```

## Work intentionally not fabricated

The branch does not invent replacement model scores. Paid agent/backbone runs
must use the frozen snapshots and write a new task-versioned receipt before any
MIMIC performance number is reintroduced. Until then, the paper describes the
protocol and excludes legacy MIMIC scores from diagnostic claims.

## Collaboration rules

1. Do not edit generated `paper_build/acl/tex/*.tex` by hand; edit
   `paper_sections/*.md` and rebuild.
2. Do not re-add old `phase4a_summary.json` MIMIC cells to the main table,
   averages, leaderboard or cost analysis.
3. Do not commit credentialed row-level MIMIC input or transcript files.
4. Any new receipt must carry task version, cohort hash, window/arm, prompt
   hash, attempted/error denominators and ontology snapshot.
5. Before merge, complete every applicable item in
   `docs/mimic_full_paper_consistency_audit.md`.
