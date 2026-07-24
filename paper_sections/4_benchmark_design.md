# §4 Benchmark Design(paper draft v0)

> 数据源:`plan.md` + `agent_methods.md` + `罕见病benchmark方案.md` + 实际 harness 代码
> 目标长度:**~1.5 main-paper page**(~1,500-1,800 words)
> 状态:**Methodology 全成熟,figures/tables 等数据**

---

## Draft for paper main text

## 4.1 Five Capability Pillars

We decompose rare-disease diagnosis into **five distinct capability pillars**, each individually testable, jointly forming the evaluation surface. The pillar choice is grounded in three considerations: (i) clinical workflow steps (phenotype recognition → DDx generation → genetic confirmation → family interpretation → communication), (ii) the dimensions on which existing rare-disease agents claim differentiation (DeepRare's reference accuracy, MAI-DxO's budgeted reasoning), and (iii) reviewer-anticipated criticism that accuracy alone is insufficient \citep{equitymedqa2024}; Pillar 5 directly addresses this.

The five pillars, and which data layer carries each, are summarised in the
benchmark-surface figure. Briefly: **P1** Phenotype Extraction (free-text EHR
→ ranked HPO list; P/R/F1); **P2** Phenotype-only DDx (HPO list → ranked
diseases; Recall@1/3/5/10, median rank, MRR); **P3** Genotype-aware DDx (HPO +
structured variants → disease + causative gene; Gene Top-k, cross-mapped R@1);
**P4** Family-aware DDx (HPO + trio/pedigree → disease + mode of inheritance;
deferred to v2 pending pedigree-bearing data); and **P5** Reasoning
Faithfulness (agent trace + prediction → a four-axis factual / relevance /
depth / faithfulness score; the current 40-trace LLM-judge sensitivity study
is exploratory, and physician validation remains future work).

**Why five and not three.** P1 and P5 in particular face the objection "isn't this just preprocessing or just a stylistic axis?". Both are load-bearing for our central claim. P1 is independent because §7.1 shows, in a same-case paired test, that downstream P2 R@1 is measurably sensitive to HPO-extraction quality — extraction is not a free preprocessing step (and the dual-pass design is what lets this be measured without confounding it with dataset difficulty). P5 is independent because §7.4/§7.5 examine whether faithfulness ranking decouples from accuracy ranking (repository-plan Hypothesis 10); we report H10 as exploratory (a modest same-trace judge difference remains, but the current Gemini-to-Claude comparison cannot identify a pure family effect), and the durable point is that accuracy-only evaluation can miss hallucinated citations and unfaithful reasoning chains — a Type-1 error category discussed by DeepRare \citep{deeprare2026}.

**Bias as cross-cutting lens, not pillar.** Following HELM and MedHELM
precedent \citep{helm2022,medhelm2025}, we apply available stratifications
(prevalence tier, specialty, age group, sex, and HPO density) across relevant
pillar metrics rather than treating bias as a separate axis. Dedicated
fairness evaluations \citep{equitymedqa2024,heal2024,omiye2023,zack2024}
remain complementary: ancestry and language analyses cannot be claimed in v1
because the current frozen resources do not support them.

## 4.2 Datasets — Three Diagnostic Layers + One Structured-EHR Probe

We assemble three diagnostic layers and one secondary structured-EHR probe; their
sources and sizes appear as the columns of the benchmark-surface figure, and
the full per-layer breakdown (disease counts, ID anchors, free-text / gold-HPO
/ variant availability) is detailed in Appendix A. The diagnostic layers are **L1**
Phenotype Backbone (Phenopacket-Store + RareBench HF; 11,173 cases; HPO-only,
gold HPO, variants on PP-Store), **L2** Scale + Free Text (RareArena RDS/RDC;
72,661 verbatim case reports), and **L4** Cutoff-After Holdout (self-built PMC
OA, publication date ≥ 2024-01-01; 198 model-verified cases with physician
annotation in progress). Separately,
**S-EHR** is a credentialed MIMIC-IV-3.1 probe \citep{mimiciv31}
(956 admissions, 239 exact-mapped
ORPHA labels) for early structured-event prediction and ICD leakage auditing.
The replacement protocol is specified but not yet scored; it is not pooled
with differential-diagnosis results.

**Rationale per layer.**

* **L1** establishes apples-to-apples comparison with RareBench's KDD'24 numbers — required by reviewers ("why not just compare to RareBench").
* **S-EHR** is designed to test whether agents can use real structured hospital events rather than curated case reports. The 24-hour primary snapshot uses timestamped labs, medications, procedures and services; it excludes target-bearing diagnosis codes/titles, post-window events and free text. Gold is derived from exact ICD-10→Orphanet mapping, so this is code-supervised retrospective prediction, not independently adjudicated diagnosis. A paired audit will compare ICD titles, ICD codes only, and context after removing target-bearing entries.
* **L2** addresses scale; RareArena's 72,661 cases span 45.6% of Orphanet. Released CC-BY-NC-SA, so we use it for academic evaluation only and acknowledge license bounds.
* **L4** responds to the leakage and benchmark-composition concerns in the
  2026 systematic review \citep{sysreview2026}. We extract PMC OA case reports
  published after 2024-01-01 via E-utilities and map diagnoses to Orphanet.
  The 198-case post-cutoff set has model-based verification but physician
  annotation is still in progress. Exact PMCIDs overlap RareArena, so L4 is a
  temporal sensitivity analysis, not an independently clean holdout.

**Total resource pool: ~85,000 cases**, with v1 analyses stratified where
supported by prevalence tier, specialty, age group, sex, and HPO density. The
current scored diagnostic study is English-language; a Chinese diagnostic
layer is deferred (§9).

**Evaluation N per dataset — honest disclosure.** We deliberately separate
"pool size" (the released benchmark) from "evaluation N" (what we run for the
v1 paper).
- **RareBench-HF** has 1,122 cases. Primary general-agent cells use the full
  attempted N; DeepRare and MAI-DxO have explicitly smaller adapter-specific N.
- **Large layers** (Phenopacket-Store 10,051; RareArena RDS 72,661): the primary
  `llm_control`/MDAgents/MedAgents matrix uses a shared, prevalence-stratified
  cap of N=2,000 case IDs (seed=42). DeepRare, MAI-DxO, and a small number of
  failed-to-launch adapter cells have smaller attempted N shown in Table 1.
- **MIMIC** will use its own attempted-admission denominator and separate
  receipts after the replacement experiment is run.

This is a **prevalence-stratified evaluation, not a power-stratified extrapolation
to full pool**; bootstrap CIs in §6 quantify the resulting uncertainty per cell.
We confirmed via our sampling-validation check that the N=2,000 stratified sample reproduces the full-N
prevalence band and HPO-organ-system distribution within ±2 pp.

## 4.3 Canonical Case Representation

The three diagnostic layers ingest into a single Pydantic v2 schema,
`CanonicalCase` (illustrated in the canonical-case figure), and every agent
adapter projects from this representation to the agent's native input. The
pending MIMIC protocol uses an analogous model-input/evaluation-only record and
maps the structured snapshot at the adapter boundary. The record groups an
identity block (`case_id`, `source_dataset`, `source_split`, `language`), an
input block (demographics; `free_text_vignette` / `synthetic_vignette`;
`gold_hpo_terms`; `variants`; local `vcf_path`; `family`), a parallel-ID gold
label, and free-form metadata.

Three design decisions deserve note: (a) gold labels are **parallel IDs** (OMIM/ORPHA/CCRD), reflecting genuine ontology disagreement across datasets — Phenopacket-Store uses OMIM, RareArena uses ORPHA, CCRD anchors the Chinese-listed 207 diseases. Evaluator must accept cross-mapped matches via Orphadata (§4.5). (b) `synthetic_vignette` is distinguished from `free_text_vignette` so we can audit any evaluation that relies on LLM-synthesized prose (§7 disclosure). (c) `vcf_path` carries a local-only file pointer; PhysioNet DUA prohibits transmission of identifiable EHR data to external LLM APIs, so adapter shims projecting Pillar 3 inputs convert structured variant info to abstracted strings before any cloud-LLM call.

## 4.4 Dual-pass evaluation

Every pillar is evaluated in two modes. In **Pass A** (gold-HPO, primary) the
case's curated HPO terms are fed directly to the agent's downstream pillar,
bypassing its own extractor — isolating downstream capability and enabling
apples-to-apples comparison on identical inputs. In **Pass B** (end-to-end) the
raw free-text vignette is fed in and the agent extracts HPO itself before
reasoning, measuring real deployment performance. The **Pass A − Pass B delta**
is itself a reported metric (following RareBench's phenotype-vs-EHR-text
comparison \citep{rarebench2024}); we show it is non-uniform across agents
(§7.1), which turns the input heterogeneity of a mixed-agent lineup into a
measured axis rather than a confound (§5.1).

## 4.5 Metrics and matching

We report Recall@1/3/5/10, median rank and MRR for the DDx pillars, P/R/F1 for
phenotype extraction, and task-success rate; a recommended tier (pass\^k,
cost-normalised accuracy, calibration, reference accuracy) and an exploratory
tier (step-level and reasoning-faithfulness scores) are defined in Appendix C.
Every accuracy metric is stratified where metadata and sample size permit;
v1 reports prevalence tier, specialty, age group, sex, and HPO-density
analyses, while ancestry and language remain deferred. A predicted
disease ID counts as a hit if it is prefix-equal on the same ontology,
cross-mapped via Orphadata (OMIM ↔ ORPHA), or fuzzy-matches an Orphanet name or
synonym at rapidfuzz score ≥ 90 — a threshold calibrated against 217 audited
borderline cases (>85% of the 70–89 band were false positives); the audit tape
is released for reproducibility (Appendix N).

---

## Working Notes / Citations TODO

### Citations needed beyond §3

- HELM (Liang et al., 2022) | §4.1 (bias-as-cross-cutting)
- EquityMedQA (Pfohl et al., Nature Medicine 2024) | §4.1
- HEAL (Schaekermann et al., eClinicalMedicine 2024) | §4.1
- Omiye et al., npj Digital Medicine 2023 | §4.1
- Zack et al., Lancet Digital Health 2024 | §4.1
- Eiz AlDin et al., MIMIC-RD arXiv:2601.11559 (2026) | §4.2
- Rivera et al., JAMIA 32(1) 2025 | §4.5
- CLEAR framework (arXiv 2511.14136) | §4.5
- FaithCoT-Bench | §4.5
- AgentClinic 24-bias | §4.5

### Strengths of this draft

1. **每个 design choice 都 anchor 一个 anticipated objection / 一个 precedent**(不抽象,不空洞)
2. **数字密度高**:具体的 case 数 / 疾病数 / 阈值 / cross-reference count
3. **Honest disclosure**:`synthetic_vignette` 跟 `free_text_vignette` 分开;non-rare filter 揭露 88,664 entries 被砍;fuzzy 90 threshold 由 audit 后定
4. **Bias 不当 pillar** 的修正背后历史敢说出来 — 反 strawman + 显得 thoughtful

### Still missing(等数据)

- CanonicalCase schema and benchmark-surface figures are rendered by
  `scripts/paper_schematics.py`.
- Table A1 / A2 / A3 完整版去 appendix(本节 main text 只放精简表)
- §4.2 L4 holdout 200 case 数字会在 final 阶段更新

### Length check

~1,400 words 现在,目标 1.5 page main paper 约 1,800 words。还有 ~400 words 空间。

可以扩的:
- §4.4 加一段双 pass 数学化定义(eg let R@k(Pass A) = ...)
- §4.5 metric taxonomy 加一个小公式 box 显示 Cost-Normalized Accuracy = accuracy / USD-per-case
- §4.2 加一段说明 RareArena CC-BY-NC-SA 跟我们 academic license 的兼容性

或保持现状交 reviewer 由他们 decide。
