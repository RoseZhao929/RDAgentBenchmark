# §4 Benchmark Design(paper draft v0)

> 数据源:`plan.md` + `agent_methods.md` + `罕见病benchmark方案.md` + 实际 harness 代码
> 目标长度:**~1.5 main-paper page**(~1,500-1,800 words)
> 状态:**Methodology 全成熟,figures/tables 等数据**

---

## Draft for paper main text

### 4.1 Five Capability Pillars

We decompose rare-disease diagnosis into **five orthogonal capability pillars**, each individually testable, jointly forming the evaluation surface. The pillar choice is grounded in three considerations: (i) clinical workflow steps (phenotype recognition → DDx generation → genetic confirmation → family interpretation → communication), (ii) the dimensions on which existing rare-disease agents claim differentiation (DeepRare's reference accuracy, MAI-DxO's budgeted reasoning), and (iii) reviewer-anticipated criticism that accuracy alone is insufficient (Pfohl et al., Nature Medicine 2024; Pillar 5 directly addresses this).

The five pillars, and which data layer carries each, are summarised in the
benchmark-surface figure. Briefly: **P1** Phenotype Extraction (free-text EHR
→ ranked HPO list; P/R/F1); **P2** Phenotype-only DDx (HPO list → ranked
diseases; Recall@1/3/5/10, median rank, MRR); **P3** Genotype-aware DDx (HPO +
structured variants → disease + causative gene; Gene Top-k, cross-mapped R@1);
**P4** Family-aware DDx (HPO + trio/pedigree → disease + mode of inheritance;
deferred to v2 pending pedigree-bearing data); and **P5** Reasoning
Faithfulness (agent trace + prediction → a four-axis factual / relevance /
depth / faithfulness score, LLM-judge with 200-case physician-κ validation).

**Why five and not three.** P1 and P5 in particular face the objection "isn't this just preprocessing or just a stylistic axis?". Both are load-bearing for our central claim. P1 is independent because §7.1 shows, in a same-case paired test, that downstream P2 R@1 is measurably sensitive to HPO-extraction quality — extraction is not a free preprocessing step (and the dual-pass design is what lets this be measured without confounding it with dataset difficulty). P5 is independent because §7.4/§7.5 examine whether faithfulness ranking decouples from accuracy ranking (pre-registered Hypothesis 10); we report H10 as exploratory (the judge-family effect is real but modest once trace-capture is controlled), and the durable point is that accuracy-only evaluation can miss hallucinated citations and unfaithful reasoning chains — a Type-1 error category the DeepRare authors flagged in their own work.

**Bias as cross-cutting lens, not pillar.** Following HELM and MedHELM precedent, we apply bias evaluation (genetic ancestry, prevalence tier, sex / X-linked, pediatric/adult, language, HPO density) as a **stratification of every pillar's metric**, not as a separate axis. This was an explicit design revision; an earlier sketch listed Bias as a sixth pillar, which we abandoned because (a) no general-purpose AI benchmark elevates bias to a pillar — those that do (EquityMedQA, HEAL, Omiye et al., Zack et al.) are dedicated fairness probes, not holistic benchmarks; (b) treating bias as a pillar reduces its measurement coverage by isolating it from accuracy evaluation.

### 4.2 Datasets — Three Diagnostic Layers + One Structured-EHR Probe

We assemble three diagnostic layers and one secondary structured-EHR probe; their
sources and sizes appear as the columns of the benchmark-surface figure, and
the full per-layer breakdown (disease counts, ID anchors, free-text / gold-HPO
/ variant availability) is detailed in Appendix A. The diagnostic layers are **L1**
Phenotype Backbone (Phenopacket-Store + RareBench HF; 11,173 cases; HPO-only,
gold HPO, variants on PP-Store), **L2** Scale + Free Text (RareArena RDS/RDC;
72,661 verbatim case reports), and **L4** Cutoff-After Holdout (self-built PMC
OA, publication date ≥ 2024-01-01; 200 manually-verified cases). Separately,
**S-EHR** is a credentialed MIMIC-IV-3.1 probe (956 admissions, 239 exact-mapped
ORPHA labels) for early structured-event prediction and ICD leakage auditing.
It is not pooled with differential-diagnosis results.

**Rationale per layer.**

* **L1** establishes apples-to-apples comparison with RareBench's KDD'24 numbers — required by reviewers ("why not just compare to RareBench").
* **S-EHR** addresses whether agents can use real structured hospital events rather than curated case reports. The 24-hour primary snapshot uses timestamped labs, medications, procedures and services; it excludes target-bearing diagnosis codes/titles, post-window events and free text. Gold is derived from exact ICD-10→Orphanet mapping, so this is code-supervised retrospective prediction, not independently adjudicated diagnosis. A paired audit compares ICD titles, ICD codes only, and context after removing target-bearing entries.
* **L2** addresses scale; RareArena's 72,661 cases span 45.6% of Orphanet. Released CC-BY-NC-SA, so we use it for academic evaluation only and acknowledge license bounds.
* **L4** directly answers the data-contamination criticism from the 2026 systematic review. We extract 2,401 PMC OA case reports published after 2024-01-01 via E-utilities filtering on `"Rare Diseases"[MeSH] ∪ "Genetic Diseases, Inborn"[MeSH]` plus `"case reports"[Publication Type]` plus `"pubmed pmc open access"[sb]`, then LLM-extract diagnosis + HPO with Gemini 3 Flash, fuzzy-map to Orphanet, and **manually verify** ~200 cases against four checks (definitive diagnosis, accurate phenotypes, post-cutoff verified, truly rare). Verification protocol and reviewer agreement (Cohen's κ) are detailed in §5 and Appendix D.

**Total v1 evaluation pool: ~85,000 cases / >12,000 diseases**, with stratification on prevalence tier (super-rare < 1/1M, rare 1/2K-1/1M, common-rare ≥ 1/2K), specialty (14 body systems, DeepRare taxonomy), and language (English / Chinese where applicable).

**Evaluation N per dataset — honest disclosure.** We deliberately separate
"pool size" (the released benchmark) from "evaluation N" (what we run for the
v1 paper).
- **RareBench-HF** (1,122 cases) is evaluated at full N. The MIMIC structured
  probe has its own attempted-admission denominator and is reported separately.
- **Large layers** (Phenopacket-Store 10,051; RareArena RDS 72,661): evaluated on
  a **prevalence-stratified random sample of N=500 per agent × backbone cell**
  for primary backbones (seed=42, proportional allocation across prevalence tiers;
  reproducibility receipts released with the benchmark). We do **not** report
  full-N results on these two layers in v1 — extrapolation to 72k cases per cell
  is cost-prohibitive given our 8-agent × 4-backbone matrix (see §9.6 cost
  transparency).
- **DeepSeek V4-Pro and GPT-5** are reported at partial N=100–500 depending on
  cell, with confidence intervals correspondingly wider; cells with fewer than
  N=100 are marked in §6.2 / Table 1 with explicit denominators.

This is a **prevalence-stratified evaluation, not a power-stratified extrapolation
to full pool**; bootstrap CIs in §6 quantify the resulting uncertainty per cell.
We confirmed via our sampling-validation check that the N=500 stratified sample reproduces the full-N
prevalence band and HPO-organ-system distribution within ±2 pp.

### 4.3 Canonical Case Representation

Every dataset ingests into a single Pydantic v2 schema, `CanonicalCase`
(illustrated in the canonical-case figure), and every agent adapter projects
from this representation to the agent's native input. The record groups an
identity block (`case_id`, `source_dataset`, `source_split`, `language`), an
input block (demographics; `free_text_vignette` / `synthetic_vignette`;
`gold_hpo_terms`; `variants`; local `vcf_path`; `family`), a parallel-ID gold
label, and free-form metadata.

Three design decisions deserve note: (a) gold labels are **parallel IDs** (OMIM/ORPHA/CCRD), reflecting genuine ontology disagreement across datasets — Phenopacket-Store uses OMIM, RareArena uses ORPHA, CCRD anchors the Chinese-listed 207 diseases. Evaluator must accept cross-mapped matches via Orphadata (§4.5). (b) `synthetic_vignette` is distinguished from `free_text_vignette` so we can audit any evaluation that relies on LLM-synthesized prose (§7 disclosure). (c) `vcf_path` carries a local-only file pointer; PhysioNet DUA prohibits transmission of identifiable EHR data to external LLM APIs, so adapter shims projecting Pillar 3 inputs convert structured variant info to abstracted strings before any cloud-LLM call.

### 4.4 Dual-pass evaluation

Every pillar is evaluated in two modes. In **Pass A** (gold-HPO, primary) the
case's curated HPO terms are fed directly to the agent's downstream pillar,
bypassing its own extractor — isolating downstream capability and enabling
apples-to-apples comparison on identical inputs. In **Pass B** (end-to-end) the
raw free-text vignette is fed in and the agent extracts HPO itself before
reasoning, measuring real deployment performance. The **Pass A − Pass B delta**
is itself a reported metric (following RareBench's phenotype-vs-EHR-text
comparison [Chen et al., 2024]); we show it is non-uniform across agents
(§7.1), which turns the input heterogeneity of a mixed-agent lineup into a
measured axis rather than a confound (§5.1).

### 4.5 Metrics and matching

We report Recall@1/3/5/10, median rank and MRR for the DDx pillars, P/R/F1 for
phenotype extraction, and task-success rate; a recommended tier (pass\^k,
cost-normalised accuracy, calibration, reference accuracy) and an exploratory
tier (step-level and reasoning-faithfulness scores) are defined in Appendix C.
Every accuracy metric is additionally stratified by six bias axes (genetic
ancestry, prevalence tier, sex, age, language, HPO density). A predicted
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
- Wu et al., MIMIC-RD arXiv 2026 | §4.2
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

- 实际 Figure 1(canonical_case schema 架构图)需要画(mermaid 或 TikZ)
- Figure 2(dual-pass evaluation 流程图)需要画
- Table A1 / A2 / A3 完整版去 appendix(本节 main text 只放精简表)
- §4.2 L4 holdout 200 case 数字会在 final 阶段更新

### Length check

~1,400 words 现在,目标 1.5 page main paper 约 1,800 words。还有 ~400 words 空间。

可以扩的:
- §4.4 加一段双 pass 数学化定义(eg let R@k(Pass A) = ...)
- §4.5 metric taxonomy 加一个小公式 box 显示 Cost-Normalized Accuracy = accuracy / USD-per-case
- §4.2 加一段说明 RareArena CC-BY-NC-SA 跟我们 academic license 的兼容性

或保持现状交 reviewer 由他们 decide。
