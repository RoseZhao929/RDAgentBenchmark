# §9 Limitations and Future Work (paper draft v0)

> 写作目的:anticipated objection 主动 surface —  锁的 12 个攻击点,这里 acknowledge 6 个真实 gap,其余在前文 already pre-empted。
> 状态:文字 ready;依赖 §6 cell 数据完成后 pin 最终数字(MAI-DxO timeout n, MIMIC slice n 等)

---

We surface six concrete limitations and three deliberate scope exclusions
of v1.  Each is paired with the section that pre-empts the related
anticipated objection.

**(L1) MAI-DxO × GPT-5 and DeepRare × GPT-5 cells missing.**  Two
(agent × backbone) cells are systematically incompatible.  (a) MAI-DxO's
panel orchestration over 3 deliberation iterations exceeded our 600 s
subprocess cap on GPT-5 in every pilot case, even with
`reasoning_effort=minimal` propagated.  (b) DeepRare's local-embedding
pipeline calls `eval_tokenizer(diseases, max_length=36)` on the
agent-emitted candidate list; GPT-5 at `reasoning_effort=minimal`
emits an empty `diseases` list with high frequency, raising
`IndexError` in `transformers.tokenization_utils_fast` (50/50 cases
failed in Phase 2 v2).  Both failures share a broader pattern —
**frontier reasoning models with reasoning forced off may under-emit
content in agent scaffolding loops that consume model output
downstream**.  We exclude these two cells rather than the full GPT-5
row; the same cells on DeepSeek V3.2 and Gemini 3 Flash complete in
90–180 s (MAI-DxO) and 25/25 ok (DeepRare).  The pattern is
reasoning-budget × downstream-consumer specific and tractable with
`reasoning_effort=high`, but that re-introduces the silent
`max_tokens` consumption we documented in §5.2.

**(L2) PhenoBrain dropped from agent lineup.** PhenoBrain
\citep{phenobrain2025} was on our original scout list. Its 14 GB Google
Drive checkpoint is hosted under nested sub-folders whose permission
chain blocks programmatic `gdown` listing; we obtained 7.6 GB of the
checkpoint by manual download before deciding the partial state was
unsafe to evaluate.  We replaced PhenoBrain with LIRICAL (the canonical
classical Bayesian baseline) in the v1 lineup.  Future work re-includes
PhenoBrain once the upstream authors confirm a public mirror.

**(L3) Chinese diagnostic layer not evaluable from public data.**  RareBench's
PUMCH-ADM subset is drawn from a 1,650-case single-center cohort at Peking
Union Medical College Hospital (PUMCH; 1,183 rare + 467 common).  We
investigated whether a Chinese layer could be built and found two compounding
barriers.  First, the **labelled** corpus (cases carrying the `RareDisease`
OMIM/Orphanet/CCRD ground truth) is not publicly distributed; the source
publication provides **no data-access application channel or data-use
agreement**, reporting only an ethics approval (S-K2051), so obtaining it would
require direct institutional collaboration rather than a self-serve download.
Second, the *only* PUMCH data that is public — the public 87-case PUMCH slice
released with the RareBench code — contains **phenotype annotations
only** (Chinese entity strings paired one-to-one with standardised HPO terms)
and **no diagnosis labels**, so it cannot be scored for differential
diagnosis.  A Chinese diagnostic layer (and hypothesis H5 on English-anchoring
bias) is therefore deferred to v2, contingent on the restricted labelled
corpus.  The Chinese-language slot is already wired through our canonical case
model and data loader to enable a one-call extension once such data is obtained
(Future Work item 2).

**(L4) Pillar 4 (family-aware) and H9 not testable on the current
corpus.**  We verified (2026-05-29) that our ingested data carries **no**
structured family/pedigree or inheritance-mode signal: the
Phenopacket-Store cohort export we use has 0/200 files with a pedigree
block, and the family-structure and inheritance-mode fields are
unpopulated across the ingested diagnostic resources.
Independently, no agent in our lineup performs *family-aware diagnosis*
(DeepRare and MAI-DxO explicitly do not consume pedigrees; only RDMA
exposes a family-history toggle, and it is a phenotype-extraction, not a
diagnosis, component). Repository-plan **H9** ("family-aware gains accrue
only on AR/XL cases") therefore cannot be evaluated without a new
pedigree-bearing corpus (e.g. MyGene2 / DDD) and a Pillar-4 diagnosis
path; both are deferred to v2.  v1 reports four pillars (P1–P3 + P5).

**(L5) HPO extraction silver gold is LLM-generated.**  Our Pillar 1
end-to-end evaluation (§7.1) compares extractors against an Opus 4.7
silver-gold reference rather than physician-annotated gold.  We mitigate
this in three ways: (a) Opus is held out from the agent and judge
lineup so no agent is judged against its own backbone; (b) we report
inter-rater Jaccard between Opus and Gemini 3 Flash silver-gold (0.41)
to surface non-redundancy of the reference; (c) the 200-case PMC OA
post-cutoff holdout is being annotated by the user (clinical co-author)
to convert to physician-validated gold for the camera-ready revision.
As an interim stand-in (Ablation A5, §8), a **frontier-model agent
(Claude Opus 4.8) independently verified all 198 held-out cases** against
the full paper text: it concurred with the Gemini extractor's *diagnosis*
in **198/198** cases and judged the extracted HPO **90.4 %** precise
(8.7 % of terms flagged unsupported — mostly negation and subtype errors),
with a recall gap (687 salient phenotypes it judged missed). At
camera-ready we recompute A5 with the physician gold and report
Opus-vs-physician Cohen's κ.

**(L6) Cost reporting heterogeneity.** Six of the nine implementations
(including the no-scaffold control) route hosted calls through our OpenRouter
wrapper and report exact USD per call. RDMA uses an off-wrapper hosted path,
so its hosted-model cost is estimated from logged tokens and the frozen price
table (≤5% band). LIRICAL and VC-RDAgent are offline and incur zero hosted-LLM
cost; that zero is not an estimate of compute or staffing cost. Appendix J
reports only diagnostic cells and labels this accounting boundary explicitly.

**(L7) Literature-frequency association on LLM backbones.** Our A6
TS-Guessing audit (§7.10 / §8.9) finds Spearman ρ between log
pre-cutoff PubMed mention count and per-disease R@1 of **0.29–0.37**
across all four LLM backbones (Gemini 3 Flash, GPT-5-minimal, DeepSeek
V4-Flash, V4-Pro), versus **ρ ≈ 0** on classical/offline baselines
(LIRICAL, VC-RDAgent — methodological control). Thus LLM R@1 has a weak
literature-frequency association. It is compatible with training exposure,
but Spearman ρ cannot be squared and interpreted as a causal fraction of R@1
variance, nor does this audit yield a numeric “contamination band.” A second
sensitivity test (**H3,
§7.10.1**) compares pre- and post-cutoff PMC sets built with the identical
pipeline (same source, query, extractor, and gold verification): pooled
Gemini R@1 is **0.57 pre-cutoff vs 0.62 post-cutoff** on the clean-gold
subset. A separate HPO-count/prevalence-matched check retains the same
direction (**0.479 vs 0.541**, 728 attempted predictions per era), but
unknown prevalence limits that matched subset. Performance does not drop,
but the sets are not contamination
free: 17/198 post-cutoff and 13/220 pre-cutoff cases share exact PMCIDs and
gold ORPHA identifiers with RareArena. We therefore do not infer that
memorisation is absent. We make the association and overlap transparent
rather than dropping the pre-cutoff layers; the classical near-zero controls
and F1's opposite-direction rarest-tier contrast provide useful context, not
a causal upper bound.

**(L8) MIMIC-IV is structured and code-supervised, not a clinical-note
diagnosis benchmark.** Our local MIMIC-IV 3.1 installation
\citep{mimiciv2023,mimiciv31} contains the `hosp` and `icu` modules but not
the separately distributed MIMIC-IV-Note resource
\citep{mimicivnote22}. The 956-admission cohort was
selected and labelled by exact ICD-10→Orphanet mapping; its earlier synthetic
vignettes deterministically rendered ICD long titles and sometimes exposed the
target disease lexically. We therefore remove those legacy point estimates from
the diagnostic matrix and its cross-dataset averages. The replacement
protocol will be reported separately after scoring: its primary input is a timestamped 24-hour
structured snapshot (labs, medications, procedures and services) with
target-bearing codes/titles and post-window events excluded; a paired
title/code/context audit quantifies leakage. Because gold remains code-derived,
this evaluates retrospective code-supervised prediction and ontology
normalisation, not independently adjudicated diagnosis, free-text reasoning or
HPO extraction. Row-level inputs remain access-controlled under the PhysioNet
DUA; before scoring, public reproducibility consists of code, hashes and
credentialed regeneration instructions, with aggregate receipts to follow.

---

## 9.1 Deliberate scope exclusions (these are *not* defects — they are scope choices)

**(S1) Retrospective, not prospective.**  We frame the benchmark as
**retrospective decision support** evaluation, not autonomous
diagnosis.  No clinical claims are made.  Anticipated objection #12 is pre-empted in §10 Conclusion.

**(S2) No fine-tuned medical LLM baseline.**  Meditron-70B and
OpenBioLLM-70B are not in the v1 backbone set — we focus on frontier
general-purpose backbones plus DeepSeek V3.2 as the open-weight
contrast.  Adding a fine-tuned medical baseline is Future Work item 3;
the harness is backbone-agnostic and the addition is purely a
deployment task.

**(S3) Single-image / multimodal pillar absent.**  Rare-disease
phenotyping increasingly involves facial photograph, MRI, or
electron-microscopy signal.  v1 is text-only.  v2 adds a multimodal
pillar (Future Work item 4).

---

## 9.2 Future work (in order of expected impact)

1. **Pillar 4 (family-aware)** — once Phenopacket-Store pedigree fields
   are normalised + MyGene2 / DDD access converges, ~1 month effort.
2. **Chinese rare-disease layer (PUMCH-ADM)** — once institutional
   agreement returns, drop-in dataset add.
3. **Fine-tuned medical LLM backbone** — add Meditron-70B and
   OpenBioLLM-70B to the backbone-axis grid (A8 extension).
4. **Multimodal pillar (P6)** — facial / radiograph inputs; requires
   new agent set (face2gene, …).
5. **Prospective clinical study** — partner with rare-disease referral
   centre to A/B-test scaffolded agents against current-of-care
   workup.  This is the long-term clinical-deployment ask the v1
   benchmark is designed to *enable*, not *substitute*.

---

## 9.3 Cross-references to pre-empted anticipated objections

| Attack | Where addressed |
|---|---|
| #1 Data contamination | §7.10 + §8.9 (A6) + §9 L7 + Appendix D |
| #2 Heterogeneous-agent fairness | §5.1 Agent Fairness Matrix |
| #4 Statistical rigor | §6 footnote (Holm–Bonferroni + bootstrap CI) |
| #5 MIMIC construct validity / ICU bias | §4.2 structured-EHR probe + §9 L8 |
| #7 Arbitrary agent selection | §5.1 inclusion matrix and §5.4 analysis-plan disclosure |
| #8 Multi-agent doesn't always help | §7.2 + headline finding F2 |
| #9 Cost not clinically meaningful | §6.3 three-axis cost reporting |
| #10 LLM-judge unreliable | §7.5 + Ablation A12 |
| #11 Model version changes silently | §5.2 dated aliases + Appendix N Docker hash |
| #3, #6, #12 | §9 above (L2, L3, S1) |
