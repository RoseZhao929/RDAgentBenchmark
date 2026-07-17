# OSF Pre-registration — Rare Disease Agent Benchmark

> **Status**: Draft v1, 2026-05-12. Submitter: [PI name TBD]
> **Submission target**: OSF Registries → "Time-stamped" registration
> **MUST be uploaded BEFORE unblinding the PMC OA cutoff-after holdout split**
> **Reference docs**: `plan.md` (full plan), `round1_plan.md` (Round 1 detail), `agent_methods.md` (lineup)

---

## 1. Study Information

### 1.1 Title

Rare Disease Agent Benchmark: A Multi-Pillar Evaluation of LLM-Based and Classical Diagnostic Agent Systems

### 1.2 Description

We benchmark **7 agent systems** (5 multi-agent or specialized rare-disease agents + 2 general medical agents) plus **3 LLM no-scaffold controls** and **1 classical non-LLM baseline (LIRICAL)** across **5 capability pillars** (phenotype extraction, phenotype-only DDx, genotype-aware DDx, family-aware DDx, clinical communication/reasoning) on **4 dataset layers** spanning ~84,000 cases with ≥12,000 distinct rare diseases.

This pre-registration freezes:
- 11 directional hypotheses (H1–H11) with effect-size predictions
- 12 planned ablations (A1–A12)
- Per-hypothesis statistical tests and multiple-comparison correction
- The cutoff-after holdout split protocol

### 1.3 Hypotheses Anchor Set

Each hypothesis below is independently testable; we use Holm–Bonferroni correction across the H1–H11 family.

#### H1 — Prevalence-tier monotonicity

Stratified by Orphanet prevalence layer ({≥1/2,000; 1/2,000–1/1M; <1/1M; "very rare/unknown"}):

Each agent's Recall@1 declines monotonically across layers.

- **Predicted effect**: 15–30 pp gap between common-rare and ultra-rare layers (anchored to RareBench RAMEDIS vs MME gap).
- **If falsified**: agent retrieving by phenotype pattern, not by frequency prior — desirable outcome to report.

#### H2 — General medical agents fail systematically on Pillar 3 (genotype-aware)

Rare-disease-specialized agents (DeepRare, RDMA, VC-RDAgent) outperform general medical agents (MDAgents, MedAgents, AgentClinic, MAI-DxO) on Pillar 3 Recall@1.

- **Predicted effect**: ≥20 pp gap on Pillar 3; ≤5 pp gap on Pillar 2.
- **Anchor**: DeepRare reports HPO-only 46.8% → HPO+VCF 70.6% Recall@1 on Xinhua (109 cases).

#### H3 — Tool-using agents are more cutoff-robust

On the cutoff-after PMC OA holdout split, agents with active retrieval (DeepRare with web tools restored, MAI-DxO with information requests, RDMA mining) show **smaller pre/post-cutoff Recall@1 drops** than parametric-only LLM controls.

- **Predicted effect**: 3–8 pp differential drop.
- **If confirmed**: load-bearing argument for tool-using rare-disease agents.

#### H4 — Multi-agent collaboration helps on complex cases, hurts on simple cases

Stratified by complexity (single-specialty vs multi-specialty needed, DeepRare-style):

MDAgents / MedAgents / MAI-DxO underperform single-LLM controls on low-complexity cases (over-thinking), exceed them on high-complexity cases.

- **Anchor**: MedAgentBoard (NeurIPS 2025) found multi-agent ≤ single-LLM on several medical tasks — pre-registering this hypothesis aligns or extends that counterintuitive finding.

#### H5 — Chinese cases expose English-anchored HPO mapping bias

On Chinese-language cases (PUMCH-ADM subset if accessible, otherwise PMC-OA Chinese journal subset built in Stream D Chinese layer):

English-trained agents show ≥10 pp Pillar 1 F1 drop and ≥5 pp downstream Recall@1 drop versus matched English subset.

- **Anchor**: RareBench reports Llama2-7B "unable to output normal results on long Chinese EHR text."

#### H6 — Reasoning-mode LLMs improve calibration more than accuracy

Comparing GPT-5 reasoning on/off and DeepSeek V3.2 reasoning on/off:

Reasoning-on yields ≥0.05 Brier improvement and <2 pp Recall@1 improvement.

- **Anchor**: MedHELM finds reasoning DeepSeek-R1 reaches 66% win-rate yet calibration metric deltas > accuracy deltas.

#### H7 — Failure modes cluster by specialty

Stratified by 14-body-system specialty (DeepRare taxonomy):

Per-agent ranking of weakest specialty correlates ρ ≥ 0.6 across agents — implying shared dataset/ontology gaps, not agent-specific weaknesses.

- **Anchor**: DeepRare "Lungs/Breathing" 31% vs "Kidneys" 66%.

#### H8 — Phenotype density non-linearly predicts performance

Bin by HPO-term count ({≤5, 6–15, 16–30, >30}):

Inverted-U: too few (under-specified) and too many (noise/distractors) both degrade Recall@1.

- **Anchor**: MIMIC-RD has ~128 phenotypes/case vs RAMEDIS ~6.

#### H9 — Family-aware (Pillar 4) gain accrues only on AR and X-linked cases

Stratified by mode of inheritance (MOI):

Family-history input produces ≥10 pp gain on AR/XL cases; ≤2 pp on AD/de novo.

- **Pillar 4 v1**: folded into Pillar 3 stratification (per Round 1 decision).

#### H10 — Faithfulness (D-class metric) is decoupled from accuracy

Spearman ρ between (Pillar 5 faithfulness rank: citation accuracy + reasoning chain validity) and (Pillar 2 accuracy rank) is < 0.5.

- **Anchor**: DeepRare flags "hallucinated citations" as Type-1 errors despite high diagnostic accuracy.
- **If confirmed**: strongest single argument for "accuracy is not sufficient."

#### H11 — Backbone effect dominates scaffolding for general agents but not for rare-disease agents

Holding backbone constant (DeepSeek V3.2 / GPT-5 / Gemini 3 Flash), variance across general agents (MDAgents / MedAgents / MAI-DxO / AgentClinic) is **smaller** than variance across rare-disease agents (DeepRare / RDMA / VC-RDAgent / LIRICAL).

---

## 2. Sampling / Datasets

### 2.1 Layered evaluation pool (frozen 2026-05-12)

| Layer | Source | Cases | Diseases | License |
|---|---|---|---|---|
| L1 Structured phenotype backbone | Phenopacket-Store | 10,051 | 751 OMIM | Apache 2.0 |
| L1 (cont.) | RareBench HF (4 splits) | 1,122 | mixed | Apache 2.0 |
| L2 Real EHR noise | MIMIC-IV rare disease slice (built per Stream C) | ~1,875 (target) | ~355 | PhysioNet credentialed |
| L3 Scale | RareArena RDS+RDC | 72,661 | ~8,000 | CC-BY-NC-SA |
| L4 Holdout (cutoff-after) | PMC OA, pub date ≥ 2024-01-01, MeSH = Rare Diseases ∨ Genetic Diseases Inborn | 200 (target after manual curation; ~1,626 definitive-diagnosis candidates already extracted) | mixed | CC-BY |

**Total v1 evaluation pool**: ~85,000 cases / >12,000 diseases.

### 2.2 Holdout split protocol (HOLDOUT MUST REMAIN BLINDED UNTIL THIS DOC IS REGISTERED)

- All PMC OA articles with publication date ≥ **2024-01-01** (after most named LLM backbones' training cutoff).
- Per-disease deduplication: only first case per (Orphanet ID, author cluster) retained.
- Manual review eliminates cases where the diagnosis appears in author's pre-2024 publications, conference abstracts, or preprints (Reviewer ARR M4 anticipated).

### 2.3 Pre-registration freeze date

This document is timestamped to OSF on the day of submission. **Holdout split metadata (PMC IDs, gold labels) MUST NOT be loaded into any LLM API call** before this date.

---

## 3. Variables

### 3.1 Independent

- **Agent system**: one of {MDAgents, MedAgents, AgentClinic, MAI-DxO, DeepRare, RDMA, VC-RDAgent, LIRICAL} (7 LLM-based agents + 1 classical baseline)
- **Backbone** (for LLM-based agents): one of {DeepSeek V3.2, GPT-5, Gemini 3 Flash Preview}
- **Pillar**: one of {P1_extraction, P2_phenotype_ddx, P3_genotype_aware, P4_family_aware (v2 only), P5_reasoning_communication}
- **Eval mode**: `gold_hpo` (canonical input) or `end_to_end` (free-text, agent extracts its own HPO)
- **Dataset layer**: one of {L1, L2, L3, L4} (per §2.1)

### 3.2 Dependent

- **Tier 1 (must report)**: Recall@1/3/5/10, Median Rank, MRR, HPO P/R/F1, Task Success Rate
- **Tier 2 (recommended)**: pass^k (k=4 or 8), Cost-Normalized Accuracy, Brier, ECE, Reference Accuracy
- **Tier 3 (exploratory)**: AgentProcessBench-style step-level scoring, CoT faithfulness, chaos-engineering robustness

### 3.3 Controlled / matched

- **Same backbone across agents** for the matched-backbone comparison run (defends against P11 reviewer attack from §6 of plan.md).
- **Deterministic seed** (where exposed by provider): seed=42 in initial pass.
- **Temperature**: 0.0 across all initial runs; alternative-temperature ablation (A5) reserved for reasoning-mode comparison.

---

## 4. Design Plan

### 4.1 Run structure

Two passes, both fully pre-registered:

- **Pass A — Gold-HPO** (primary): canonical HPO list fed to each agent; agents bypass their own Pillar 1 module where possible. All 5 pillars are **embarrassingly parallel** in this pass.
- **Pass B — End-to-end** (secondary): raw free-text vignette to agent; agent extracts its own HPO. P1 → {P2, P3, P4} serial per case.

The **Pass A − Pass B delta** is itself a reportable metric (per RareBench Table 6 precedent).

### 4.2 Sanity-check before unblinding

A `sanity-check` run on 200 cases (random sample stratified by source layer, **drawn from non-holdout pool only**) validates pipeline end-to-end with the 3 LLM controls. Errors discovered here do not invalidate pre-registration; they trigger code patches before the main run.

### 4.3 Holdout unblinding

After OSF registration timestamp, the manually-curated holdout (`data/pmc_oa_holdout/<finalized>.jsonl`, ~200 cases) is opened for evaluation. Pre/post-cutoff comparison uses pre-cutoff slices of L1-L3 as the "pre" arm.

---

## 5. Analysis Plan

### 5.1 Per-hypothesis tests (pre-registered)

| H | Test | Correction | Notes |
|---|---|---|---|
| H1 | Spearman ρ of agent's R@1 across prevalence tiers; one-sided test ρ<0 | Holm | Per-agent, then meta-aggregated |
| H2 | Paired bootstrap on R@1 (10⁴ resamples), comparing specialized vs general agents on P3 | Holm | Pillar 3 is the key |
| H3 | Difference-in-differences on R@1 pre vs post cutoff, tool-using vs parametric | Holm | Holdout-dependent |
| H4 | Two-way ANOVA (agent type × complexity), planned contrasts | Holm | Aligned with MedAgentBoard |
| H5 | Two-sample bootstrap on Pillar 1 F1 and downstream R@1, EN vs ZH | Holm | Depends on Chinese layer build-out |
| H6 | Paired bootstrap on (Brier, R@1) reasoning on vs off | Holm | Backbone-specific |
| H7 | Spearman ρ of per-specialty ranks across agents; threshold ρ≥0.6 | Holm | Descriptive primary |
| H8 | Trend test on R@1 across density bins; quadratic fit | Holm | |
| H9 | Two-sample test on Pillar 4 gain across MOI strata | Holm | v2 only |
| H10 | Spearman ρ between Pillar 5 faithfulness rank and Pillar 2 accuracy rank; threshold ρ<0.5 | Holm | Headline finding |
| H11 | Variance decomposition (mixed-effects, backbone as random, agent as fixed); F-tests | Holm | |

### 5.2 Effect sizes

For every pairwise comparison: **Cliff's δ** (rank-based, non-parametric).
For every metric reported: **bootstrap 95% CI** with ≥1000 resamples.

### 5.3 Multiple-comparison correction

Holm–Bonferroni across the H1–H11 family (α_family = 0.05).
Within-family per-stratum tests not corrected separately (controlled by parent-H Holm).

---

## 6. Ablation Catalog (pre-registered)

Each ablation A* answers a specific reviewer-anticipated question:

- **A1** DeepRare module ablation (case retrieval / web knowledge / self-reflection on-off)
- **A2** Multi-agent depth ablation (MDAgents PCC/MDT/ICT; MedAgents role count 1/3/5/7, rounds 1/2/3; MAI-DxO modes)
- **A3** Backbone × scaffolding 2×N grid (DeepSeek V3.2 vs GPT-5 vs Gemini 3 Flash on each agent)
- **A4** Rare-disease ontology ablation (HPO/Orphanet/OMIM tools on-off; replace with Wikipedia retrieval)
- **A5** Reasoning-mode on/off (where exposed)
- **A6** Post-cutoff holdout split (data leakage estimate via differential drop)
- **A7** LLM controls: zero-shot vs few-shot-static vs dynamic-few-shot vs MedPrompt
- **A8** Input format (gold HPO vs agent-extracted HPO vs free-text)
- **A9** Genotype channel (HPO-only vs HPO+VCF vs VCF-only) on P3
- **A10** Family-aware channel (with/without family hx; with/without pedigree; with/without MOI hint)
- **A11** Cost-cap sweep (per-case API budget at {$0.10, $0.50, $2, $10, unlimited})
- **A12** LLM-judge vs exact-match scoring (exact-OMIM/ORPHA; BioLORD synonym fuzzy; GPT-5 LLM-judge; physician adjudication on 200-case stratified sample)

---

## 7. Reviewer-Anticipated Attacks and Pre-registered Defenses

Mirroring `plan.md` §6:

1. **Data contamination** → A6 cutoff-after holdout + TS-Guessing + n-gram audit
2. **Unfair heterogeneous-agent comparison** → A8 dual-pass + per-agent adapter shim transparency
3. **Missing baselines** → LIRICAL (classical) + Med-fine-tuned LLM placeholder
4. **Statistical rigor** → bootstrap CIs + paired McNemar + Holm correction + Cliff's δ
5. **MIMIC ICU bias** → 4-layer stack; per-dataset stratification
6. **English-centric** → H5 + Chinese subset (Stream D Chinese layer)
7. **Arbitrary agent selection** → §3 inclusion criteria + Agent Fairness Matrix
8. **Multi-agent might not help** → A2 framed as a test, not a claim
9. **Cost is not clinically meaningful** → three independent cost axes (token / latency / simulated test fee)
10. **LLM-as-judge unreliable** → A12 + physician sub-sample agreement

---

## 8. Open Materials and Reproducibility

- **Pre-registered**: this document, H1–H11, A1–A12, canonical case schema, harness code (release tag v0.1.0 at submission)
- **Open data**: PMC OA holdout JSONL (post-manual-review), Orphanet cross-map, MIMIC-IV slice script (data not redistributable)
- **Docker image**: per agent, with pinned model versions and `.env` template
- **Leaderboard**: static-site at submission, full 400-cell matrix in appendix

### 8.1 Backbone version pinning

| Alias | Model ID | Cutoff | Notes |
|---|---|---|---|
| `BACKBONE_LO` | `deepseek/deepseek-v3.2-exp` | TBD | Cheap end |
| `BACKBONE_HI` | `openai/gpt-5` | TBD | Frontier |
| `BACKBONE_GEMINI` | `google/gemini-3-flash-preview-20251217` | 2025-12-17 | 3rd LLM control |

(Exact dated versions pinned at submission; preview→GA migration noted in limitations.)

---

## 9. Deviations / Updates

A deviation log will accumulate any post-registration changes (e.g., backbone preview→GA migration, ablation scope adjustments). Material deviations require a justified addendum.

---

## 10. Submission Checklist

- [ ] All 11 hypotheses include directional prediction and effect-size estimate
- [ ] All 12 ablations include reviewer-question they answer
- [ ] Statistical tests + correction specified per hypothesis
- [ ] Holdout split protocol frozen (PMC OA cutoff date + dedup + manual curation rules)
- [ ] Backbone versions specified with dates
- [ ] Pre-registration uploaded to OSF; timestamp ≤ holdout unblinding date
- [ ] Round-1 execution report (`round1_execution_report.md`) cross-referenced
- [ ] Full hash of canonical_case schema attached as supplementary
