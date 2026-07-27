# Data-Leakage Audit — Four Non-MIMIC RareAgentBench Datasets

**Frozen commit:** `e85cb3ca7d5b58e5296c8d589d1deaa8cfe4e6f6`
**Run (UTC):** 2026-07-24 01:11 UTC
**Mode:** READ-ONLY, OFFLINE, no LLM calls. Pure string/ID matching.
**Normalizer:** `harness.pmc_oa.orphanet._normalize` (lowercase, strip punctuation, collapse whitespace) — the same function the repo uses for scoring.
**Synonyms:** parsed live from `data/orphadata/en_product1.xml` (11,456 disorders; 7,084 OMIM→ORPHA crossmap keys).
**Runtime env:** `.venv_audit/bin/python` (rapidfuzz 3.14.5).

---

## What the agent actually sees (verified from ingest + adapter code)

The main-matrix runner (`scripts/phase4a_runner.py:208`) calls
`adapter.predict(case, pillar="P2_phenotype_ddx", eval_mode="gold_hpo", ...)`.
All free-text adapters route the case through
`harness/agents/_adapter_utils.py::case_to_question(case, eval_mode="gold_hpo")`.

Under `eval_mode="gold_hpo"` the `end_to_end` free-text branch is **never taken**.
The case-specific input is assembled by this branch priority (after an optional
Demographics line):

```
gold_hpo_terms  →  synthetic_vignette  →  free_text_vignette
```

Per dataset, the resulting **model input** is:

| dataset (split) | input fields fed to agent (verified) | source |
|---|---|---|
| `phenopacket_store` | HPO term **labels + IDs** ("label (HP:xxxxxxx); …"). No prose. | `harness/ingest/phenopacket_store.py` sets `free_text_vignette=None`, `synthetic_vignette=None`; populates `gold_hpo_terms` |
| `rarebench` (RAMEDIS/LIRICAL/MME/HMS) | **bare HPO IDs** ("(HP:xxxxxxx); …"); `label=None` in ingest | `harness/ingest/rarebench.py` sets `free_text_vignette=None`; HPO IDs only |
| `rarearena_rds` (RDS) | **`free_text_vignette` = full `case_report` prose** (has no HPO → falls through) | `harness/ingest/rarearena.py` sets `free_text_vignette=record["case_report"]`, `gold_hpo_terms=[]` |
| `pmc_oa_holdout` (post-cutoff) | **`free_text_vignette` = "Clinical phenotypes: <term>; <term>; …"** (gold_hpo_terms empty → falls through) | `data/pmc_oa_holdout/holdout_gold_opus.jsonl` |
| `pmc_precutoff` (pre-cutoff) | same "Clinical phenotypes: …" phenotype-list vignette | `data/pmc_precutoff/holdout_gold_opus.jsonl` |

**Held out as gold (must NOT appear in input):** `gold_label` = `{omim_id, orphanet_id, ccrd_id, disease_name}`.

**Scope note on measurement:** rates are computed on the **case-specific input
only**. The fixed Task-instruction boilerplate that `case_to_question` appends is
excluded because it is constant across every case and itself contains the example
acronym "CADASIL" (which would otherwise inject a spurious identical hit into
every row). This is the conservative choice.

---

## Masking / redaction: NONE

Grep of ingest adapters and prompt builders (`mask|redact|scrub|blind|deidentif|
replace.*diagnosis`) found **no input-side masking or redaction anywhere** in the
pipeline. The only `mask`/`blind` hit is a *reviewer instruction string* in
`harness/pmc_oa/finalize.py` ("…before OSF pre-registration unblinding the
holdout") — a curation-process note, not code that scrubs the model input.

**Verdict per dataset: NOT MASKED (all four).** Whatever is in the input fields
above reaches the agent verbatim. The mitigating factor is not masking but the
**nature of the inputs**: three of the four feed HPO/phenotype-term lists rather
than diagnostic prose, which structurally carries little name/ID leakage. Only
RareArena feeds real free-text case reports.

---

## Leakage rates

| dataset (split) | n_audited | exact_name_rate | synonym_rate (long ≥5) | identifier_rate | title_leak_rate | masked? |
|---|---|---|---|---|---|---|
| phenopacket_store | 10,051 (all) | 0.68% | 0.33% (denom 7,235; 2,816 n/a) | 0.00% | n/a | not masked |
| rarebench (RAMEDIS+LIRICAL+MME+HMS) | 1,122 (all) | 0.00% | 0.00% (denom 1,114; 8 n/a) | 0.09% (1 case) | n/a | not masked |
| rarearena_rds (RDS) | 2,000 (sample of 8,562, seed=42) | 0.00% | 0.00% (denom 2,000) | 0.00% | 0.00% | not masked |
| pmc_oa_holdout (post-cutoff) | 198 (all) | 2.02% | 0.00% | 0.00% | n/a | not masked |
| pmc_precutoff (pre-cutoff) | 220 (all) | 5.45% | 0.91% | 0.00% | n/a | not masked |

**Secondary / diagnostic columns** (not the headline, reported for transparency):

| dataset | short/acronym synonym hits (len ≤4) | fuzzy synonym rate (WRatio partial ≥90) | synonym n/a (no ORPHA mappable) |
|---|---|---|---|
| phenopacket_store | 97 / 10,051 (0.97%) | 0.29% | 2,816 (OMIM w/o ORPHA crossmap) |
| rarebench | 1 / 1,122 | 0.00% | 8 |
| rarearena_rds | 17 / 2,000 (0.85%) | 0.10% | 0 |
| pmc_oa_holdout | 0 / 198 | 1.52% | 0 |
| pmc_precutoff | 5 / 220 (2.27%) | 0.45% | 0 |

- **exact_name_rate** = fraction of cases where the normalized `gold_label.disease_name`
  (or the mapped ORPHA canonical name) appears as a substring of the input.
- **synonym_rate** = fraction (over ORPHA-mappable cases) where any Orphanet
  synonym of length ≥5 (normalized) appears in input. Denominator excludes
  cases with no ORPHA id available; those are counted "n/a".
- **identifier_rate** = any `ORPHA:xxxx`/`OMIM:xxxxxx` and common variants
  (`ORPHA xxxx`, `Orphanet xxxx`, bare number, `#xxxxxx`, `MIM xxxxxx`) in input.
- **title_leak_rate** = first-sentence-of-`case_report` heuristic; only meaningful
  for RareArena (the only dataset with real prose). None of the four datasets
  carries a dedicated `title` field, so PMC/phenopacket/rarebench are **n/a**.

---

## Interpretation (conservative)

**Bottom line: none of the four non-MIMIC datasets shows material answer leakage
into the agent input, and none is masked (but little needs masking).**

- **phenopacket_store — negligible (0.68% exact, 0% id).** Input is HPO
  labels+IDs, not disease prose. The small exact-name rate is a genuine but benign
  artifact: a disease name occasionally *equals* an HPO term label (e.g.
  "Galactosemia", "Anaplastic astrocytoma"). This is an ontology-vocabulary
  overlap, not the pipeline echoing the answer. 2,816 cases are OMIM-only with no
  ORPHA crossmap, so their synonym channel is honestly **n/a**.

- **rarebench — effectively zero (0% exact/synonym).** Input is *bare HPO IDs*
  (ingest sets `label=None`), so no natural-language disease text is present at
  all. The single identifier "hit" (1/1122) is a bare-number coincidence and
  should be treated as noise.

- **rarearena_rds — near-zero, and this is the surprising, load-bearing finding.**
  RareArena is the ONE dataset that feeds full free-text case reports, so the
  prior expectation was high name leakage. It is not: **0/2000 in the sample, and
  only 6/8,562 (0.07%) across the full set** state the gold `Orpha_name` verbatim
  in the case report. The RareArena case reports are written as
  presentation-only vignettes with the diagnosis stripped. Its LLM R@1 therefore
  reflects genuine DDx, **not** reading the answer out of the text. (The 17
  short-synonym hits are ≤4-char acronym coincidences, not real leakage.)

- **pmc_oa_holdout / pmc_precutoff — low but non-zero (2.0% / 5.5% exact).** These
  vignettes are Opus-extracted "Clinical phenotypes: …" term lists. The exact-name
  hits arise where the extraction folded a *diagnosis-level* term into the
  phenotype list (genuine: "Anaplastic astrocytoma", "Nephroblastoma", "Serrated
  polyposis") — a mild self-leak channel worth noting — **plus** some short-name
  substring false-positives (verified example: gold "Noma" matches inside
  "schwannoma"). The true exact-leak rate is therefore *at most* the reported
  figure and likely a bit lower after removing ≤4-char substring FPs. **No
  identifier leakage at all.** Pre-cutoff leaks modestly more than post-cutoff.

**Effect on reported R@1:** The datasets whose R@1 could be inflated by
"reading-comprehension" rather than de-novo diagnosis are, at most, the two small
PMC holdout splits at the 2–5% level — small enough that it cannot materially move
aggregate R@1. RareArena, despite being free-text, is clean. Phenopacket/RareBench
carry structured phenotype input with essentially no disease-name or ID leakage.

---

## Caveats / unverifiable-from-frozen-data

- Rates are on the case-specific input under `eval_mode="gold_hpo"` (the main
  matrix). If any experiment ran with `eval_mode="end_to_end"` (which would feed
  `free_text_vignette` even when HPO exists), phenopacket/rarebench inputs would
  differ — but no such invocation was found in `scripts/phase4a_runner.py`
  (it hard-codes `gold_hpo`). Other bespoke runners were not exhaustively traced;
  flagged as **partially verified**.
- Exact-name substring matching over-counts on very short gold names (≤4 chars,
  e.g. "Noma"). Short/acronym synonym hits are reported in a separate column for
  the same reason; treat those as an upper bound, not real leakage.
- OMIM-only phenopacket cases (2,816) without an in-repo ORPHA crossmap have their
  synonym channel marked **n/a**, not 0 — we did not fabricate a mapping.
- Fuzzy-synonym column (WRatio partial ≥90) is a secondary heuristic signal only;
  headline rates are deterministic exact/substring matches.

---

## Files produced (all under `audit_frozen/leakage_audit/`)

- `leakage_summary.md` — this file.
- `leakage_case_level.csv` — 13,591 rows (one per audited case): `dataset, split,
  case_id, gold_orpha, gold_omim, gold_name, input_char_len, exact_name_hit,
  identifier_hit, synonym_hit, title_hit`. De-identified IDs + 0/1 flags only; no
  raw input text. RareArena rows are the 2,000 sampled cases.
- `leakage_audit.py` — the reproducible script (`.venv_audit/bin/python
  audit_frozen/leakage_audit/leakage_audit.py`).
- `_summary.json` — machine-readable aggregate the table above is built from.
