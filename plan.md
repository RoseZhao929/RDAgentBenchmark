# 罕见病 Agent Benchmark 实验执行 Plan：默认并行设计

## 1. 执行答案：5 个 Pillar 能完全并行吗？

**部分能，答案取决于一个设计决策：用源数据集的 gold-standard HPO 输入，还是把每个 agent 自己的 Pillar 1 抽取串接到下游 pillar。** 如果采用 **RareBench 惯例** — 把表型抽取（Pillar 1）当作一个单独评估的任务，把 **gold HPO**（Phenopacket-Store、RareBench 子集、RareArena 都已提供）喂给 Pillar 2–5 — 那么**一旦共享基础设施就位，Pillar 1、2、3、4、5 互相独立，可真正并行**。这是罕见病领域的主流做法，也是 DeepRare、RareBench、PhenoBrain 实际在做的。如果反过来把每个 agent 自己抽取的表型串接到它自己的下游流水线（"端到端"评估），那 Pillar 2/3/4 就变成**以每个 agent 自己 Pillar 1 的输出为条件**，出现了串行约束。

推荐的设计是**两个 pass 都做**：完全并行的 "gold-HPO" pass 给出每个 pillar 干净的对比，再加上串行的"端到端" pass，传播 Pillar 1 的错误并量化不完美抽取的代价。这种双评估直接镜像 RareBench Table 6 在相同模型上对比 phenotype-input vs EHR-text-input 的做法，是回应"格式异质性不公平"reviewer 攻击的最干净防御。

本文后续每个下游设计选择都锚定到 HELM、MedHELM、AgentBoard、τ-bench、SWE-bench、BFCL、ToolBench、RareBench、DeepRare、MedAgentBench、MedAgentBoard、AgentClinic、MedR-Bench、MDAgents、MedAgents、MAI-DxO、RDMA、PhenoBrain 的实际做法。

---

## 2. Benchmark 论文组织模式（问题 1）

**10 × 4 × 2 × 5 = 400 个 cell 的矩阵是正常的 — 但没有任何主流 benchmark 论文把它呈现为单一表格。** 每篇论文都把它拆解为少量 headline table、2–3 个 signature 图、加上一个 leaderboard 或 appendix 装原始矩阵。你应该采用的主流惯例有四个要素。

### 把 agent × backbone 折叠为行，不作为独立维度

**我们调研的每个 agent benchmark 都把 (agent, backbone) 当作单一行标识**，不是单独的列维度。τ-bench 用 `gpt-4o (FC)`、`gpt-4o (ReAct)` 标行；SWE-bench Table 5 把 `Claude 3 Opus`、`SWE-Llama 7b` 等列为行；ToolLLM 用 `Claude2-DFSDT`、`GPT4-ReAct`。AgentBoard 按家族（专有 / 开放权重通用 / agent 微调）给行标签上色。对你的 benchmark 来说意味着 **20 行**（10 agent × 2 backbone），按 backbone 边界用横线视觉分组，每组内按头条 metric 排序。这是文献中最一致的惯例。

### 论文主体两张 headline table，不是一张

实证模式是**一张 master table + 3–6 张分析图 + leaderboard URL**。AgentBoard (Table 3)、τ-bench (Table 2)、MedHELM (Table 1)、MMLU 都收敛到这个。对你的矩阵，最干净的拆法：

- **Table 1 — Pillar-first headline**：行 = 20（agent × backbone），列 = 5 个 pillar + 右侧的 `Avg.` 列，每个 cell 是跨 4 个 dataset 的均值。这让 5-pillar 贡献成为一等公民，匹配 MedHELM 按类别分桶的 Table 1。列最优加粗、次优加下划线（RareBench Table 4 惯例）。
- **Table 2 — 主 pillar 在数据集上的分布**：行 = 同样的 20，列 = 4 个 dataset + `Avg.`，cell = *最重要的*那个 pillar metric（Pillar 2 仅表型 Recall@1 是自然选择 — 它是罕见病版的 SWE-bench "% Resolved"）。匹配 τ-bench 的 Table 2（retail / airline / avg）和 AgentBoard 的 Table 3 分组任务列。

置信区间、per-dataset × per-pillar 完整分布、per-disease 数字进 appendix — 这正是 AgentBoard 做的（CI 在 Appendix D），也是 HELM 大规模做的（原始矩阵放网站，论文里只放图）。

### 3–4 张 signature 图压缩维度

每篇主流论文都有 1–2 张 signature 图，工作就是把高维矩阵压缩到读者能在 30 秒内抓到的东西。实证成功的做法：

- **Heatmap**，agent × (dataset × pillar) — MedHELM Figure 3 的做法；适合你 20 × 20 cell 的格子，颜色编码分数。
- **Radar/极坐标图**，覆盖 5 个 pillar，3–5 个顶级 agent 叠加 — AgentBoard Figure 1 / §4.4 显式对它的子技能轴这么做，5 个轴是 radar 可读性的甜区。
- **Cost-vs-accuracy 散点图**，每个 (agent, backbone) 一个标记，高亮 Pareto 前沿 — BFCL 的标志性可视化，HELM 和 ToolLLM (Figure 2) 也用。对包含 MAI-DxO 成本感知 orchestration 的 benchmark 至关重要，匹配领域对效率日益增长的关注。
- **分层柱状图**，按专科或复杂度看性能 — DeepRare Figure 3（14 个身体系统）是范本；这也是患病率层和"# specialists"分层可视化的位置。

### Web leaderboard + appendix 是原始矩阵的家

HELM、BFCL、SWE-bench、τ-bench 全都维护公开 leaderboard 托管完整 per-cell 数字矩阵；论文里只放图和 headline table。对 EMNLP 投稿来说，**在投稿时就发布一个 static-site leaderboard** — 现在已经是预期的可复现性产物，也让你能指向原始矩阵给 reviewer 看而不臃肿 appendix。Appendix 仍然应该包含三张完整分布表（agent × pillar × dataset、完整 bootstrap CI、per-disease 性能），满足那些不点链接的 reviewer。

### 要避免的

20 × 40 的单体表格在 EMNLP 单列格式下不可读 — 调研过的论文没有这么做的。跨异质 pillar 的未加权均值会引来批评（BFCL 因此被质疑过）；**同时报告未加权均值和 normalized win-rate**（HELM/MedHELM 惯例），让任何一种聚合都不会被单独攻击。Radar 图叠加 5 个以上就不可读了；上限 5 个，数字放 appendix。

---

## 3. 输入异质性处理（问题 2）

**罕见病 agent 论文的标准做法是"内部 adapter shim"模型，不是"每个 agent 用自己原生格式"模型。** DeepRare、VC-RDAgent、RDMA 都把异质输入（自由文本、HPO、VCF）包在 agent 内部规范化。RareBench 走了互补路线：把 HPO 固定为**规范输入**，把 free-text 到 HPO 的转换当成**一个独立 benchmark 任务**（Task 1，GPT-4 的 F1 也只有约 0.245 — 故意暴露的薄弱点）。

对你的 benchmark，可防御的方法设计有三层。

**第一，定义单一规范案例表示**：一个 phenopacket 风格的结构化对象，包含 (a) 自由文本 vignette、(b) gold HPO 词项列表、(c) 可选 VCF、(d) 可选家族/pedigree、(e) demographic 字段。每个数据集在 ingest 时规范化到这个对象一次。匹配 MedAgentBench 的 FHIR 规范化做法。

**第二，为每个 agent 写一个发布的 adapter shim**，把规范对象投影到那个 agent 原生期望的输入格式。Adapter 是 artifact 发布的一部分（Docker image + 代码）、被审查、跨数据集一致。每个 agent 的 adapter 都记录在 "Agent Fairness Matrix" appendix table 里：原生输入格式、什么保持恒定（backbone、temperature、max tokens、retry 策略）、作者默认配置、任何偏差。DeepRare 论文显式把它的中央 host backbone 跨所有对比保持恒定；copy 这个惯例。

**第三，跑双 pass 评估**：

- **Gold-HPO pass（主）**：把 gold HPO 列表喂给每个 agent（尽可能跳过它内部的抽取器）。这隔离了下游诊断能力，是 apples-to-apples 对比。
- **End-to-end pass（副）**：把原始自由文本 vignette 喂给每个 agent，让它自己抽取表型。这是真实部署的样子，量化了不完美抽取的代价。

**两个 pass 之间的 delta 本身就是可报告的 metric** — RareBench Table 6 有效地做了这个（PUMCH GPT-4 上 phenotype input 0.520 hit@1 vs EHR-text 0.453），成为论文最被引用的发现之一。Reviewer 会接受这个设计，因为它把异质性问题从混淆变量转化为评估轴。

**捍卫 method 部分**：引 RareBench Table 6 作为直接先例；引 DeepRare 的 MCP 启发的 adapter 架构作为架构先例；显式枚举三个有效性威胁 — (a) adapter 质量影响结果，通过开源每个 adapter 缓解；(b) agent 内的 backbone 选择可能混淆，通过 matched-backbone 跑中保持 backbone 恒定来缓解；(c) 某些 agent 作者的默认配置与规范化配置不一致，通过双 leaderboard 缓解。这是 MedAgentBench 用的同款三重防御。

---

## 4. 预注册的失败分析假设（问题 3）

罕见病 agent 文献中没有论文预注册假设 — RareBench、DeepRare、MedAgentBench、MedAgentBoard 都做的是事后失败分析。**预注册会是 EMNLP 投稿的正向差异化因子**。下面的假设校准到 DeepRare、RareBench、AgentClinic 已发表失败分析实际使用的具体分层，效应量在可能时锚定到文献。

**H1 — 超罕见患病率降级所有 agent**。按 Orphanet 患病率层分层（≥1/2,000、1/2,000–1/1M、<1/1M、"非常罕见/未知"）。假设：每个 agent 的 Recall@1 跨层单调下降。预期效应量：基于 RareBench RAMEDIS vs MME gap，常见罕见 vs 超罕见之间 15–30 个百分点。**如被证伪**：agent 可能在按表型模式而不是按疾病频率先验检索，这实际上是期望的。

**H2 — 通用医学 agent 系统性失败在 Pillar 3（基因型感知）上**。对比罕见病专用 agent（DeepRare、PhenoBrain、RDMA、VC-RDAgent）和通用医学 agent（MDAgents、MedAgents、AgentClinic、MAI-DxO）在 Pillar 3 上的 Recall@1。假设：Pillar 3 上 ≥20 pp gap，Pillar 2 上 ≤5 pp gap。锚点：DeepRare 报告 Xinhua（109 例）HPO-only 46.8% → HPO+VCF 70.6% Recall@1 — 基因型通道是最大单一贡献者，对非专用 agent 不可见。

**H3 — 工具使用 agent 对数据泄漏更鲁棒**。用 cutoff 后 PMC OA holdout split。假设：有主动检索的 agent（DeepRare、RDMA、MAI-DxO）比仅参数化的 agent（MedAgents、LLM controls）显示更小的 pre/post-cutoff 下降。预期效应：3–8 pp 差分下降。**如被证实**，这成为工具使用罕见病 agent 的承载论证。

**H4 — 多 agent 协作在复杂病例上帮助，在简单病例上有害**。按复杂度分层（单专科 vs 多专科需要，按 DeepRare 风格）。假设：MDAgents/MedAgents/MAI-DxO 在低复杂度病例上低于单 LLM controls（overthinking），在高复杂度病例上超过。**MedAgentBoard（NeurIPS 2025）发现多 agent 在多个医学任务上不一致地击败单 LLM** — 预注册这个假设让你能对齐或扩展那个反直觉发现。

**H5 — 中文病例揭示 HPO 映射中的英语锚定偏倚**。在 PUMCH-Chinese 和匹配的英文子集上对比 phenotype-extraction F1 和下游 Recall@1。假设：英语训练 agent 的 Pillar 1 F1 下降 ≥10 pp，下游 Recall@1 下降 ≥5 pp。锚点：RareBench 报告 Llama2-7B "在长篇中文 EHR 文本上性能差到无法输出正常结果" — 具体的先验证据。

**H6 — Reasoning 模式 LLM 改善校准多于准确率**。对比 GPT-5 reasoning on/off 和 DeepSeek V3.2 reasoning on/off（暴露此功能时）。假设：reasoning on 时 Brier score / ECE 改善 ≥0.05；Recall@1 改善 <2 pp。锚点：MedHELM 发现 reasoning 模式 DeepSeek-R1 达到 66% 胜率，但校准 metric 上的差异比准确率上的更大。

**H7 — 失败按专科聚类**。按 14 个身体系统类别分层（DeepRare 分类法）。假设：agent 在代谢和肺部领域最弱（DeepRare "Lungs/Breathing" 31% vs "Kidneys" 66%），在肾脏和血液领域最强。跨 agent：弱专科的*排名*在 agent 间相关 ≥0.6（共享盲点），暗示数据集/本体 gap 而非 agent 特定弱点。

**H8 — 表型密度非线性预测性能**。按 # HPO 词项分桶（≤5、6–15、16–30、>30）。假设：倒 U 型 — 词项太少（欠规约）和词项太多（噪声/干扰）都降级 Recall@1。RDMA 报告 MIMIC-RD 有 ~128 phenotypes/case vs RAMEDIS 的 ~6，提供了测试平台。

**H9 — Family-aware（Pillar 4）增益只在常染色体隐性和 X 连锁病例上累积**。按遗传方式分层 Pillar 4。假设：family-history 在 AR/XL 病例上产生 ≥10 pp 增益，AD/de novo 上 ≤2 pp。蕴含：如被证实，Pillar 4 应按遗传方式分层作为主要报告。

**H10 — 忠实度（D 类 metric）与准确率脱钩**。假设：按 Pillar 5 忠实度（引用准确率、推理链效度）排名 agent 与按 Pillar 2 准确率排名只是弱相关（Spearman ρ < 0.5）。锚点：DeepRare 标记了"幻觉引用"作为 Type-1 错误类别，尽管诊断准确率高。**如被证实**，这是"仅准确率不够"的最强单一论证 — 也是主要卖点。

**H11 — Backbone 效应在通用 agent 上主导 scaffolding 效应，但罕见病 agent 上不是**。假设：保持 backbone 恒定，通用 agent scaffold（MDAgents/MedAgents/AgentClinic）之间的展开小于罕见病 agent（DeepRare/PhenoBrain/RDMA/VC-RDAgent）之间的展开。**如被证实**，scaffolding 在领域专用时最重要；如被证伪，scaffolding 是通用提升。

每个假设预注册测试（stratum proportion 上的 Wilson-CI；跨 agent 对比的 paired bootstrap McNemar）和多重对比修正（H1–H11 族上的 Holm–Bonferroni）。在 unblind held-out split 之前预注册到 OSF — 这一动作单独提前回应 ARR R1（数据分析严谨性）和 R5 批评。

---

## 5. 消融实验目录（问题 4）

DeepRare、MDAgents、AgentClinic、RareBench 已发表的消融落到五个族里。下面是针对你 benchmark 可能做出的具体主张设计的 12 个消融的目录。

**A1 — DeepRare 模块消融**。切换（case retrieval、web knowledge、self-reflection loop）on/off。锚点：DeepRare 自己报告的结果 — RareBench-MME 上 case retrieval +40%、self-reflection +64%、web-knowledge +62%。独立验证这些数字；如果复现，强化 DeepRare 的贡献和你 benchmark 的效度。**工具级消融（40+ 工具逐个）在已发表论文中没做过** — 做它会是净新贡献。

**A2 — 多 agent 深度消融**。对 MDAgents 跑 PCC-only（1 个 agent）、MDT（多学科，~3 个 agent）、ICT（综合护理团队，完整 panel）。对 MedAgents 扫描专家角色数 {1, 3, 5, 7} 和讨论轮次 {1, 2, 3}。对 MAI-DxO 社区移植版跑模式 `instant`、`question_only`、`budgeted`、`no_budget`。直接测试 H4，对齐 MedAgentBoard 关于多 agent 不一致帮助的反直觉发现。

**A3 — Backbone × scaffolding 2×N 网格**。每个 agent 跨两个 backbone（DeepSeek V3.2、GPT-5）。把方差分解为 backbone 效应、scaffolding 效应、交互。这是 reviewer 最常要求的消融（锚定到 ARR H13/H14 批评模式），DeepRare 也精确地对它的中央 host 跨 DeepSeek-V3、GPT-4o、Claude-3.7 做了这个。

**A4 — 罕见病 agent 的领域知识消融**。对每个罕见病 agent 跑 (i) 完整系统、(ii) 禁用 Orphanet/HPO/OMIM 工具的系统、(iii) 把疾病知识替换为通用 Wikipedia 检索器的系统。量化精选罕见病本体的价值。PhenoBrain 的经典 ML 流水线作为非 LLM 消融点。

**A5 — Reasoning 模式 on/off**。对暴露此功能的 backbone（GPT-5 thinking；DeepSeek V3.2 reasoning channel 暴露时），在两种模式下跑所有 agent。锚定到 H6。也相关于 MedHELM 发现 reasoning 模型领跑胜率排名。

**A6 — Cutoff 后 holdout split（数据泄漏）**。在每个 agent 上跑 pre-cutoff 和 post-cutoff split。差分是泄漏估计。配 TS-Guessing 和 n-gram overlap 审计（Sainz et al. EMNLP-Findings 2023；Deng et al. NAACL 2024）。这是你对污染批评的单一最强预先回应。

**A7 — LLM controls 的 few-shot vs zero-shot**。RareBench 报告 dynamic-3-shot 比 zero-shot 给 ~108% Top-1 改善 — 一个很大的效应，如果不控制，污染任何"agent 击败 LLM"的主张。在 {zero-shot, few-shot-static, dynamic-few-shot, MedPrompt} 下跑 LLM controls，让 agent-vs-LLM 对比是针对*最强*的 LLM baseline。

**A8 — 输入格式消融（gold HPO vs 抽取 vs free-text）**。每个 agent 三次跑：(i) phenopacket 的 gold HPO，(ii) agent 自己 Pillar 1 模块抽取的 HPO，(iii) 仅 free-text。测量端到端 vs 组件性能，是 RareBench Table 6 的直接扩展。

**A9 — Pillar 3 的基因型通道消融**。跑 HPO-only、HPO+VCF、VCF-only。DeepRare 报告加 VCF 后 46.8% → 70.6% Recall@1；跨 agent 阵容复现并扩展。缺少 VCF 处理组件的 agent 会显示 0% delta — 这是 Pillar 3 专用化测试。

**A10 — Pillar 4 的 family-aware 通道消融**。带/不带家族史；带/不带显式 pedigree；带/不带遗传方式提示。测试 H9，量化家族信息的边际价值。

**A11 — 成本上限扫描**。受 MAI-DxO `budgeted` 模式启发。把每例 API/工具预算上限设为 $0.10、$0.50、$2、$10、unlimited；在每个上限测量 Recall@1。产生成本 Pareto 图，成为 signature 图。

**A12 — LLM-judge vs exact-match 评分**。用 (i) exact OMIM/Orphanet ID match、(ii) BioLORD synonym fuzzy match、(iii) GPT-5 LLM-judge、(iv) 分层 200 例子集上的医生裁决重新评分相同预测。报告一致性统计（Cohen's κ；ICC）。这预先回应了 reviewer 对 LLM-as-judge 的怀疑 — DeepRare 的 Pearson 0.87 / 95.4% 医生一致率是要匹配的金标准。

每个消融回答一个具体的 reviewer 问题。A1、A2、A4 捍卫 agent 层的价值；A3、A5、A7 防御 backbone 混淆；A6 防御污染；A8、A9、A10 给多 pillar 结构以动机；A11 给成本作为 metric 以动机；A12 捍卫评估方法论。

---

## 6. Top 10 Reviewer 攻击与预先缓解（问题 5）

锚定到 ARR Reviewer Guidelines（May 2025）、接受的 EMNLP/NAACL 医学 benchmark 论文的 Limitations 部分、以及 DeepRare、RareBench、MedAgentBench、MedAgentBoard 的显式防御。按可能性 × 严重性排序。

**攻击 1 — "数据污染未充分控制"**。任何 2023 年后 LLM benchmark 的最常见攻击。公开数据集（RAMEDIS、MME、HMS、LIRICAL、RareBench 自己的 split）可证明在预训练语料中。**缓解**：cutoff 后 PMC OA holdout（A6）作为主要报告；TS-Guessing 审计（Deng et al. NAACL 2024）和 appendix 中的 n-gram overlap 分析；每个 agent 的 pre/post-cutoff 结果分开报告；显式 Limitations 段落说明哪些数据集是公开的。

**攻击 2 — "跨异质 agent 的不公平比较"**。不同 agent 接受不同输入；benchmark 可能在测 adapter 质量而不是 agent 能力。**缓解**：双 pass 评估（gold HPO + 端到端；上面 §3）；发布的 per-agent adapter shim，配显式 "Agent Fairness Matrix" appendix；双 leaderboard（作者默认配置 + matched-backbone 配置）；引 RareBench Table 6 作为双 pass 设计的直接先例。

**攻击 3 — "缺失 baseline，特别是微调医学 LLM 和经典工具"**。**缓解**：把经典 Exomiser + LIRICAL + PhenoBrain 流水线作为非 LLM baseline（PhenoBrain 本身是强非 LLM 罕见病流水线，报告 top-3 0.513）；包含至少一个微调医学 LLM（Meditron-70B 或 OpenBioLLM-70B）；包含最强的 no-scaffold reasoning-LLM（你的 DeepSeek V3.2 和 GPT-5 controls 如果开 reasoning 模式就覆盖了）。DeepRare 论文做了精确的同款 baseline 选择，被 Nature 接受。

**攻击 4 — "统计严谨性不足"**。ARR R5 显式标记缺失 CI 和显著性测试。**缓解**：每个报告 metric 上的 bootstrap 95% CI（≥1000 重采样）；vs 最强 baseline 的 paired McNemar / paired bootstrap p 值；跨 agent 对比的 Holm–Bonferroni 修正；Cliff's δ 效应量；报告每层的样本量。

**攻击 5 — "MIMIC-IV 是 ICU only，不代表人群；benchmark 不具代表性"**。**缓解**：四层数据集 stack 是答案 — Phenopacket-Store（精选）、RareBench（5 子集合包括 PUMCH、MME、RAMEDIS、HMS、LIRICAL）、MIMIC-IV 切片 + MIMIC-RD（真实 EHR）、RareArena（RDS+RDC）、自建 PMC OA holdout。Table 2 报告 per-dataset metric 并按 source-type 分层（精选 vs 真实 EHR vs 病例报告 vs 文献）。DeepRare 用三个难度层（文献 / 病例报告 / 真实临床）做了同样的论证。

**攻击 6 — "单语 / 英语中心偏倚"**。**缓解**：显式包含 RareBench 的 PUMCH 中文子集，报告 per-language metric（也测试 H5）；引 AgentClinic 的 7 语言评估作为领域标准；如果非英语覆盖有限，在 Limitations 把声明范围缩到英语，而不是过度声称。

**攻击 7 — "为什么选这 10 个 agent？选择似乎任意"**。ARR M4（未给动机的选择）。**缓解**：在 §3 预注册纳入标准（例如"≥2023 的 agent 论文、公开代码或详细伪代码、peer-reviewed 或 arXiv、声称罕见病或通用临床诊断能力"）；考虑但排除的系统的显式 table 加理由（RareAgents、RDguru、RDmaster 是值得至少提到的可能候选）；记录 LLM-control 选择（便宜 vs 贵 backbone）。

**攻击 8 — "多 agent 协作可能实际不帮助，削弱 benchmark 的框架"**。MedAgentBoard（NeurIPS 2025）发现多 agent ≤ 单 LLM 在多个医学任务上。**缓解**：显式包含单 LLM 带强 prompting 的 baseline（A7）；不论方向报告 H4 结果；把 Pillar 5（临床沟通与推理）框架为差异化器 — 多 agent 可能不提升准确率但可能提升忠实度/沟通。主动引 MedAgentBoard 作为动机而不是威胁。

**攻击 9 — "成本不是临床有意义的 metric"**。MAI-DxO 因此被攻击。**缓解**：报告三个不同的成本轴 — (i) 确定性 API token 成本、(ii) 墙钟延迟、(iii) 用已发表收费表模拟的诊断检查成本（Medicare 临床实验室收费表），每个清楚标注；不混淆它们；在 Limitations 注明模拟检查成本是虚拟的，不是临床经济声明。

**攻击 10 — "LLM-as-judge 对诊断正确性不可靠"**。**缓解**：主 metric 是对 gold OMIM/Orphanet 编码的**精确匹配**（确定性）。LLM-judge 仅用于开放式维度（推理链质量、沟通清晰度），并在分层 200 例子集上对 ≥2 名临床医生验证，报告 Cohen's κ — DeepRare 的 Pearson 0.87 和 MedHELM 的 ICC 0.47（vs 医生间 0.43）是先例 benchmark。

值得在 Limitations 部分预防的两个额外批评：**(11) 可复现性** — 闭源模型版本静默变化，所以固定模型版本 + 日期并提供 Docker image；**(12) 过度声称** — 框架为"回顾性决策支持"而非"自主诊断"，除非条件匹配否则避免与医生头对头对比（MAI-DxO 的医生对比正因为临床医生没有书、同行、AI 工具而被攻击）。

---

## 7. Pillar 依赖 DAG（问题 6）

依赖结构完全取决于你用 **gold HPO 输入**（并行）还是 **agent 抽取的 HPO 输入**（串行）。两个都应该报告。

### Gold-HPO 模式（推荐为主；匹配 RareBench、DeepRare 惯例）

```
                  ┌──────────────────────────────────────────┐
                  │  规范案例对象（每个数据集行）             │
                  │   • 自由文本                              │
                  │   • gold HPO 列表（从 phenopacket）       │
                  │   • 可选 VCF                              │
                  │   • 可选家族/pedigree                     │
                  │   • demographics                          │
                  └────┬────┬────┬────┬────┬─────────────────┘
                       │    │    │    │    │
                       ▼    ▼    ▼    ▼    ▼
                    P1   P2   P3   P4   P5
                  (抽取) (HPO→ (HPO+ (HPO+ (推理
                         DDx)  VCF) family) +沟通)
                       │    │    │    │    │
                       ▼    ▼    ▼    ▼    ▼
                  五个 pillar 全部可真正并行评估
```

在这个模式下每个 pillar 只读规范案例对象；没有 pillar 的*输出*被要求作为另一个 pillar 的*输入*。**所有 5 个 pillar 在每个 agent 每个 dataset 每个 backbone 上同时跑。**

### 端到端模式（副；匹配部署现实）

```
              自由文本  ──►  P1（agent 抽取 HPO）
                                    │
                ┌───────────────────┼───────────────────┐
                ▼                   ▼                   ▼
               P2                  P3                  P4
       (抽取的 HPO)       (抽取的 HPO + VCF)   (抽取的 HPO + 家族)
                                    │
                                    ▼
                                   P5
                       (在 P2/P3/P4 输出上推理)
```

这里 P1 在 P2/P3/P4 的关键路径上，P5 又消费它们的输出。严格串行依赖：P1 → {P2, P3, P4}（这组内并行）→ P5。

### 横切评估透镜（对所有 pillar 并行）

Bias 评估、污染审计、成本/延迟测量是**横切的**：它们在事后从相同的预测日志重新计算，所以**不施加额外的执行依赖**。它们是对存储预测的事后分析。

### 实际蕴含

对 "gold-HPO" 跑，**沿着 (agent × backbone × dataset × pillar) = 20 × 4 × 5 = 400 个独立 job 并行**，加上 LLM-control 额外的和消融 cell。embarrassingly parallel — 只受 API 速率限制和预算约束。"端到端" 跑增加单个 P1 → 下游串行依赖 per (agent, case)，但其他方面跨案例和跨 agent 仍然并行。

---

## 8. 最终实验 plan（问题 7）

下面是逻辑序列和并行结构，无时间/人员细节。步骤内并行用 **‖** 标记，步骤间串行依赖用 **→** 标记。

### Step 0 — 前置（全串行；任何东西开跑前必须完成）

单一最长的串行阻塞。组件：

1. **数据规范化**：把 Phenopacket-Store、RareBench（5 子集合）、MIMIC-IV 切片 + MIMIC-RD、RareArena（RDS+RDC）ingest 到规范案例对象 schema（自由文本 + gold HPO + VCF + 家族 + demographics）。验证 gold-HPO 和 OMIM/Orphanet ID。
2. **Cutoff 后 PMC OA holdout 构建**：收割出版日期严格晚于两个 backbone 最新已知训练 cutoff 的病例报告；人工精选 gold 标注；保留为污染受控 split。
3. **Per-agent adapter shim**：实现 10 个 agent 各自的规范对象 → 原生格式投影。记录到 Agent Fairness Matrix。
4. **Metric 实现**：Recall@1/3/10、Median Rank、MRR、Brier/ECE、Pillar 1 的 F1、Pillar 5 的忠实度 rubric、成本/延迟 logger。
5. **基础设施**：预测日志 schema、确定性 seed、per-call 成本/延迟捕获、可复现性 Docker image、leaderboard scaffolding。
6. **预注册**：在 unblind holdout split 之前把 H1–H11 假设、评估协议、消融列表存到 OSF。

这一步主要串行；唯一有意义的并行是 **(1) ‖ (3) ‖ (4)** 一旦 schema 商定就可以同时推进，**(2)** 可以与其他所有并行推进。**(6) 必须在 (1)–(5) 之后、Step 2 之前**。

### Step 1 — 基础跑（校准和效度检查；主要串行但小）

这是个小桥接步骤，在承诺 API 预算给完整跑之前锁定评估方法效度。组件，相互可并行：

- 在分层 200 例子集上**对临床医生校准 LLM-as-judge**（消融 A12 第一切片）。在主跑之前建立 Cohen's κ。
- **Adapter 健全检查**：每个 agent 在每个数据集 20 个 canary case 上跑，人工检查输出格式错误。便宜地抓 adapter bug。
- **Backbone 版本固定**：snapshot DeepSeek V3.2 和 GPT-5 的模型 ID、日期、系统指纹；在暴露的地方设确定性 seed。
- **Few-shot 样例选择**：为 LLM controls（A7）预选 few-shot 样例 — 只能从 train/dev split 抽取，绝不从 holdout。

**‖** 四个子任务并行。**→** Step 2 不能开始直到 A12 校准通过（否则主跑评分未验证）和 adapter 健全通过（否则主跑结果损坏）。

### Step 2 — 主实验（大规模并行）

两个 pass，每个在 (agent × backbone × dataset × pillar × case) 上完全并行。

**Step 2a — Gold-HPO pass（主）**：20 (agent × backbone) × 4 dataset × 5 pillar。**所有 5 个 pillar 真正并行**因为 gold HPO 移除了 P1 → 下游依赖。job 内并行只受 API 速率限制和预算约束。包含横切 bias 和污染 cell（免费；从同一预测计算）。

**Step 2b — 端到端 pass（副）**：同样的 20 × 4 网格，但现在每个 (agent, case) 内 P1 → {P2, P3, P4} → P5 串行。跨案例和 agent，仍然 embarrassingly parallel。

只要预算允许，2a 和 2b 可以**互相并行**跑；它们用不同的 prompt 不共享状态。

**‖** Step 2 内：2a 的所有 (agent × backbone × dataset × pillar × case) cell 并行；2b 的所有 (agent × backbone × dataset × case) 并行，案例内 P1→下游串行。
**→** Step 3 不能开始直到 Step 2 预测被存储。

### Step 3 — 消融和分析（主要并行；部分依赖 Step 2 日志）

所有 12 个消融（A1–A12）混合使用**新跑**（A1、A2、A4、A5、A8、A9、A10、A11）和**Step 2 日志的事后重分析**（A3 backbone-vs-scaffolding 分解；A6 pre/post-cutoff 切片；A7 LLM control 变体；A12 替代评分）。

- **‖** 重分析消融（A3、A6、A7、A12）立即对 Step 2 日志并行跑。
- **‖** 新跑消融（A1、A2、A4、A5、A8、A9、A10、A11）相互之间和与重分析并行跑。
- **→** 假设测试 H1–H11 是 Step 3 的*输出*，必须跟随消融完成（某些 H 测试如 H4 依赖 A2 结果；H6 依赖 A5）。
- **‖** 失败分析案例研究和定性错误编码可以在 Step 2 日志可用后与定量消融并行推进。

### Step 4 — 写稿和防御（最终串行化）

**→** Step 3 的头条数字和假设测试稳定后开始。Step 4 内并行回归：

- **‖** 主论文起草（8–9 页：§1 intro/贡献，§2 相关工作配显式 RareBench/DeepRare gap 分析，§3 benchmark 设计，§4 实验设置含预注册链接，§5 主结果配 Table 1–2 和 Figure 1–4（heatmap、radar、cost-Pareto、专科 bar），§6 消融，§7 limitations，§8 conclusion）。
- **‖** Appendix 构建（Agent Fairness Matrix、完整 per-cell table、prompt、污染审计、可复现性声明、完整假设测试结果、Responsible NLP checklist）。
- **‖** Leaderboard 发布（含 400 cell 完整矩阵的 static site）。
- **‖** 防御材料：ARR rebuttal-ready 笔记，把每个 Tier-1 reviewer 攻击（§6 上面）映射到具体论文章节、表号、appendix 行。准备"Top 10 预期问题"内部 doc 按攻击 1–10 索引。

**→** 最终串行化是主论文 + appendix + leaderboard URL + Responsible NLP checklist 的组装提交。

### 关键路径总结

**关键路径是 Step 0 → Step 1 中的校准 → Step 2a 主 pass → Step 3 中的关键假设测试 → Step 4 中的主论文起草**。其他一切（消融、副 pass、appendix table、leaderboard）可以从这个脊柱并行分支跑。**5 个 Pillar 本身在推荐的 gold-HPO 设计中不是串行瓶颈** — 这是项目最重要的并行性发现。

---

## 结论：采用这个 plan 会改变什么

三个设计选择完成大部分工作。**第一**，把 Pillar 1 当作单独评估的任务、对 Pillar 2–5 用 gold HPO，把 5-pillar 结构从串行流水线转化为 embarrassingly parallel 网格 — 这单一决定让主实验能跑成一次大型并行扫描而不是五个分阶段 pass。**第二**，双 pass（gold-HPO + 端到端）评估通过把格式异质性公平性批评从混淆变量转化为测量的轴来直接回答，RareBench Table 6 作为直接先例。**第三**，在 unblind cutoff-后 holdout 之前预注册假设 H1–H11 和消融 A1–A12 同时回应数据污染和统计严谨性批评（两个最可能的 Tier-1 reviewer 攻击），且是正向差异化因子，因为没有任何先前的罕见病 benchmark 做过这个。

实证上对 400 cell 矩阵起作用的主论文结构是：一张 Pillar-first headline table、一张主 metric 上的 dataset 分布 table、4 张 signature 图（heatmap、5 轴 radar、cost-Pareto scatter、专科 bar）、显式回答攻击 1–10 的 Limitations 部分、托管完整矩阵的公开 leaderboard。这是 AgentBoard / τ-bench / MedHELM / SWE-bench 惯例，能在不淹没读者的情况下扩展到你的维度。没有先例消除的唯一结构性风险是多 agent 开销不带准确率增益（MedAgentBoard 的反直觉发现） — 解决它要求你的单 LLM 带强 prompting baseline（A7）是真正强的，不是稻草人。