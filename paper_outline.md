# Paper Outline — Rare Disease Agent Benchmark (EMNLP submission)

> **Historical planning document.** Numerical placeholders and proposed claims
> below are not the source of truth for the current paper. No OSF registration
> was completed; H1--H11 and A1--A12 are repository-defined, not formally
> pre-registered. Use `paper_sections/` and the frozen manifest for submission
> text and results.

> Target venue:**EMNLP 2026**(8 pages main + unlimited appendix)
> Status:Round 2 实验进行中(Phase 0 done, Phase 1 done, Phase 2 启动)
> Working title 候选(暂定):
> - "RDAgentBench: A Multi-Pillar Benchmark for Rare Disease Diagnostic Agents"
> - "Beyond Accuracy: A Five-Pillar Evaluation of LLM Agents for Rare Disease Diagnosis"
> - "From RareBench to RDAgentBench: Agent-Native Evaluation for Rare Disease Diagnosis"

---

## 0. Narrative Arc(我们到底在讲什么 story)

**核心 thesis**:**Rare disease diagnosis 已经从 single-LLM 时代进到 agent 时代(2024-2026 涌现 8+ 个 agent 系统),但 1 个共享 benchmark 都没有 — 每个 agent paper 自建临时评估集 → 不可比 + 无可复现性 + reviewer 不信。我们建一个 agent-native 评估基座**:

1. 不是 LLM-only 静态 input→output,而是 5 个 capability **pillar**(覆盖 agent 真正的差异化能力)
2. 不是单 dataset,而是 4 layer(curated phenotype + 真 EHR + 大规模 free text + 防污染 holdout)
3. 不是 fuzzy "accuracy" 一刀切,而是 repository-defined 11 个假设 + 12 个 ablation,Holm 校正
4. 关键发现 — preview:
   - **Multi-agent scaffolding 真有效**(MedAgents 0.36 / MDAgents 0.34 vs Gemini Flash baseline 0.26)— 反 MedAgentBoard 2025 的"多 agent 无用"结论
   - **HPO extraction quality 决定 downstream**(LIRICAL R@1 在 gold HPO 上 0.40,LLM-extracted HPO 上 0.04 — 10x 落差)
   - **Reasoning trace 评分有 self-preference bias**(Gemini judge 给 Gemini agent 多 +0.30-0.90,Claude judge 后差距收敛到 ±0.20-0.40)
   - **Accuracy 不充分**:H10 Spearman(faithfulness, accuracy)< 0.5 → 这是我们最强 single argument

**反对的 strawman**:"这就是 RareBench++ / DeepRare paper 已经做了"
**我们的回应**(plan.md §可防御性 5 主张):
1. RareBench 是 LLM 静态 evaluation,我们是 agent interactive evaluation — 范畴不同
2. DeepRare 自建 9 个 ad-hoc dataset,没有 shared benchmark
3. 2026-03 systematic review 独立证实 gap(R²=0.55 prevalence vs R@1,所有 19 个 LLM evaluation 标 high contamination)
4. 我们的 D-class metric(faithfulness)+ pass^k reliability 是新颖具体贡献,不是抽象 framing
5. 中文 layer(`_zh`)+ post-cutoff holdout 是真公平性 / 真复现性贡献

---

## 1. Abstract(~ 220 words)

### 想说什么
- **Hook**(2-3 sentences):rare disease agents 涌现 vs 共享 benchmark 真空
- **What we built**(2-3 sentences):5 pillar × dataset resources × systems/backbones × repository-defined 11 假设 + 12 ablation
- **Key headline numbers**(2 sentences):
  - eg "Multi-agent scaffolding agents (R@1 = 0.36) beat single-LLM controls (0.26) on Pillar 2 across N=X case,but degrade by Y pp under noisy phenotype extraction (Pillar 1 cascade)"
  - eg "Faithfulness ranking is decoupled from accuracy ranking (Spearman ρ = 0.X < 0.5),supporting the claim that accuracy-only evaluation is insufficient"
- **Practical implication**(1 sentence):benchmark + leaderboard + harness 开源
- **CTA**(1 sentence):`github.com/...` + leaderboard URL

### Placeholder template
```
Rare disease diagnostic AI agents have proliferated (8+ systems in 2024-2026),
yet no shared benchmark exists; each agent paper evaluates on an ad-hoc subset,
making cross-system claims unverifiable. We introduce <NAME>, an agent-native
benchmark spanning five capability pillars (phenotype extraction,
phenotype-only DDx, genotype-aware DDx, family-aware DDx,
clinical-communication faithfulness) on a layered dataset (Phenopacket-Store
n=10,051; RareBench 1,122; RareArena 72,661; MIMIC-IV rare-disease slice n=956;
post-cutoff PMC OA holdout n=200). We evaluate 7 agent systems against 3 LLM
no-scaffolding controls and one classical baseline (LIRICAL), with all
hypotheses (H1-H11) and ablations (A1-A12) documented in the repository plan.

Key findings: <NUMBER 1>. <NUMBER 2>. <NUMBER 3>. We release the harness,
canonical case schema, per-agent adapter shims, and a static-site leaderboard
hosting the full 400-cell matrix at <URL>.
```

### 评分要求
- 同行评审 60 秒内能 grasp "what / how / why care"
- 至少 1 个 quantitative finding 在 abstract 里(numerical anchor)
- 不堆术语,不超 5 个 acronym

---

## 2. Introduction(~ 1.25 pages)

### 2.1 The phenomenon(第 1 段,3-4 sentences)

罕见病诊断难题 +(LLM)agent 兴起 — 引 DeepRare(Nature 2026)、MAI-DxO(Microsoft 2025)、MDAgents(NeurIPS 2024)、RareAgents(AAAI 2026)等 — 显示 8+ 系统在不同 ad-hoc setups 上 claim 不同数字。

### 2.2 The gap(第 2 段,4-5 sentences)

3 类 evidence:
1. 我们调研的 9 个 rare disease benchmark 中 **8 个 LLM-only**(plan.md §1 表),零个 agent-native
2. 2026-03 systematic review 独立 validate:跨 19 个 LLM evaluation,所有标 high contamination,无 prevalence stratification,无 agent process metric
3. 每个 agent paper(DeepRare/RareAgents/RDguru)**都自建 evaluation** → claims 不可比

### 2.3 Why agent-native, not LLM++(第 3 段,4 sentences)

Agent benchmark 跟 LLM benchmark 的本质区别:
- 工具使用 evaluation(tool selection / DAG / 调用准确率)
- 多轮 / 信息引出
- 成本与延迟 trade-off
- 推理轨迹忠实度
- 可靠性(pass^k under noise)

引 τ-bench / AgentBoard / SWE-bench 作类比 — code generation 也有"HumanEval(静态)→ SWE-bench(交互式)"的范式转变,我们要给 rare disease 做同样的事。

### 2.4 Our approach(第 4 段,5-6 sentences)

5 pillar × dataset resources × 双 pass(gold HPO vs end-to-end)× 四 backbone × repository-defined H1-H11 + A1-A12。其中 3 个 design decision 单独说:
- 双 pass 评估(plan.md §3)— RareBench Table 6 先例
- Repository-defined hypotheses and multiplicity control; no completed OSF registration
- Cutoff-after PMC OA holdout(自建,200 manually verified case)— 防 contamination

### 2.5 Key findings preview(第 5 段,5 numerical claims)

格式:每个 finding 一行,带数字 + 假设号:

- **F1**:Multi-agent scaffolding 真有效 — MedAgents R@1=0.36 / MDAgents 0.34 vs Gemini Flash baseline 0.26(H4 confirmed for medical reasoning)
- **F2**:HPO extraction quality 是 downstream bottleneck — LIRICAL R@1 0.40→0.04 when fed LLM-extracted vs gold HPO(H8 P1→P2 cascade)
- **F3**:Reasoning trace 评估有强烈 self-preference bias — Gemini judge → Gemini agent 系统性 +0.50;Claude judge 后消除(methodology note)
- **F4**:Faithfulness rank 跟 accuracy rank 解耦(Spearman ρ = <TBD,期望 < 0.5)— H10 confirmed → "accuracy 不够"
- **F5**:Genotype channel 大幅提升 P3(DeepRare HPO-only → HPO+VCF 提升 ~24 pp on Xinhua per their paper;我们复现 <TBD>)

### 2.6 Contributions(第 6 段,bullet list)

1. **Agent-native benchmark** — first shared evaluation base for rare disease agents,5 pillar × 4 dataset
2. **Layered datasets** including self-built **post-cutoff PMC OA holdout**(200 manually verified case)
3. **Repository-defined** H1-H11 + A1-A12; the OSF file is an unregistered draft
4. **Open harness**:canonical_case schema(Pydantic)+ 8 agent adapter shims + 5 metric module(accuracy / phenotype / calibration / reliability / cost)+ Docker image
5. **Empirical findings**:F1-F5 above + per-pillar / per-backbone breakdown

---

## 3. Related Work(~ 0.5 page)

3 段:

### 3.1 Rare disease LLM benchmarks
- RareBench(KDD'24)、RareArena(Lancet Digit Health 2025)、Phenopacket-Store(HGG Adv 2025)、MIMIC-RD(arXiv 2026)、Reese et al.(Eur J Hum Genet 2026)、Chimirri 多语言(eBioMedicine 2025)
- Common gap:LLM-only,静态 input→output

### 3.2 Agent benchmarks(其他领域)
- τ-bench(retail/airline)、AgentBoard、SWE-bench、MedAgentBench(NEJM AI 2025)、MedHELM
- 范式启发:tool-use / pass^k / cost-Pareto

### 3.3 Medical / rare disease agent systems
- DeepRare(Nature 2026,40+ tool, central host)、MAI-DxO(Microsoft 2025,8-role panel)、RareAgents(AAAI 2026,MDT)、MDAgents(NeurIPS 2024,solo↔group adaptive)、MedAgents(ACL 2024)、AgentClinic(MIT/multimodal)、RDMA(arXiv 2025,EHR mining)、PhenoBrain(npj Digital Medicine 2025,classical ensemble — we drop in v1 due to checkpoint availability)、LIRICAL(Robinson lab,classical Java)、VC-RDAgent(offline Poincaré embedding)

引每个时 1 句话其差异化(eg "MAI-DxO operationalizes Microsoft Diagnostic Orchestration with budget-aware test ordering")。

**Differentiation 落点**:既有 rare disease benchmark 缺 agent process metric;既有 agent benchmark(MedAgentBench)缺 rare disease 特异性(prevalence stratification、HPO ontology、Orphanet 跨映射)。我们交集。

---

## 4. Benchmark Design(~ 1.5 pages)

### 4.1 Five Capability Pillars(0.5 page)

| Pillar | What | Input | Output | Key Datasets |
|---|---|---|---|---|
| P1 Phenotype Extraction | EHR text → HPO terms | free-text vignette | HPO ID list | RareArena RDS + Opus 4.7 silver gold(我们自建)|
| P2 Phenotype-Only DDx | HPO terms → ranked disease | HPO list | OMIM/ORPHA ranked top-k | Phenopacket-Store + RareBench + RareArena |
| P3 Genotype-Aware DDx | HPO + variant → ranked disease | HPO + VCF / structured variants | Disease + causative gene | Phenopacket-Store(only layer with structured variants)|
| P4 Family-Aware DDx | + pedigree/MOI | HPO + trio/pedigree | Disease + MOI | v2(MyGene2 / DDD application pending; v1 fold into P3 stratification)|
| P5 Reasoning Faithfulness | trace evaluation | full agent trace | LLM-judge score(4 axes)| Phenopacket-Store n=10 stratified + Claude Sonnet 4.5 judge |

每 pillar 之下说:
- 为什么独立成 pillar(plan.md §可防御性 + 罕见病benchmark方案.md §推荐结构)
- 跟既有 benchmark 的关系(P2 ≈ RareBench Task 4;P3 ≈ DeepRare's headline;P5 是新创)

### 4.2 Datasets — Layered(0.4 page)

4 layer(plan.md / agent_methods.md):
1. **Structured phenotype backbone**:Phenopacket-Store 10,051(GA4GH JSON)+ RareBench HF 1,122(4 splits)
2. **Real EHR noise**:MIMIC-IV rare disease slice 956 例 / 239 disease(ICD→Orphanet 映射 + non-rare 过滤,我们自建)
3. **Scale**:RareArena RDS 49,760 + RDC 22,901
4. **Cutoff-after holdout**:PMC OA pub date ≥ 2024-01-01,LLM 抽 + Orphanet 映射 + 人工核验 200 例(自建,本 benchmark 防 contamination 头号贡献)

Methods 章节会 cite Orphanet 阈值(EU ≤1/2,000)+ OMIM 锚定 + CCRD(中国 207 病目录)。

### 4.3 Canonical Case Representation(0.2 page)

`harness.canonical_case.CanonicalCase`(Pydantic v2):每个 case 是同一 schema,包括 demographics / free_text_vignette / synthetic_vignette / gold_hpo_terms / variants / family / gold_label(OMIM ‖ ORPHA ‖ CCRD)/ metadata。

8 个 agent adapter shim 都从 canonical case 项目到原生输入。**关键 figure**(Figure 2):一张 architecture 图显示 4 dataset → ingest adapter → canonical_case → 8 agent shim → unified PredictionLog。

### 4.4 Evaluation Modes — Dual Pass(0.2 page)

- **gold-HPO pass**(primary):case.gold_hpo_terms 直接喂给 agent,Pillar 1 跳过 — apple-to-apple 对比下游能力
- **end-to-end pass**(secondary):free text → agent 自己 P1 抽 → 下游 — 量化 P1→P2 cascade

**双 pass 之间的 delta 本身是 reportable metric**(RareBench Table 6 先例)。

我们的 Phase 0 V2 已经看到这个 cascade:LIRICAL gold-HPO 0.40 vs end-to-end 0.04 — section 7.1 会展开。

### 4.5 Metric Taxonomy(0.2 page)

A/B/C/D 类 × Tier 1/2/3(`罕见病benchmark方案.md` 二维表)— 复制进 paper appendix。Main text 只列 Tier 1(必报):Recall@k / Median Rank / MRR / HPO P/R/F1 / Gene Top-k(P3 用)/ Task Success Rate。Tier 2 在 Analysis 部分按需 invoke。

---

## 5. Experimental Setup(~ 0.5 page)

### 5.1 Agents(8)
- 2 通用医学:MDAgents、MedAgents、AgentClinic、MAI-DxO(× 3)= 4
- 罕见病专用:DeepRare、RDMA、VC-RDAgent = 3
- 经典 non-LLM:LIRICAL = 1
- LLM no-scaffolding controls:DeepSeek V3.2、GPT-5(reasoning_effort=minimal)、Gemini 3 Flash Preview = 3

**Table:Agent Fairness Matrix**(plan.md §3)— 列每个 agent 的(原生输入格式 / 我们的 adapter / 保持恒定的 backbone temp/max_token/retry / 任何 deviation)。

### 5.2 Backbones(3)

| Alias | OpenRouter ID | Price ($/M in-out)| Use |
|---|---|---|---|
| Cheap | deepseek/deepseek-v3.2-exp | 0.27 / 1.10 | Primary backbone for adapter cost A/B |
| Mid | google/gemini-3-flash-preview-20251217 | 0.50 / 3.00 | Primary baseline + LLM judge alt |
| Frontier | openai/gpt-5(`reasoning_effort=minimal`)| 1.25 / 10.00 | Frontier ceiling |

**Methods note**(reviewer-defensive):GPT-5 默认 reasoning_effort 把 max_tokens=6000 全吃光导致 content=null;**我们显式设 minimal**(论文 footnote 实验数据)。同时 GPT-5 reasoning on/off 是 H6 假设的轴。

### 5.3 Per-Agent Adapter Shim Methodology

每个 agent 是 subprocess + venv 隔离调用 — 防 openai SDK pre-1.0 跨 agent 冲突。adapter 接受 canonical_case,projection 到 agent 原生格式,subprocess 跑,parse 输出回 PredictionLog。3,485 LOC 全开源(`harness/agents/`)。

### 5.4 Repository analysis plan

H1-H11 + A1-A12 + 统计协议记录在 repository；OSF 文件未完成注册，论文不得声称 prospective pre-registration。

---

## 6. Main Results(~ 1.5 pages)

### 6.1 Table 1 — Pillar-First Headline(8 agent + 3 control 行 × 5 pillar 列 + Avg)

格式参考 plan.md §2 / AgentBoard Table 3。每个 cell 是跨 4 dataset 的均值 R@1(P1 用 F1)。最优粗体 / 次优下划线(RareBench Table 4 convention)。

### 6.2 Table 2 — Main Metric × Dataset(同 20 行 × 4 dataset + Avg)

cell = Pillar 2 Recall@1(我们的 headline metric,等价 RareBench)。τ-bench Table 2 convention。

### 6.3 Figure 1 — Heatmap

agent × (dataset × pillar)20 × 20 cell 格子,颜色编码 R@1。MedHELM Figure 3 convention。

### 6.4 Figure 2 — Radar / Polar(5 pillar 轴)

3-5 个 top agent 叠加。AgentBoard convention。

### 6.5 Figure 3 — Cost-vs-Accuracy Scatter

每个(agent, backbone)一标记,Pareto 前沿描线。BFCL/HELM convention。

### 6.6 Figure 4 — Specialty Stratified Bar

14 个 body system(DeepRare 分类法)各自一柱。

### 6.7 Web leaderboard

`<URL>` 托管完整 400-cell 矩阵 + per-disease breakdown(论文 appendix 太大放不下)。

---

## 7. Analysis(~ 1.5 pages)

5 个 subsection,每个 0.3 页,锚定 H1-H11:

### 7.1 P1 → P2 Cascade(H8 phenotype density + 我们新发现)
LIRICAL R@1:gold HPO 0.40 vs LLM-extracted 0.04 → 10x 落差。VC-RDAgent 类似(0.32 vs 0.04)。**论文卖点**:HPO extraction quality 是 downstream bottleneck,end-to-end deployment 必须先解 P1。

### 7.2 Scaffolding Pays(H4)
MedAgents 0.36 / MDAgents 0.34 ≥ Gemini Flash baseline 0.26。**但 AgentClinic 0.20 < baseline** — 不是所有 scaffolding 都 helpful;OSCE-style dialogue 在 HPO-only case 上 over-engineer。条件 H4。

### 7.3 Genotype Channel(H2)
DeepRare(when bug fix v3 done)P3 HPO-only vs HPO+VCF — 期望 ≥20 pp gain。其他 non-genotype agent 在 P3 上 ≈ 等于 P2(no improvement)— support H2 specialized > generalist。

### 7.4 Faithfulness vs Accuracy(H10,headline finding)
Spearman ρ(Pillar 5 faithfulness rank, Pillar 2 accuracy rank)= <TBD>。期望 < 0.5。**这是 paper 最强 single argument**:accuracy-only 不够。配 figure:rank correlation scatter。

### 7.5 Self-Preference Bias(methodology contribution)
Gemini Flash judge 给 Gemini agent 系统性 +0.30-0.90 per axis(P5 v1)。**Switch to Claude Sonnet 4.5 judge 后**消除大部分:llm_control 4 axes margin 从 {+0.30, +1.00, +0.40, +0.90} → {+0.20, +0.33, **-0.39**, +0.24}。**支撑 A12 LLM-judge ablation** + 给 LLM-judge methodology 社区一个新 cautionary tale。

---

## 8. Ablations(~ 1 page)

A1-A12 选 6-8 个在 main text(剩 appendix)。Priority:

| Ablation | Main text? | Why |
|---|---|---|
| A1 DeepRare modules | yes | Independently replicates DeepRare's own claims |
| A2 Multi-agent depth | yes | Tests H4 mechanism |
| A3 Backbone × scaffolding 2×N | yes | reviewer 最常要求的 |
| A5 Reasoning-mode on/off(GPT-5 minimal/low/high)| yes | H6 |
| A6 Pre/post-cutoff split | yes | Headline contamination defense |
| A8 Input format(gold HPO / agent-extracted / free-text)| yes | Pillar dual-pass 明示 |
| A11 Cost-cap sweep | yes(figure)| MAI-DxO budget mode 现成 |
| A12 LLM-judge vs exact match | yes | Defends evaluation methodology |
| A4/A7/A9/A10 | appendix | Supporting |

每个 ablation 一段 + 一个小 table 或 forest plot。

---

## 9. Limitations + Future Work(~ 0.5 page)

直接 anticipate reviewer attack(plan.md §6 锁定的 10 个):
1. Data contamination — A6 covers
2. Heterogeneous-agent fairness — Agent Fairness Matrix in §5.1
3. Missing fine-tuned medical LLM baseline — note as future
4. Statistical rigor — Holm-Bonferroni + bootstrap CI documented
5. MIMIC ICU bias — 4-layer stack
6. English-centric — Chinese layer was deferred(v1),acknowledge
7. Arbitrary agent selection — inclusion criteria documented and disclosed
8. Multi-agent doesn't always help — exactly what H4 reports
9. Cost not clinically meaningful — 3 cost axes 不混淆
10. LLM-judge unreliable — A12 + Claude judge methodology + physician validation 200 case κ
11. Model version changes silently — dated backbone aliases + Docker image
12. Over-claiming — frame as retrospective decision support,not autonomous diagnosis

Future work:
- Pillar 4 升级(MyGene2 / DDD 申请到位后)
- 中文 layer 扩展(PUMCH-ADM 申请)
- Fine-tuned medical LLM(Meditron-70B、OpenBioLLM-70B)加入 lineup
- Multimodal pillar(imaging / pathology)
- 真临床部署 study(prospective)

---

## 10. Conclusion(~ 0.25 page)

简短 wrap:gap → benchmark → headline findings F1-F5 → release。重述 thesis:"accuracy 不够,5 pillar 必须并行评估,未来 confirmatory study 应 prospective registration"。CTA。

---

## 11. Appendix(unlimited)

- A. Full per-cell matrix(400 cell)
- B. Per-agent adapter shim 设计 + patch list(8 RUN_REPORT 内容)
- C. Prompts(every agent 主 prompt + LLM judge rubric)
- D. Contamination audit(TS-Guessing scores + n-gram overlap)
- E. Bootstrap CI per metric
- F. Per-disease breakdown(top-50 disease × per agent R@1)
- G. Specialty stratified detail(14 body system)
- H. Prevalence-tier stratified(super-rare / ultra-rare / rare)
- I. Per-language analysis(EN / ZH if applicable)
- J. Cost breakdown per (agent, backbone, pillar)
- K. Latency / pass^k distribution
- L. Unregistered OSF analysis-plan draft (clearly labelled)
- M. Responsible NLP checklist
- N. Reproducibility statement + Docker image hash
- O. License clarifications(per agent — note 4 agents lack LICENSE)

---

## 12. Figures and Tables Master List(便利施工)

| Item | Section | Status |
|---|---|---|
| Figure 1: Architecture | §4.3 | Needs to draw |
| Figure 2: Heatmap agent × dataset×pillar | §6.3 | After Phase 4a |
| Figure 3: Radar 5-axis | §6.4 | After Phase 4a |
| Figure 4: Cost-Pareto | §6.5 | After Phase 4a |
| Figure 5: Specialty bar | §6.6 | After Phase 4a |
| Figure 6: P1→P2 cascade scatter | §7.1 | Phase 0 V2 data ready |
| Figure 7: Faithfulness vs accuracy rank | §7.4 | After Phase 4a + P5 v2 |
| Figure 8: Self-preference bias delta | §7.5 | **Phase 1 data ready ✅** |
| Figure 9: Cost-cap sweep | §8 A11 | Phase 5 |
| Figure 10: pre/post-cutoff drop | §8 A6 | After holdout unblind |
| Table 1: Pillar-first headline | §6.1 | After Phase 4a + ablations |
| Table 2: Main metric × dataset | §6.2 | After Phase 4a |
| Table 3: Agent Fairness Matrix | §5.1 | **Can draft now** |
| Table 4-N: per-ablation small tables | §8 | Phase 5 |

---

## 13. Writing Order(我的 suggested writing order — minimize block on data)

不要按 §1→§12 顺序写,而是按数据 ready 顺序:

1. **§5.1 Agent Fairness Matrix**(数据全有)— 最先写
2. **§4 Benchmark Design**(plan / methods 都成熟)— 第二
3. **§3 Related Work**(调研已经在 罕见病benchmark方案.md)— 第三
4. **§7.5 Self-Preference Bias methodology**(Phase 1 v2 数据 ready)— 早写一段
5. **§7.1 P1→P2 cascade**(Phase 0 V2 数据 ready)— 早写一段
6. **§2 Introduction**(等 main results 出后回写)
7. **§6 Main Results**(blocked on Phase 4a)
8. **§7.2/7.3/7.4 Analysis**(blocked on Phase 4a + ablations)
9. **§8 Ablations**(Phase 5)
10. **§1 Abstract** + **§9 Limitations** + **§10 Conclusion**(最后)
11. **§11 Appendix**(全程并行)

---

## 14. Style Notes

- **不用任何 emoji** in paper text(EMNLP convention)
- 数字 ≥ 4 位数加 thousand separator(`10,051` not `10051`)
- 第一次出现 acronym 必须展开:`Recall@1 (R@1)`
- 不 cherry-pick — 任何 finding 报 bootstrap 95% CI
- 不夸大 — 论文里"agents"指 LLM-based 系统,LIRICAL 称"classical baseline"
- “Repository-plan”标记 H/A finding；exploratory 与 post-hoc 分析显式区分
- 不指责 single LLM controls 是 strawman — 论文用最强 LLM control(reasoning-enabled GPT-5 + Gemini Flash + DeepSeek V3.2,三个齐上 + few-shot 选项 A7)
- LIMITATIONS 部分 honest 列短板 — 包括 PUMCH-ADM 中文 layer 没拿到 + DDD pending + P1 silver gold 100 case 小

---

## 15. Open Questions / Decisions Still Needed

- [ ] **Working title** finalize — 3 候选投票
- [ ] **Author order + affiliations** — 等用户定
- [x] **OSF status** — no registration exists; disclose the bundled draft as unregistered
- [ ] **GitHub repo URL** — release tag v0.1.0 at submission
- [ ] **Web leaderboard URL** — host where?(GitHub Pages 默认)
- [ ] Phase 4a 结果定后,确认 headline findings 数字
- [ ] Phase 5 ablation 12 个跑完后,确认哪 6-8 个进 main text
- [ ] Camera-ready / journal extension 是否做 PUMCH-ADM 中文层 + DDD trio

---

## 16. Submission Logistics(EMNLP)

- Deadline check:EMNLP 2026 主 deadline + ARR cycle 节奏
- Page limit:**8 pages main + unlimited references + unlimited appendix**
- Format:EMNLP 2026 LaTeX template
- Anonymity:double-blind during review — code repo 改 `anonymous-RDAgentBench`
- Responsible NLP checklist:必填
- ARR 选项 vs direct submission — TBD

---

**Status as of 2026-05-16**:Phase 0/1 done,Phase 2 starting after DeepRare/maidxo bug fix。Paper outline draft 完成。每节 placeholder 标 status,下一步 §5.1 Agent Fairness Matrix 可以马上 draft(数据 ready)。
