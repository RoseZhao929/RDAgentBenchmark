# MIMIC-IV structured-EHR experiment plan

## Decision

With the data currently present, the strongest defensible MIMIC experiment is
not diagnosis from clinical notes. The best complete design has two linked
parts:

1. a **primary early-window structured-EHR prediction task**, using information
   available near admission to predict the rare-disease code assigned to the
   hospitalization; and
2. a **paired ICD leakage audit**, measuring rare-disease selection and
   ICD-to-Orphanet normalization from the coded problem list.

The local MIMIC-IV 3.1 installation contains `hosp/` and `icu/`, but no
MIMIC-IV-Note `discharge` or `radiology` tables. The 956-case cohort has no
`free_text_vignette` and no gold HPO terms. Its prose input is a deterministic
rendering of ICD long titles. The target disease title is frequently present in
that input, so an ordinary differential-diagnosis score confounds diagnosis,
rare-disease selection, and label recognition.

The first part uses real EHR events but remains a code-supervised prediction
task, not independently adjudicated clinical diagnosis. The second part is a
coding/normalization task. Neither may be called “free-text EHR diagnosis,”
“discharge-note diagnosis,” or “phenotype extraction from EHR.”

## Primary experiment: early-window structured EHR

### Target

Predict the exact-mapped ORPHA label attached to the index hospitalization.
The label comes from the admission's ICD-10 coding, but all target-bearing
diagnosis codes and their titles must be excluded from the model input.

### Indexing and split

- Recover `hadm_id` from the canonical case ID and join it locally to
  `admissions`, `patients`, and event tables.
- Prefer one index admission per patient for the primary cohort. If multiple
  admissions are retained, split and bootstrap at `subject_id`, never at
  admission, to prevent patient leakage.
- Freeze a patient-grouped development/test split before prompt development.
  Use the full 956 admissions for the final locked evaluation only after all
  prompts and mappings are frozen.
- Keep the exact ICD↔ORPHA cohort as primary. Any broader/narrower ontology
  relations belong in sensitivity analysis.

### Input available at prediction time

Create snapshots at 24 and 48 hours after `admittime`:

- age band and sex;
- admission type/location and non-identifying encounter metadata;
- abnormal laboratory results represented as test name plus
  low/normal/high, avoiding raw dates and identifiers;
- medications ordered or administered inside the window, normalized to generic
  names;
- procedures and services recorded inside the window;
- non-target prior/current diagnosis categories only if their availability
  before the prediction cutoff can be established.

Do not include discharge diagnoses, ICD long titles mapped to the target ORPHA,
post-window events, provider identifiers, free-form text, or raw dates. An
admission-wide feature without a trustworthy timestamp is excluded from the
primary input and may appear only in a clearly labeled retrospective
sensitivity arm.

The 24-hour snapshot is the primary endpoint; 48 hours is a secondary
information-growth analysis. This makes the clinical question explicit:

> Given structured information available early in a hospitalization, can an
> agent recover the rare disorder later represented in the discharge coding?

### Controls

- disease-frequency prior with no patient input;
- regularized bag-of-events classifier trained only on the development split;
- single-LLM structured prompt;
- best scaffolded agent using exactly the same serialized snapshot;
- oracle target-ICD lookup, reported only as a 100% mapping ceiling, not as a
  diagnostic baseline.

The classical bag-of-events model is essential: without it, an apparent agent
gain may simply reflect medication or laboratory co-occurrence that a simple
classifier can exploit.

### Required validity checks

- Target-code and synonym scanning after serialization, with zero tolerated
  leaks.
- Timestamp audit for every included table.
- Patient-grouped split and cluster bootstrap.
- Performance by disease frequency and number of early-window events.
- An input-ablation table: demographics only; labs; medications; procedures;
  all structured events.
- Manual review of at least 100 stratified snapshots to ensure that the
  serialized representation is clinically interpretable and does not contain
  target labels.

If too few admissions retain usable early-window events, report that attrition
as a result and keep the ICD leakage audit as the only MIMIC experiment. Do not
silently fall back to admission-wide post-hoc features.

## Research questions

1. How accurately can an agent identify the primary Orphanet-listed disorder
   from a noisy list of coded hospital diagnoses?
2. How much of that accuracy comes from the disease name appearing in the ICD
   long title?
3. Can the agent normalize an ICD code to the intended Orphanet concept without
   receiving the disease title?
4. After removing the target-bearing diagnosis entry, is there meaningful
   diagnostic signal in the remaining coded context?
5. Do multi-agent scaffolds improve normalization beyond a single-LLM control,
   or merely add cost?

## Cohort

- Use all 956 admissions in `cases_filtered_diverse.jsonl`.
- Keep the frozen set of 239 gold ORPHA labels.
- Treat admission, not patient, as the unit of analysis. Report explicitly that
  repeated patients may occur unless a subject-level deduplication audit proves
  otherwise.
- Primary analysis: cases whose primary ICD-to-Orphanet mapping relation is
  exact (`E`).
- Secondary sensitivity analysis: the complete diverse cohort including
  broader/narrower mappings (`NTBT` and `BTNT`).
- Report performance macro-averaged by ORPHA disease in addition to
  admission-level micro accuracy, because the cohort is disease-imbalanced.

## Secondary experiment: paired ICD leakage audit

Every admission appears in all three arms. Pairing is essential: differences
must be computed within admission rather than across independently sampled
sets.

| Arm | Input | Scientific interpretation |
|---|---|---|
| Title selection | ICD long titles, including the target-bearing entry | Rare-disease selection from a coded problem list; upper bound with direct lexical cue |
| Code selection | ICD-10 codes only | ICD knowledge and ICD-to-Orphanet normalization without a disease-name cue |
| Context only | Co-occurring titles after removing entries mapped to the gold ORPHA label | Negative control for residual contextual signal |

The key estimands are:

- `title_selection − code_selection`: benefit of direct disease-name wording;
- `code_selection − context_only`: benefit of the target ICD code itself;
- `context_only`: residual comorbidity/demographic signal and a sanity check
  against memorized cohort priors.

The builder is:

```bash
python3 scripts/mimic_structured_ehr_ablation.py
python3 scripts/mimic_structured_ehr_ablation.py \
  --output data/mimic_iv_rd_slice/structured_ablation_v1.jsonl
```

The first command prints only an aggregate manifest. The second creates
credentialed case-level inputs under the gitignored `data/` tree.

## Minimal model matrix for the ICD audit

Run a small, hypothesis-driven matrix rather than repeating every historical
agent/backbone cell:

| System | Purpose |
|---|---|
| Deterministic ICD→ORPHA lookup | Non-LLM ceiling/control for the code-selection arm |
| Single-LLM control on Gemini Flash | Main generative baseline and continuity with existing runs |
| MDAgents on Gemini Flash | Best historical scaffolded MIMIC cell |
| Single-LLM control on one independent backbone | Backbone-robustness check |

Use temperature 0, one attempt per case for the primary analysis, and identical
prompts and decoding limits across the two generative systems. A second seed or
three repeats is useful only if the provider cannot guarantee deterministic
decoding.

Do not run LIRICAL or VC-RDAgent on these arms: no HPO input exists, and mapping
ICD titles through an LLM-generated HPO list would introduce a different task.

## Outcomes and statistics

Primary outcome:

- early-window experiment: ontology-normalized top-1 accuracy at 24 hours;
- ICD audit: ontology-normalized top-1 accuracy in each paired arm.

Secondary outcomes:

- strict top-1 disease-name/ID accuracy;
- top-5 accuracy where a ranked list is requested;
- macro accuracy across the 239 diseases;
- exact-relationship-only accuracy;
- abstention and invalid-output rate;
- cost and latency per attempted admission.

Report attempted-case denominators. Errors, timeouts, and empty responses count
as incorrect in the primary intention-to-evaluate analysis. A success-only
accuracy may be shown only as a secondary operational diagnostic.

For arm contrasts, use paired bootstrap confidence intervals over admissions.
As a sensitivity analysis, cluster bootstrap by patient if `subject_id` can be
recovered locally. Use McNemar’s test for paired top-1 outcomes and apply
Holm correction to the predeclared arm contrasts. Also report disease-level
macro bootstrap intervals to prevent common disorders from dominating.

## Leakage and validity audits

Before model calls:

1. Verify all 956 gold labels are non-empty and record the cohort SHA-256.
2. Verify every target-bearing entry is identified by ORPHA ID, not merely by
   fuzzy text matching.
3. Count empty context-only inputs; retain them as impossible negative controls,
   rather than silently dropping them.
4. Inspect a stratified sample of at least 100 admissions across mapping
   relations and disease-frequency deciles.
5. Confirm prompts contain no gold disease name, ORPHA ID, or target ICD title
   in the code-selection and context-only arms.

The current cohort gold derives from the same ICD-to-Orphanet mapping used to
select cases. Consequently, the experiment evaluates mapping/selection, not
independently adjudicated clinical diagnosis. This circularity must appear in
Methods and Limitations.

## Evidence and release

Keep protected row-level data and model transcripts out of the public Git
repository unless the PhysioNet DUA clearly permits the proposed release.
Publish:

- code and environment lock;
- input and receipt SHA-256 manifests;
- aggregate cohort counts and mapping-relation counts;
- per-cell attempted/ok/error counts and aggregate metrics;
- exact scoring command and ontology snapshot version;
- instructions for credentialed researchers to regenerate the cohort.

Use one generated receipt as the sole source for the paper table, leaderboard,
figures, and cost appendix. Archive old partial-run summaries and never merge
them with the full 956-admission result.

## Paper integration

### Main paper

Keep the three non-MIMIC datasets as the primary diagnostic benchmark. Present
MIMIC as a structured-EHR experiment answering a different question:

> On a credentialed MIMIC-IV cohort derived from coded hospital diagnoses, we
> evaluate whether early structured hospital events predict the rare-disease
> label later represented in discharge coding, followed by a paired leakage
> audit of ICD-title and ICD-code cues. Because clinical notes are unavailable
> and the cohort gold is code-derived, this layer is not used as evidence for
> free-text clinical diagnosis.

Use one compact main-paper table for 24-hour structured-EHR results and place
the three ICD audit arms in the appendix. The most important audit result is the
paired accuracy drop across arms, not the absolute title-selection score.

### Claims to remove

- “Real EHR free-text” or “discharge-note” evaluation for this cohort;
- claims that MIMIC demonstrates phenotype extraction;
- claims that classical HPO tools fail on MIMIC because they cannot consume
  free text;
- averages that mix this mapping task with phenotype-based differential
  diagnosis datasets.

### Claims that remain defensible

- the cohort is derived from real MIMIC-IV hospital diagnosis records;
- it tests robustness to coded comorbidity lists and ontology normalization;
- paired masking quantifies lexical and code leakage;
- access-controlled reproducibility can be supported through scripts, hashes,
  aggregate receipts, and credentialed regeneration instructions.

## Upgrade path

If MIMIC-IV-Note later becomes available, create a new preregistered experiment
rather than silently replacing this one. Construct diagnosis-masked discharge
notes, establish independently reviewed gold labels, audit masking leakage, and
compare note-native diagnosis with note→HPO→diagnosis. That future experiment
would support the “real free-text EHR” claim; the current structured experiment
does not.
