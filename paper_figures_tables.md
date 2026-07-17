# Paper Figures & Tables — Design Spec

> 用途:每个 figure / table 一个 entry,描述要表达什么、怎么画、状态、依赖哪些数据。等实验结果出来按 status 填。
> 关联文档:`paper_outline.md` §12 / `paper_sections/*.md`

---

## 0. 全局原则

- **Every figure 必须有 take-home message in 1 sentence**(写在 caption 第一句)
- **Color-blind safe palette**:用 ColorBrewer "Set2" 或 viridis,不用纯红绿
- **黑白 print readable**:形状区分(circle / square / triangle / cross)+ pattern 区分(solid / dashed / dotted)
- **Caption self-contained**:reviewer 不读正文也能看懂(包括 N、单位、统计 detail)
- **Numbers 在 figure 上读得到**:R@k 数字直接标在 bar/dot 上,不只是 color
- **EMNLP 双栏**:figure 默认单栏宽(~3.3 inch); double-column figure 仅在 必要时(eg heatmap)用 figure*
- **统一 typography**:Helvetica/Arial 8-9pt,与 EMNLP body 一致

---

## 1. Figures(主文 ~6-8 + appendix 多)

### Figure 1 — Benchmark Architecture(§4.3)

**Message**:4 dataset layer → canonical_case schema → 8 agent adapter shim → unified PredictionLog → metric library.

**Draw**:
```
┌─ Dataset Layer ────────┐    ┌─ Ingest ──┐    ┌─ Canonical ──┐    ┌─ Adapter ──┐    ┌─ Metric ──┐
│ Phenopacket-Store      │ ─→ │ adapters  │ ─→ │ CanonicalCase│ ─→ │ 8 agent    │ ─→ │ R@k       │
│ RareBench (4 splits)   │ ─→ │ per       │    │ (Pydantic v2)│    │ shims      │    │ MRR       │
│ RareArena (RDS+RDC)    │ ─→ │ dataset   │    │              │    │ subprocess │    │ Brier     │
│ MIMIC-IV slice (956)   │ ─→ │           │    │              │    │ isolation  │    │ pass^k    │
│ PMC OA holdout (200)   │ ─→ │           │    │              │    │            │    │ cost      │
└────────────────────────┘    └──────────┘    └──────────────┘    └────────────┘    └───────────┘
```

**画法**:`graphviz` 或 `tikz`(LaTeX 原生)或 Inkscape SVG。3.3 in 单栏即可。
**Status**:架构清晰,可直接画。**Today can draft**。

### Figure 2 — Dual-Pass Evaluation Flow(§4.4)

**Message**:Pass A (gold-HPO) vs Pass B (end-to-end);Delta 本身是 metric。

**Draw**:左右两个 swimlane,Pass A 直 short path,Pass B 多 stage,两条 path 末端汇到同一 PredictionLog。

**Caption**:"Dual-pass evaluation. Pass A feeds canonical gold HPO directly to the downstream pillar (P2-P5), isolating capability. Pass B routes the free-text vignette through the agent's own Pillar 1 module, measuring end-to-end deployment performance. The Pass A − Pass B delta on the same agent quantifies P1 sensitivity (§7.1)."

**Status**:可马上画。

### Figure 3 — Pillar-First Headline Heatmap(§6.3)

**Message**:同时呈现 8 agent × 4 dataset × 5 pillar 全貌。

**Draw**:rows = 11 (agent × backbone),cols = 20 (4 dataset × 5 pillar);cell color = R@1 normalized;numbers on cells。
- 用 `seaborn.heatmap`,`cmap="viridis"`,`annot=True, fmt=".2f"`
- 行按 R@1 平均降序;backbone 内按 agent 字母序
- 列按 dataset 分组 + 内部 P1→P5

**Caption**:"Headline heatmap. Each cell is Recall@1 on the corresponding (agent, dataset, pillar) cell; LIRICAL only emits P2/P3 so other cells are gray. **Rows sorted by per-agent mean across all pillars.** Bootstrap 95% CIs are in Table A?"

**Status**:**Blocked on Phase 4a data**(100 case per dataset × 8 agent × 3 backbone)。

### Figure 4 — Radar / 5-Pillar Polar(§6.4)

**Message**:Top-5 agent 在 5 pillar 上的能力 profile,看哪个 agent 是 generalist 哪个是 specialist。

**Draw**:5 轴 polar plot,3-5 个 top agent 叠加(不同 color + marker)。每轴是 normalized score 0-1。

**Caption**:"Capability radar across five pillars. Top-5 agents by overall R@1 shown; each axis is the agent's score on that pillar normalized to the best across all systems. **DeepRare specializes in P3 (genotype-aware)**; MedAgents is most generalist."

**Status**:Blocked on Phase 4a。

### Figure 5 — Cost-vs-Accuracy Pareto(§6.5)

**Message**:Cost-Pareto 前沿 — 哪些(agent, backbone)是非 dominated 选择。

**Draw**:scatter,x = log USD per case,y = R@1。每(agent, backbone)一个 marker (shape = agent, color = backbone)。Pareto 前沿用线连。

**Caption**:"Cost-vs-accuracy Pareto frontier. Each marker is one (agent, backbone) combination. **LIRICAL ($0, R@1=0.22) dominates the lower-left corner** as the cheap classical baseline. **Gemini 3 Flash + MedAgents at R@1=0.36 / $0.005 per case is the LLM Pareto winner.** GPT-5-based DeepRare's $0.X/case lies above the frontier (dominated by cheaper alternatives)."

**Status**:Blocked on Phase 4a。 BFCL / HELM / ToolLLM 已用同款 figure,reviewer 熟悉。

### Figure 6 — Specialty-Stratified Bar(§6.6,DeepRare-style)

**Message**:每 agent 在 14 个 body system 上的表现 — 暴露 systemic weak specialty。

**Draw**:grouped bar chart,x = 14 body systems(DeepRare 分类法),y = R@1。组内是 4-6 个 top agent + baseline。

**Caption**:"Per-specialty stratified Recall@1. The 14 body systems follow DeepRare's classification. **All agents are weakest on Lungs/Breathing (mean R@1 ≈ X) and strongest on Endocrine / Hematology (≈ Y)** — supporting Hypothesis 7 that failures cluster by specialty across agents (Spearman ρ ≥ 0.6) implying shared dataset/ontology gaps rather than agent-specific blind spots."

**Status**:Blocked on Phase 4a + per-disease metadata。

### Figure 7 — P1 → P2 Cascade Scatter(§7.1)

**Message**:**Headline finding F2**:HPO extraction quality decides downstream — 10× gap in LIRICAL's R@1 between gold and LLM-extracted HPO.

**Draw**:scatter,x = Pillar 1 F1(LLM-extracted vs gold),y = Pillar 2 R@1。每 agent 一个 marker。也叠加 LIRICAL gold vs end-to-end 的箭头。

**Caption**:"P1→P2 cascade. **Agents fed gold HPO (open markers) achieve 0.20-0.40 R@1; agents fed LLM-extracted HPO (filled markers, same agent) drop by 0.10-0.36.** LIRICAL collapses most (0.40 → 0.04, **10× degradation**) because its Bayesian P/L ratios cannot recover from upstream HPO mismatches. RDMA (HPO-extraction specialist) shows the smallest gap (0.32 → 0.21)."

**Status**:**Phase 0 V2 数据 ready** — 可马上画 preliminary 版本。

### Figure 8 — Self-Preference Bias Forest Plot(§7.5)

**Message**:**Methodology contribution**:LLM judge backbone 选择决定 ranking outcomes。

**Draw**:4 个 axes(factual / relevance / depth / faithful),每个 axis 上 4 个 agent(llm_control / mdagents / deeprare / maidxo)。每个 agent 两个 marker:Gemini judge(triangle)vs Claude judge(circle)。连线显示 v1 → v2 shift。

**Caption**:"Self-preference bias in LLM-as-judge. With **Gemini Flash judge (v1)**, the single-Gemini-Flash agent (`llm_control`) scores systematically higher than scaffolded agents (+0.30 to +1.00 across 4 axes). Switching to **Claude Sonnet 4.5 judge (v2)** with identical traces shrinks the gap to ±0.20-0.40 — **mdagents now beats `llm_control` on depth (3.49 vs 3.10)**. This supports Ablation A12: LLM-judge methodology must use non-family backbone."

**Status**:**Phase 1 P5 v1→v2 数据 ready** — 可马上画。最强 methodology 卖点,确保 main text。

### Figure 9 — Cost-Cap Sweep(§8 Ablation A11)

**Message**:MAI-DxO `budgeted` mode 在 cost cap 改变下的 R@1 弧线。

**Draw**:line plot,x = cost cap USD per case,y = R@1。可叠加多 backbone 不同颜色。

**Caption**:"MAI-DxO budgeted-mode cost-cap sweep. At cost cap $0.10 per case, R@1 drops to X; at $2 cap, R@1 plateaus near Y. **The cap value at which 95% of unconstrained performance is recovered is $Z.** This operationalizes A11 ablation."

**Status**:Blocked on Phase 5 ablation A11 run。

### Figure 10 — Pre/Post-Cutoff Differential Drop(§8 Ablation A6)

**Message**:**Headline finding** — data contamination 对哪些 agent 影响大。

**Draw**:每 agent 两根 bar:pre-cutoff R@1(L1-L3 数据)vs post-cutoff R@1(L4 holdout)。Delta 是 contamination 估计。

**Caption**:"Pre vs post-cutoff Recall@1 differential. Pre-cutoff uses the L1-L3 datasets (PhenoPacket-Store + RareBench + RareArena pre-2024 subsets); post-cutoff uses the 200-case PMC OA holdout (pub date ≥ 2024-01-01). **Tool-using agents (DeepRare, MAI-DxO) show smaller drops (3-8 pp); parametric LLM controls drop X pp**, supporting Hypothesis 3."

**Status**:Blocked on PMC holdout 200 case manual review + Phase 4a。

---

## 2. Tables(主文 ~3-4 + appendix 很多)

### Table 1 — Pillar-First Leaderboard(§6.1)

**Message**:每个 agent × 5 pillar 的 R@1(or 主 metric),across 4 dataset 平均。

**Schema**:
```
| Agent (backbone)      | P1 F1 | P2 R@1 | P3 R@1 | P4 R@1 | P5 mean | Avg | Cost |
|-----------------------|-------|--------|--------|--------|---------|-----|------|
| MedAgents (Flash)     |  ...  |  ...   |  ...   |  ...   |   ...   | ... | ...  |
| ... 20 rows total ... |       |        |        |        |         |     |      |
```

- 行 = 11 agent × 3 backbone = up to 30 rows;v1 用 8 agent × 3 backbone = 24
- 每 cell 最优粗体,次优下划线(RareBench Table 4 convention)
- 行按 Avg 列降序

**Status**:Blocked on Phase 4a。

### Table 2 — Main Metric × Dataset(§6.2)

**Message**:agent × dataset matrix(Pillar 2 R@1)— 看 dataset-specific 表现。

**Schema**:
```
| Agent (backbone)   | PhenoP | RareBench | RareArena | MIMIC-IV | Holdout | Avg |
|--------------------|--------|-----------|-----------|----------|---------|-----|
| ...                |  ...   |   ...     |   ...     |   ...    |   ...   | ... |
```

**Status**:Blocked on Phase 4a。

### Table 3 — Agent Fairness Matrix(§5.1)

详见 `paper_sections/5_1_agent_fairness_matrix.md` 已 drafted。

**Status**:**Drafted ✅**。数据全 ready。

### Table 4 — Pre-registered Hypothesis Test Results(§8 final)

**Message**:H1-H11 每个一行,test 类型 + effect size + p value(Holm 校正)+ confirmed/refuted。

**Schema**:
```
| H  | Description                                       | Test           | Effect | p(Holm) | Verdict   |
|----|---------------------------------------------------|----------------|--------|---------|-----------|
| H1 | Recall@1 monotonic in prevalence tier             | Spearman ρ     | -0.X   | 0.0X    | Confirmed |
| H2 | Specialized agents > general on Pillar 3          | paired bs      | +20pp  | 0.0X    | Confirmed |
| H4 | Multi-agent ≤ single-LLM on simple cases          | two-way ANOVA  | +X pp  | 0.0X    | Partial   |
| ...|
```

**Status**:Blocked on all Phase 4 + Phase 5。

### Table 5 — Ablation Summary(§8 A1-A12)

**Message**:每 ablation 一行,key finding 一句话 + 数字。

**Status**:Blocked on Phase 5。

---

## 3. Appendix Tables(numerous)

| Tag | Content | When ready |
|---|---|---|
| Table A1 | Existing rare-disease benchmark survey (11 rows) | Now |
| Table A2 | Per-dataset full schema + license + access | Now |
| Table A3 | Metric Taxonomy 3×4 grid (Tier × Class) | Now |
| Table A4 | Per-agent adapter shim full detail | Now |
| Table A5 | Per-disease breakdown (top 50 ORPHA × agent R@1) | Phase 4a |
| Table A6 | Per-language metrics(EN / ZH if applicable) | Phase 4a |
| Table A7 | Bootstrap 95% CI for every reported metric | Phase 4a |
| Table A8 | Full per-cell matrix (400 cells from Phase 4a + 100 holdout) | Phase 4a+4b |
| Table A9 | Contamination audit(TS-Guessing + n-gram)| Pre-Phase 4 |

---

## 4. Status Summary(at 2026-05-16)

**Data ready,可马上画**:
- Figure 1 (Architecture)
- Figure 2 (Dual-Pass Flow)
- Figure 7 (P1→P2 cascade preliminary)
- Figure 8 (Self-Preference Bias forest plot)
- Table 3 (Agent Fairness Matrix)
- Table A1-A4

**Blocked on Phase 4a/4c**:
- Figure 3-6 (heatmap, radar, Pareto, specialty)
- Figure 10 (pre/post-cutoff)
- Table 1, 2 (main results)
- Table A5-A8

**Blocked on Phase 5 ablations**:
- Figure 9 (cost-cap sweep)
- Table 4, 5

**Blocked on PMC holdout manual review**:
- Figure 10 (pre/post-cutoff drop)
- Holdout-specific A6 ablation

---

## 5. Drawing Tooling

- **Python**:`matplotlib` + `seaborn`(for heatmap / scatter / bar)
- **Polar / radar**:`matplotlib.projections.polar`
- **Forest plot**:`seaborn.PointPlot` or custom
- **Architecture / flow**:`graphviz` Python API → `.dot` → PDF;或 LaTeX TikZ 原生
- **Statistical lines / error bars**:`scipy.stats.bootstrap` for CI,`matplotlib.errorbar`

Output:
- vector PDF for paper(EMNLP latex accepts PDF figures)
- PNG 副本 for slides / repo README
- Source `.py` checked into `paper_figures/` for reproducibility

---

## 6. 风格 cross-check

- 所有 agent / metric 名字与 main text 一致(eg `MedAgents` not `Med-Agents`)
- 所有数字格式一致(2 decimal R@k, 3 decimal MRR)
- 所有 figure 都有 `caption first sentence = take-home message` rule
