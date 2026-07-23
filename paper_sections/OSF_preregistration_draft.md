# OSF Pre-Registration Draft — `RareAgentBench`

> **Draft for OSF.io submission.** Copy this verbatim into the OSF
> registration form. After OSF assigns the ID, replace the placeholder
> `<TODO-OSF-ID>` in §5.4 of the paper with the real ID.
>
> **Important**: this document must be **frozen and submitted to OSF BEFORE
> running any post-cutoff PMC OA holdout evaluation cell**. The three
> pre-cutoff diagnostic layers (L1 Phenopacket-Store, L2 RareArena,
> RareBench HF) are *development* data and may be re-run as bugs are
> found; the L4 holdout is *evaluation* data and is touched only once
> after this pre-registration is locked.

---

## A. Project metadata

- **Title**: Pre-registered evaluation of LLM agent systems on rare-disease
  diagnosis
- **Authors**: Yu Tian Zhao, et al.
- **Contact**: kbessietiffany5Yjas@germanymail.com
- **Frozen date**: 2026-MM-DD (user enters before OSF submit)
- **License**: data CC-BY-NC-SA 4.0; code Apache 2.0
- **Registration type**: Pre-registration (standard, post-data-collection
  variant — Phase 4a development data already collected; L4 holdout
  evaluation has NOT begun)

---

## B. Hypotheses (H1–H11)

All hypotheses are pre-registered with directional prediction and effect-size
threshold where applicable.

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
| H11 | (retired before pre-registration; not in paper) | n/a | n/a | n/a |

**Family-wise correction**: Holm–Bonferroni at α = 0.05 over the testable
subset of H1–H11; H3/H5/H6/H9 are deferred if their data sources are
unavailable at submission (documented as Limitations).

---

## C. Ablations (A1–A12)

| # | Name | Status at pre-reg |
|---|---|---|
| A1 | Top-1 vs Top-5 metric A/B | mechanical |
| A2 | Strict ID vs cross-mapped | superseded by A4 (decided pre-reg) |
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
| S-EHR (amended exploratory probe) | MIMIC-IV structured admissions | 956 | ORPHA (code-derived) | no notes | separate |
| L3 scale | RareArena RDS | 72,661 | ORPHA | ✓ | ✓ (stratified N=500) |
| **L4 holdout** | PMC OA pub ≥ 2024-01-01 | 200 (target) | ORPHA + OMIM | ❌ (UNTOUCHED) | ✓ once, only after this OSF lock |

Pre-registration freezes the L4 evaluation protocol: **one** run per
(agent, backbone) cell with the same eval pipeline as L1–L3; no metric
tuning, no agent prompt modification, no scaffold swap based on L4
performance.

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
  hit their pre-registered N just because the result is borderline.

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

## H. What is exploratory (not pre-registered)

These analyses are reported for context but are *not* part of the
pre-registered claims and will not be used to make headline statements:

- MIMIC structured-EHR protocol is an explicitly amended exploratory analysis,
  not represented as part of the original preregistration.
- Backbone × cost-per-call analysis (§6.3) beyond the cells in the H/A
  table above.
- the contamination audit LLM ρ band (the *value* of ρ ≈ 0.3 is observational; only the
  *dichotomy LLM ρ > 0 vs classical ρ ≈ 0* is interpreted as confirming
  anticipated objection #1 is bounded).
- Any post-hoc subgroup analysis not in the pre-registered DoD/H7 axes.

---

## I. Deviations from pre-registration

We commit to disclosing any deviation in a "Pre-registration deviations"
table in Appendix D of the camera-ready paper, with: (a) what changed,
(b) why, (c) what direction the change biased results.

---

## J. Re-use of this pre-registration

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
- Sections 5.2–5.4 — pre-registration narrative.
- Current Holm–Bonferroni result snapshot, to be re-run at full N
  before L4 unblinding.
