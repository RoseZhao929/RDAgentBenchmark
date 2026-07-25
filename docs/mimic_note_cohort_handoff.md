# MIMIC-IV-Note cohort mapping and sampling handoff

This note separates the historical MIMIC cohort construction from the proposed
MIMIC-IV-Note replacement. That distinction matters: the old 956-admission
cohort was **not** the paper's prevalence-stratified N=2,000 design.

## Public mapping assets now in Git

All four public assets below are tracked on `main`; MIMIC files remain local.

| File | Role | Snapshot |
|---|---|---|
| `data/orphadata/en_product1.xml` | ICD-10 to ORPHA cross-references | 2025-12-09 |
| `data/orphadata/en_product9_prev.xml` | ORPHA prevalence classes | 2025-12-09 |
| `data/orphadata/en_product4.xml` | ORPHA to HPO phenotype associations | 2025-12-09 |
| `data/hpo/hp.obo` | HPO graph, including top-level organ-system ancestors | local frozen evaluator copy |

`en_product4.xml` was added in commit `01c91231`. Its SHA-256 is
`82079cfb9e6fdce0280001338618ecc8f4a5ae76d66f8e7c22e39fcdaebdebb7`.
It is the December 2025 Orphadata release, so it is version-aligned with
products 1 and 9. Orphadata is CC BY 4.0.

The files called `en_product4_HPO.xml` in informal discussion and
`en_product4.xml` here are the same *kind* of resource; the official Orphadata
filename is `en_product4.xml`.

## What the historical MIMIC filter actually did

The executable implementation is in:

- `harness/ingest/mimic_iv.py`
- `harness/ingest/mimic_iv_filter.py`

It performed these operations:

1. Read MIMIC-IV `hosp/diagnoses_icd.csv.gz`.
2. Keep ICD-10 rows and remove dots from codes before joining.
3. Map ICD-10 to ORPHA through Orphadata product 1.
4. Drop Orphadata entries whose disease name begins
   `NON RARE IN EUROPE`.
5. For the strict cohort, keep only relation `E` (exact ICD↔ORPHA mapping).
6. The historical “diverse” file then applied **cap 5 per ORPHA disease** in
   input order.

The historical local counts were:

| Stage | Admissions | ORPHA labels |
|---|---:|---:|
| Exact, non-non-rare frame | 18,480 | 239 |
| Historical cap-5 cohort | 956 | 239 |

The cap-5 command is retained below only to reproduce the old cohort. It must
not be used for the new prevalence-stratified N=2,000 cohort.

```bash
python3 -m harness.ingest.mimic_iv \
  --mimic-root /path/to/mimic-iv-3.1 \
  --orpha-xml data/orphadata/en_product1.xml \
  --relations E \
  --out data/mimic_iv_rd_slice/cases_exact_raw.jsonl

python3 -m harness.ingest.mimic_iv_filter \
  --in_path data/mimic_iv_rd_slice/cases_exact_raw.jsonl \
  --out_path data/mimic_iv_rd_slice/cases_filtered_diverse.jsonl \
  --only-exact \
  --cap-per-disease 5
```

The raw/derived JSONL files above are credentialed MIMIC derivatives and must
not be committed.

## Building the MIMIC-IV-Note candidate frame

The collaborator needs both MIMIC-IV and MIMIC-IV-Note. At minimum:

```text
/path/to/mimic-iv-3.1/hosp/diagnoses_icd.csv.gz
/path/to/mimic-iv-3.1/hosp/d_icd_diagnoses.csv.gz
/path/to/mimic-iv-3.1/hosp/admissions.csv.gz
/path/to/mimic-iv-3.1/hosp/patients.csv.gz
/path/to/mimic-iv-note/note/discharge.csv.gz
```

Generate the raw exact candidates with the first command above, then remove
explicitly non-rare entries **without** a disease cap:

```bash
python3 -m harness.ingest.mimic_iv_filter \
  --in_path data/mimic_iv_rd_slice/cases_exact_raw.jsonl \
  --out_path data/mimic_iv_rd_slice/cases_exact_note_frame.jsonl \
  --only-exact
```

Intersect `cases_exact_note_frame.jsonl` with admissions having a non-empty
discharge note, using `hadm_id`. If an admission has multiple discharge-note
rows, freeze and report one deterministic rule (recommended: concatenate in
`note_seq` order, or take the highest `note_seq`; do not select by model
outcome).

Before sampling, audit repeated `subject_id`. Use one index admission per
patient, selected by a frozen rule, or keep repeated admissions but split and
bootstrap at patient level. The first option is preferred for a clean
evaluation cohort.

This creates the candidate frame. Do not sample from the old 956-case file:
N=2,000 is mathematically impossible there, and the cap-5 distribution is
already distorted.

## Required N=2,000 prevalence-stratified design

Use seed 42 and sample admissions, not diseases:

1. Assign each admission's primary ORPHA label to one of:
   `common_rare`, `moderate`, `ultra_rare`, `super_rare`, or `unknown`, using
   `en_product9_prev.xml`. Use the same rules as
   `scripts/ablation_H1_prevalence.py`: prefer point prevalence; otherwise use
   another available estimate; when several remain, take the rarest class.
2. Compute each tier's proportion in the full note-bearing candidate frame.
3. Allocate the N=2,000 tier quotas proportionally (largest-remainder rounding).
4. Shuffle admissions *within tier* with a local deterministic RNG seeded 42
   and take the quota. This is prevalence-stratified sampling; there is no
   per-disease cap.
5. Map each ORPHA label to its HPO terms with `en_product4.xml`, then map those
   terms to top-level phenotype/organ-system ancestors through `hp.obo`.
6. Compare the selected sample with the full candidate frame. Report
   prevalence-tier and HPO-system proportions and absolute percentage-point
   differences. The stated target is at most 2 pp for every sufficiently
   covered category.

Product 4 supplies a **disease-level expected HPO profile**, not phenotypes
observed in the patient's note. Therefore the HPO-system comparison is a
sampling-balance check only. Any claim about patient-level phenotype
distribution requires a separate, frozen note-to-HPO extraction procedure.

Do not silently drop unmapped labels. In the old exact frame, the frozen
assets cover 14,809/18,480 admissions for prevalence and 11,986/18,480 for
ORPHA→HPO; only 181/239 and 144/239 unique labels, respectively. Keep and
report an `unknown` prevalence stratum and an `HPO-unmapped` category. If the
2 pp target cannot be met because of sparse or multilabel categories, report
the failure and the largest deviation rather than repeatedly changing the
sample.

## Reproducibility outputs

Keep these beside the credentialed data, not in public Git:

- selected `subject_id`, `hadm_id`, and `note_id` manifest;
- case-level ORPHA, prevalence tier, and HPO-system assignments;
- the prepared note text and model receipts.

The public handoff may contain only code plus an aggregate manifest with:

- MIMIC and MIMIC-IV-Note release versions;
- SHA-256 hashes of the four public mapping assets;
- candidate and selected counts;
- seed and exact selection/deduplication rules;
- mapping coverage and all distribution deltas;
- SHA-256 of the private selected-ID manifest.

## Important task interpretation

MIMIC-IV-Note publicly provides discharge summaries and radiology reports, not
a general longitudinal collection of admission notes. Diagnosis from a full
discharge summary is a real free-text EHR task, but it is retrospective and can
contain the diagnosis explicitly. It must not be described as early-admission
diagnosis. If the paper wants early prediction, use the timestamped structured
24-hour design already documented in `docs/mimic_structured_ehr_experiment.md`,
or obtain a note source that is genuinely available before the prediction
cutoff.
