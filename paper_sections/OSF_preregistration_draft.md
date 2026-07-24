# OSF Pre-Registration Draft — `RareAgentBench`

> **Unregistered historical draft.** This file was prepared as a possible
> OSF submission but was never registered and has no OSF ID or registration date.
> It is included to document the proposed analysis plan, not as evidence of
> prospective registration.
>
> **Status note**: because no OSF registration occurred before the reported
> analyses, the paper describes H1--H11 and A1--A12 as repository-defined.
> Any future confirmatory study must register a revised protocol before
> collecting or unblinding a new independent holdout.

---

## A. Project metadata

- **Proposed title**: Prospective evaluation of LLM agent systems on rare-disease
  diagnosis
- **Authors**: Yu Tian Zhao, et al.
- **Registration date**: not assigned (registration never completed)
- **License**: data CC-BY-NC-SA 4.0; code Apache 2.0
- **Intended registration type**: post-data-collection analysis plan; never
  submitted and not a prospective pre-registration

---

## B. Hypotheses (H1–H11)

The draft proposed the following hypotheses, directional predictions, and
effect-size thresholds. They were not formally pre-registered.

| # | Statement | Test statistic | Direction | Threshold |
|---|---|---|---|---|
| H1 | On super-rare diseases (<1/1,000,000) classical baselines beat scaffolded LLM agents at R@1 | 2-proportion z-test | classical > LLM | p < 0.05 (one-sided), δ ≥ 10 pp |
| H2 | Genotype channel (P3: HPO + variants) gives ≥ +10 pp R@1 over P2 (HPO-only) on any single agent | within-agent paired z | P3 > P2 | p < 0.05 one-sided |
| H3 | Post-cutoff PMC OA holdout R@1 differs from pre-cutoff layer R@1 by ≤ 5 pp absolute | diff of proportions | (no direction predicted) | reject if |Δ| > 5 pp at p < 0.05 |
| H4 | Multi-agent scaffolding helps more on cases with ≥4 affected HPO organ systems than ≤1 (DoD) | difference-of-differences | scaffold benefit grows | p < 0.05 |
| H5 | LLM R@1 on Chinese rare-disease cases (PUMCH) is ≥ 5 pp lower than on English ones | paired z | English > Chinese | p < 0.05 |
| H6 | GPT-5 with `reasoning_effort=medium` is better calibrated (ECE↓) than `minimal` | paired ECE | medium < minimal | p < 0.05 |
| H7 | Cross-agent specialty rank correlation ρ ≥ 0.6 (shared blind spots) | Spearman ρ on per-specialty R@1 | ρ positive | ρ ≥ 0.6 |
| H8 | Inverted-U: R@1 at 16–30 HPO terms per case > R@1 at ≤5 terms | 2-proportion z | peak > sparse | p < 0.05 |
| H9 | On AR/XL cases, family-aware agents gain ≥ +10 pp R@1 vs proband-only | within-pair z | family-aware > proband-only | p < 0.05 |
| H10 | Faithfulness-rank and accuracy-rank decouple: Spearman ρ < 0.5 | Spearman ρ | ρ < 0.5 | upper-bound test |
| H11 | (retired in the repository plan; not in paper) | n/a | n/a | n/a |

**Family-wise correction**: Holm–Bonferroni at α = 0.05 over the testable
subset of H1–H11; H3/H5/H6/H9 are deferred if their data sources are
unavailable at submission (documented as Limitations).

---

## C. Ablations (A1–A12)

| # | Name | Status in draft |
|---|---|---|
| A1 | Top-1 vs Top-5 metric A/B | mechanical |
| A2 | Strict ID vs cross-mapped | superseded by A4 in repository plan |
| A3 | Backbone × scaffolding 2×N | required for paper §6.2 |
| A4 | Strict vs ORPHA-fuzzy-variants | required for paper §8.1 |
| A5 | Silver gold vs physician gold | conditional on holdout completion |
| A6 | TS-Guessing contamination audit | required for §7.10 |
| A7 | Single LLM judge vs dual-judge | required for §7.5 |
| A8 | GPT-5 reasoning_effort axis | optional (cost-constrained) |
| A9 | Subprocess timeout cap | required for §8.6 |
| A10 | Prevalence-stratified R@1 | required for H1 |
| A11 | Cross-dataset agent ranking stability | required for §7.6 |
| A12 | LLM-judge swap | required for §7.5 |

---

## D. Datasets

| Layer | Source | Cases | Disease IDs | Allowed for development? | Allowed for evaluation? |
|---|---|---|---|---|---|
| L1 phenotype | Phenopacket-Store + RareBench HF | 11,173 | OMIM + ORPHA + CCRD | ✓ | ✓ |
| S-EHR (amended exploratory probe) | MIMIC-IV structured admissions | 956 | ORPHA (code-derived) | excluded | separate; pending |
| L3 scale | RareArena RDS | 72,661 | ORPHA | ✓ | ✓ (stratified N=500) |
| **L4 temporal set** | PMC OA pub ≥ 2024-01-01 | 200 (target) | ORPHA + OMIM | overlap audited | temporal sensitivity analysis |

These are proposal values, not the executed denominators: the frozen large-layer
diagnostic cells use attempted \(N=2{,}000\), the realised post-cutoff set has
198 cases, and the structured-EHR replacement remains unscored.

The draft proposed one run per (agent, backbone) cell with the same evaluation
pipeline as L1–L3 and no metric, prompt, or scaffold tuning based on the
temporal set. This prospective lock was not executed; the paper therefore
reports the PMC set only as an overlap-audited temporal sensitivity analysis.

---

## E. Sample sizes & power

- **Pre-cutoff diagnostic layers**: RareBench at full N; large
  (PP-Store, RareArena) at N=500 stratified sample (seed=42, proportional
  allocation across prevalence tiers).
- **Holdout**: target N=200 physician-annotated. Realistic floor N=150
  given annotation attrition. At N=150 we have ≥80% power to detect
  a 10-pp R@1 difference between any two agents at α=0.05 (computed
  with 2-prop z-test assuming p₁=0.30).

---

## F. Stopping rules

- Each (agent, backbone) cell stops at full N for small layers / N=500
  for large layers / N=200 for L4. **No early stopping on positive
  results.**
- If a cell exhibits a systematic crash pattern (>5% timeout/error
  rate), we re-run once after fixing the cause, logged in the
  per-baseline reproduction doc.
- We do **not** continue accumulating data on cells that have already
  hit the planned N just because the result is borderline.

---

## G. Analysis pipeline

- **Evaluator**: `harness/metrics/cross_map.py:gold_hit_with_crossmap`
  with `gold_hit_with_variants` for the dual-reported variants column.
- **Statistical tests**: 2-prop z-test for H1/H2/H8, Spearman ρ for
  H7/H10, difference-of-differences for H4, paired z for within-agent
  comparisons.
- **Confidence intervals**: bootstrap 1000-iter percentile, 95%.
- **Multiple-testing correction**: Holm–Bonferroni at α=0.05 family-wise.
- **LLM-judge protocol** (for P5 faithfulness): Gemini-judge primary,
  Claude-judge confirmation; report Cohen's κ; require κ ≥ 0.6 to
  publish judge-derived numbers.

---

## H. Analyses outside the proposed registration

These analyses were outside the proposed confirmatory family and are reported
descriptively:

- MIMIC structured-EHR protocol is an explicitly amended exploratory analysis,
  not represented as part of the proposed registration.
- Backbone × cost-per-call analysis (§6.3) beyond the cells in the H/A
  table above.
- the contamination audit LLM ρ band (the *value* of ρ ≈ 0.3 is observational; only the
  *dichotomy LLM ρ > 0 vs classical ρ ≈ 0* is interpreted as confirming
  anticipated objection #1 is bounded).
- Any post-hoc subgroup analysis not in the proposed DoD/H7 axes.

---

## I. Deviations from the draft plan

We disclose relevant changes in an "Analysis-plan deviations"
table in Appendix D of the camera-ready paper, with: (a) what changed,
(b) why, (c) what direction the change biased results.

---

## J. Prospective re-use of this draft

Anyone running an additional rare-disease agent system on the L4 holdout
can use the same protocol (their results would be reported in the
external-replication appendix of subsequent papers). Required:
(i) the same evaluator binary (Apache 2.0), (ii) the same disease-ID
cross-map (Orphadata), (iii) the same prevalence-tier strata.

---

## K. References

- Full hypothesis enumeration in development shorthand.
- Section 4 (benchmark design) — dataset stack, evaluation N per
  dataset.
- Sections 5.2–5.4 — repository analysis-plan narrative and status disclosure.
- Current Holm–Bonferroni result snapshot, to be re-run at full N
  before L4 unblinding.
