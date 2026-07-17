# 罕见病 Agent Benchmark：可行性、结构与可防御性分析

## 执行摘要

**Agent 导向的 benchmark 方向有充分的差异化空间且可行，但你的草稿结构需要在投 NeurIPS/ICLR D&B 或 Nature Medicine/npj Digital Medicine 之前做精准修订。** 证据支撑四个明确结论。

**第一，gap 是真实的。** 在 2023–2026 年发表的 9 个专门的罕见病诊断 benchmark 中，**8 个评估的是 base LLM（用 prompting、few-shot 或 RAG），1 个是混合型；零个是为 agent 评估而设计的 benchmark。** 现有的 agent *系统*（DeepRare、RareAgents、RDguru、RADAR、RDMA）全部都是在自建或临时改造的 LLM benchmark 上评估自己。罕见病领域**没有任何 SWE-Bench、τ-bench、WebArena 的对应物**。2026 年 3 月 medRxiv 一篇系统综述（涵盖 15 项研究、39,529 例）独立验证了这一不对称，并显示 agent 增强系统优于 LLM 单体（R@1 52.5% vs 35.4%，p=0.004）— 然而它们没有共享评估基座。

**第二，有足够的 agent 候选作为 benchmark 对象。** 我们识别出 **8–11 个不同的 agent 方法**，舒服地超过 5–10 个的可行下限：5 个罕见病专用真 agent（DeepRare、RareAgents、RADAR、RDMA、Almasoud 拓扑变体）、3–4 个可移植到罕见病数据的强通用医学 agent baseline（MAI-DxO、MDAgents、MedAgents、MedAgent-Pro）、2 个边界案例（LA-MARRVEL、AMIE）。这足够支撑 leaderboard 密度和消融实验深度。

**第三，推荐的 metrics 结构是三轴分类法** — 结果准确率（Recall@k、中位数排名、Gene Top-k）、过程质量（工具选择准确率、推理步数、成本、引用/参考准确率、校准度）、可靠性（pass^k、工具失败下的鲁棒性）。现有罕见病 benchmark 第一轴覆盖良好、第二轴只部分覆盖（DeepRare 的 95.4% 参考准确率指标是唯一示例）、第三轴基本未覆盖。**覆盖三个轴就是可发表的核心贡献。**

**第四，结构性建议非常明确：把"Bias"从顶层 pillar 降为横切的评估透镜，"Family-aware"只有在能凑够 ≥150–300 个 trio/pedigree 病例时才保留为顶层 pillar。** 没有任何主流的整体性 benchmark — HELM、MedHELM、VHELM、RareBench、DeepRare — 把 bias 当作顶层 pillar。Bias 作为顶层 pillar 只出现在*专门的公平性探针*（EquityMedQA、HEAL、Omiye、Zack）中，这些工作并不自称是整体性 benchmark。对罕见病而言，最有意义的 bias 维度（遗传祖源偏倚、训练数据记忆、语言偏倚）本质上都是*诊断准确率的分层切片*；把它们提升为独立 pillar 反而会*降低*它们的测量覆盖度。

最强的 peer review 防御叙事：这**不是"RareBench++"**，因为 (a) 现有 benchmark 是对 base LLM 的静态 input→output 评估，agent benchmark 需要带成本和可靠性语义的交互式工具环境；(b) 没有任何现有 benchmark 暴露了定义 agent 系统的工具使用、推理轨迹、pass^k 可靠性这三个维度；(c) 中文角度（`_zh`）正面回应了 HPO 已被记录的英语锚定偏倚，是真正的公平性贡献；(d) DeepRare 和 RareAgents 自己**不得不**搭建临时评估集，正是因为没有共享基座。

---

## 现有 benchmark 调研：LLM vs Agent 分类

下表覆盖我们识别到的所有专门罕见病诊断 benchmark，按年份排序。**加粗行**是引用最多或规模最大的。"Agent 定位？"列反映作者是否*显式将其定位*为 agent 评估 — 而非偶尔提到 "agent" 一词。

| Benchmark | 年份 / 期刊会议 | 类型 | 病例数 | 疾病数 | Rare 定义 | 模态 | 指标 | Agent 定位？ |
|---|---|---|---|---|---|---|---|---|
| **RareBench**（Chen et al.） | KDD 2024 | **LLM** | ~2,764 | ~700+ | Orphanet + OMIM + CCRD | 结构化 HPO 编码 | Top-1/3/10, MR | 否 |
| **RareArena**（Zhao et al.） | Lancet Digit Health 2025 | **LLM** | 49,760 / 22,901 | 4,597 / 3,522（Orphanet 的 45.6%） | Orphanet | 自由文本（PMC） | Top-1, Top-5 | 否 |
| **MIMIC-RD**（Wu et al.） | arXiv 2026 | 混合 | 145（挖掘） | ~145 | Orphanet | 真实 EHR 出院记录 | Hit@1/5/10 | 部分 |
| Phenopacket-Store（Danis et al.） | HGG Adv 2025 | 资源 | 4,916–7,552 | 277–481 | OMIM/Mendelian | GA4GH Phenopackets | n/a | 否 |
| Reese et al. phenopacket 评估 | Eur J Hum Genet 2026 | LLM | 5,213 | 378 | OMIM | Phenopackets→文本 | MRR, Top-1/3/10 | 否 |
| Chimirri et al. 多语言 | eBioMedicine 2025 | LLM | 4,917（10 语言） | 360–378 | OMIM | Phenopackets | Top-1/3/10 | 否 |
| ReDis-QA / ReCOP | arXiv 2024 | LLM (RAG) | 1,360 QA | 205 | NORD（<200k US） | MCQ + 开放 QA | 准确率 | 否 |
| DxGPT 评估 | medRxiv 2024 | LLM | ~275 + 合成 | RAMEDIS+PUMCH | Orphanet | 自由文本 | Strict Acc, Top-5 | 否 |
| RareAlert | arXiv 2026 | LLM（筛查） | 158,666 | 33 类 | Orphanet | 初诊叙述 | AUC 0.917 | 否 |
| House M.D. benchmark | arXiv 2025 | LLM | ~302 | 33 类 | 叙述型 | 电视剧叙述 | 准确率 | 否 |
| Almasoud 拓扑研究 | AAAI 2026 | Agent 评估论文（非数据集） | 302 | 33 | n/a | 叙述 | 准确率 + Reasoning Gap | 是 |

**结论**：「现有 benchmark 大多以 LLM 为中心」这一假设*得到强力验证*。9 个真正的诊断 benchmark 中，8 个评估 base LLM、1 个是混合型。Almasoud 拓扑研究是唯一显式以 agent 为对象的工作，但它复用了 302 个叙述病例而非引入新数据集。所有现有 agent 系统（DeepRare、RareAgents、RDguru）**都自建临时评估集**，正是因为没有社区共享的 agent 评估基座。

Gap 分析使差异化论证清晰起来。当前 benchmark 缺失：交互式工具 API（罕见病领域没有 BFCL 的对应物）、多轮信息引出任务（只有 RDguru 用 238 例提示了一下）、推理轨迹金标准（DeepRare 报告了 5 类失败分类但未对轨迹打分）、成本/延迟维度、多 agent 协作评估、工具失败鲁棒性、患病率分层（2026 综述呼吁但无人实现）、未见过疾病的 held-out split（综述指出每个现有数据集都有高数据泄漏风险）。

---

## Agent 方法目录

我们识别出 8–11 个不同的 agent 方法，按作为 benchmark 对象的契合度组织如下。

| # | 方法 | 年份 / 期刊会议 | 架构 | Backbone | 工具 | 评估数据集 | 头条性能 | Agent 程度 |
|---|---|---|---|---|---|---|---|---|
| 1 | **DeepRare** | Nature 2026 | 多 agent：中央 host + agent server + 反思 | 模型无关（DeepSeek-V3 最佳） | 40+ 工具（HPO、Orphanet、OMIM、PubMed、web、变异分析器） | 9 数据集，6,401 病例，2,919 疾病 | R@1 57.18% HPO；69.1% 多模态；95.4% 参考准确率 | 高 |
| 2 | **RareAgents** | AAAI 2026（arXiv 2412.12475） | 多学科团队 + 记忆 + 工具 | Llama-3.1-8B/70B | 41 个专科池 + 医学 KG | RareBench + MIMIC-IV-Ext-Rare（4,760 患者） | 优于 GPT-4o、MedAgents、MDAgents | 高 |
| 3 | **MAI-DxO**（Microsoft） | arXiv 2506.22405 | 8 角色 panel + 顺序检查决策 | 模型无关 | 检查决策模拟器、成本追踪 | 304 例 NEJM CPC（多为罕见/复杂） | 准确率 85.5%，成本下降 ~70% | 高 |
| 4 | **RADAR** | arXiv 2511.04720 | 初诊医生 → 检索 agent → 终诊医生（loop 内 RAG） | 模型无关 | FAISS 索引（病例报告 + 文献） | 脑 MRI 罕见病例 | 多 backbone 上一致提升 | 中-高 |
| 5 | **RDMA** | arXiv 2507.15867 | 专门挖掘子 agent | 开源（本地） | HPO/Orphanet 本体校验 | EHR 罕见病抽取 | F1 +30%，成本降低 10× | 高（挖掘任务） |
| 6 | **MDAgents** | NeurIPS 2024（oral） | 自适应 solo↔group + moderator | GPT-4/Gemini/Claude | 外部医学 KG | 10 个医学 benchmark（通用） | +4.2–11.8% over prior | 高（通用 baseline） |
| 7 | **MedAgents**（Tang et al.） | ACL 2024 | 多学科角色扮演 | GPT-3.5/4 | 无 | MedQA 系列 | 用作 baseline | 中（通用） |
| 8 | **Almasoud 拓扑** | AAAI 2026 | 层次化 / 对抗式 / 协作式变体 | GPT-5.1 | 无 | 302 病例 × 33 类 | 层次化 50.0% > 对抗式 27.3% | 中 |
| 9 | **MedAgent-Pro** | preprints 2025 | 层次化 workflow + 多模态 | MLLM | 检索准则 | 多种医学任务 | — | 中 |
| 10 | **LA-MARRVEL** | arXiv 2511.02263 | LLM 重排 + 排名投票聚合 | Claude / Claude-Thinking | AI-MARRVEL、HPO、VEP | BG、DDD、UDN 队列 | +12–15 pp R@1 | 边界 |
| 11 | **AMIE** | Nature 2025 | 微调 LLM + 自博弈 critic | 自定义 Gemini | 内部 critic；多模态版加工具 | OSCE 风格、NEJM CPC | Top-10 ≥ 全科医生 | 中（训练时 agentic） |

**作为非 agent 排除**（但适合作为经典 baseline）：SHEPHERD（生物医学 KG 上的 GNN，npj Digital Medicine 2025）、Phen2Gene/Phen2Disease/Phenolyzer/Exomiser/LIRICAL/AI-MARRVEL（概率排序器）、PhenoBrain（BERT 集成，npj Digital Medicine 2025）、RareSeek-R1（微调 LLM + GraphRAG）、DxGPT（单 GPT-4 prompt）、Med-Gemini（带可选搜索路由的微调多模态 LLM）。

**怀疑性观察**。第一，文献里有些 "agent" 本质上就是 GPT-4 加个 prompt — DxGPT 和大多数 "RareBench 上的评估" 属于此类，应该过滤掉。第二，真正不同的 agentic *架构*只有三四种（DeepRare 的 host-server 模式、RareAgents 的 MDT、MAI-DxO 的 role panel、RDMA 的挖掘流水线），其他系统都是 prompt 设计的变体。第三，数据污染风险高：2026 综述判定全部 19 项 LLM 罕见病评估都存在高数据泄漏偏倚，因为病例报告很可能在预训练语料中。新 benchmark 必须包含一个 cutoff 后 held-out split。第四，多 agent 不一定有用 — Almasoud 的对抗式拓扑*降低*准确率到 27.3%，明显低于单 agent（48.5%）。

---

## Metrics 全景

### 标准准确率指标（A 类）

罕见病领域已经果断收敛到 **Recall@k / Hit@k**（k = 1, 3, 5, 10）作为主要指标，**Median Rank** 作为补充的分布性指标。RareBench、DeepRare、RareAgents、LIRICAL、Exomiser、AI-MARRVEL、DxGPT 全部以 Recall@1 作为头条数字。**MRR** 偶尔出现（Reese et al. 2026）但未成标准；**nDCG** 罕见。HPO 表型抽取的惯例是 **Precision/Recall/F1**（RAG-HPO：P=0.81, R=0.76, F1=0.78）。2026 综述确立了一个事实：R@1 因数据集组成不同而显著差异 — Phenopacket Store 19.9–23.6%、RareBench 32.3–46.0%、Chinese Rare Disease List 64.5%，主要受超罕见病比例驱动。

### 罕见病专属指标（B 类）

**患病率分层是文献里最大的尚未填补的缺口。** 文献中的定义使用：超罕见（<1/1,000,000）、罕见（EU <1/2,000；US <40–50/100,000）、临界常见（6–9/10,000）三层。2026 综述展示了 R@1 与超罕见比例之间的反比关系（R²=0.55，超罕见比例每增加 10% 对应 R@1 下降 5.8 pp），但**目前没有 benchmark 默认报告按患病率分层的准确率** — 这是一个干净的新颖性主张。DeepRare 按 14 个医学专科分层，并按 HPO-only vs HPO+Gene 分层（R@1 从 46.8% → 70.6%，超过 Exomiser 的 53.2%）。基因型驱动评估的标准是 **Gene Top-k**（Exomiser、LIRICAL、AI-MARRVEL）；**变异级 Recall** 出现在 3ASC（Top-10 93.7%）等工具中。

### Agent 专属指标（C 类）

这是你的 benchmark 必须建立新颖性的地方（与现有罕见病 benchmark 的差异 — 后者只用 A 类和部分 B 类）。Agent 评估文献已有成熟工具包，尚未应用到罕见病。

**工具使用**方面，ToolBench、BFCL、MCPToolBench++、MedAgentBench（NEJM AI 2025）的惯例包括：Tool Selection Accuracy、Invocation Accuracy、Input Parameter Accuracy、多步调用的 AST/DAG accuracy、工具依赖图上的 Node-F1/Edge-F1。**MedAgentBench 的主指标是 task success rate**，配以人工策展的参考解，区分 query-based（GET）与 action-based（POST）。

**效率**方面，MedAgentsBench（arXiv 2503.07459）系统性报告性能、成本、推理时间三者的相互作用。CLEAR 框架（arXiv 2511.14136）引入 Cost-Normalized Accuracy（accuracy/USD）、Cost-Per-Success、SLA compliance。Token 成本（输入+输出）和端到端延迟现在已是标准。

**推理轨迹质量**方面，AgentBoard（NeurIPS 2024）引入 Progress Rate（子目标达成比例，与人工判断的 Pearson r > 0.95）和 Grounding Accuracy。AgentProcessBench 提供 8,509 条人工标注的步骤级轨迹。**DeepRare 的 95.4% 参考准确率** — 10 位副主任医师对每条引用是否可靠且直接相关达成的一致率 — 是罕见病领域最佳已发表示例，应该作为默认指标复用。CoT 忠实度 benchmark（FaithCoT-Bench、C²-Faith、MME-CoT、FUR）提供互补的扰动型探针。

**可靠性**方面，τ-bench 的 **pass^k**（k 次独立同分布试验全部成功的概率）现在已是行业标准 — Anthropic model card 报告这个指标，GPT-4o 在零售场景的 pass^8 低于 25%，暴露了单次准确率看不到的脆弱性。ReliabilityBench 引入 Reliability Surface R(k, ε, λ) 和混沌工程式工具失败注入（超时、畸形响应、schema 漂移）。PALADIN 报告 Recovery Rate、Catastrophic Success Rate、Efficiency Score。

**多轮诊断对话**方面，AgentClinic 在准确率之外测量 patient compliance、consultation rating、doctor confidence、follow-up willingness。Information Gain per Turn（基于 Shannon 熵）和 Token Waste Ratio 是医学问诊 agent 的新兴惯例。

**校准**方面，Rivera et al. 在 JAMIA Vol 32 No 1 给出的标准推荐 ECE（10 bin）、Brier Score、置信度判别 AUROC（阈值 ≥0.7），比较 token 概率、采样一致性、置信度引出三类方法。医学应用推荐采样一致性方法。

### 忠实度与幻觉（D 类）

通用医学幻觉方面，**MedHallu**（10,000 PubMedQA 派生 QA，EMNLP 2025；最佳模型 hard-tier F1 = 0.625）和 **MedCite**（引用 P/R）是主流 benchmark。**FActScore** 把生成分解为原子事实，仍是主流通用方法，CORE 提供唯一性过滤。罕见病专属语境下，金标准稀疏的处理方式包括专家评审（DeepRare、LIRICAL 人工评估）、phenopacket 模拟 + spike 变异、知识图谱锚定评估（RareSeek+GraphRAG）。RAG-HPO 的假阳性分类（幻觉 <1%、不相关词项 1.3%、更宽泛的祖先词项 95.2%）是罕见病本体锚定输出的有用模板。

### 推荐的三层 metrics 分类法

**Tier 1 — Core（必报，与现有文献可比）**：差分诊断的 Recall@1/3/5/10 与 Median Rank（RareBench/DeepRare/RareAgents 惯例）；HPO 表型抽取的 P/R/F1；基因型感知流水线的 Gene Top-k（Exomiser/LIRICAL 惯例）；Task Success Rate（MedAgentBench 惯例）；按患病率层、专科、HPO-only-vs-HPO+Gene 分层的准确率；**未见过疾病的 held-out 子集 R@k**，回应综述指出的数据泄漏关切。

**Tier 2 — Secondary（强烈推荐，对应 NeurIPS D&B + JAMIA 期望）**：Tool Selection Accuracy 与 Tool Call Correctness；每例推理步数；延迟与 token 成本，配 Cost-Normalized Accuracy；pass^k 可靠性（k=4 或 k=8）；Progress Rate 用于部分得分；Reference/Citation Accuracy（DeepRare 风格，对 100+ 病例样本由 ≥10 位专家评审）；ECE、Brier Score、置信度 AUROC；对话场景再加 Information Gain per Turn 和 turns-to-diagnosis。

**Tier 3 — Exploratory（可防御性与新颖性）**：在样本上做 AgentProcessBench 风格的步骤级评分；CoT 忠实度（FaithCoT-Bench 或扰动 AOPC）；混沌工程式工具失败鲁棒性，配 Recovery Rate；人口扰动鲁棒性（AgentClinic 24-bias 惯例）；FActScore 风格的原子事实验证（对 UMLS/Orphanet/HPO/OMIM）；采样一致性不确定性代理；儿科/成人和 AR/AD 子组分层。

---

## 数据集与罕见病定义

| 数据集 / 来源 | 病例数 | 疾病数 | Rare 定义 | 金标准 | 模态 | 许可 / 访问 |
|---|---|---|---|---|---|---|
| **RareBench（5 子数据集）** | ~2,764 | ~700+ | Orphanet + OMIM + 中国 CCRD | 临床/基因确诊 | 结构化 HPO 编码 | Apache 2.0 |
| ↳ RAMEDIS | 624 | 74 | 罕见代谢 | 已确诊 | HPO | open |
| ↳ MME（Matchmaker Exchange） | 40 | ~40 | 孟德尔罕见病 | 已确诊 | HPO | open |
| ↳ HMS（Hannover） | 88 | 39 | Orphanet | 已确诊 | HPO | open |
| ↳ LIRICAL test set | 370 | ~370（每病一个） | OMIM/Orphanet | 已确诊 | HPO | open |
| ↳ PUMCH-ADM | 75 | 16 | 中国 CCRD | 已确诊 | HPO + 科室 | 受限 |
| **RareArena（RDS / RDC）** | 49,760 / 22,901 | 4,597 / 3,522（Orphanet 45.6%） | Orphanet | 医生验证的 PMC 报告 | 自由文本 | CC-BY-NC-SA-4.0 |
| **Phenopacket-Store**（最新） | 7,552 | 481 | OMIM 孟德尔/染色体 | 出版物确诊 | GA4GH Phenopackets | CC-BY |
| **MIMIC-IV** 罕见病切片 | 1,875 / 4,760 / 145 | 355 / 不一 / ~145 | ICD→Orphanet 映射 | 医生/学生标注 | EHR 文本（+ 入院/用药） | PhysioNet 凭证 |
| **DDD** | 2,283 | 发育 | 孟德尔/OMIM | 已确诊 | 结构化 | 受控 |
| **MyGene2** | 146 | 不一 | OMIM/孟德尔 | 社区 | 患者提交 | open with terms |
| **NORD 派生 ReDis-QA** | 1,360 QA / 205 | 205 | NORD（<200k US，FDA 阈值） | 来源描述 | MCQ + 开放 | open |
| **House M.D. benchmark** | ~302 | 33 类 | 叙述驱动 | 剧集 resolution | 电视剧叙述 | open（教育用途） |
| **NEJM CPC（MAI-DxO 使用）** | 304 | 多种（罕见/复杂） | 未明确 | 出版病例讨论 | 文本 | NEJM 访问 |

**主流罕见病定义**包括：(1) **Orphanet**（EU 患病率 ≤1/2000），被 RareBench、RareArena、DeepRare 使用；(2) **OMIM 孟德尔/染色体**疾病 ID，被 Phenopacket-Store、Reese et al.、Chimirri et al. 使用；(3) **NORD/FDA 阈值**（<200k US），被 ReDis-QA 使用；(4) **中国 CCRD**（中国第一批罕见病目录），被 PUMCH 使用，且对 `_zh` 框架是关键考虑。**可防御的 benchmark 应该把 Orphanet 作为主要骨架**（覆盖最广、社区共识最强），并显式提供到 OMIM 和 CCRD 的交叉映射，CCRD 用于中文语言层。金标准应在可能的情况下以 HPO 锚定（Phenopacket-Store 仍是最干净的开源数据），辅以医生标注的 EHR 病例（MIMIC-IV 切片，承认 PhysioNet 凭证访问对完全开源发布是个障碍）。

---

## 对你草稿的批判性评估

`rare_bias_harness_zh` 看起来把 **Bias** 和 **Family-aware** 评估并列为顶层结构 pillar 与诊断准确率并行。证据支持对每一项的明确差异化结论。

**Bias 作为顶层 pillar 不可防御。** 每个主流的整体性 AI benchmark — HELM、VHELM、MedHELM — 都使用 *scenarios × metrics 矩阵*，bias 和 fairness 是 7 个横切 metric 中的 2 个，**应用到每一个 scenario**，而不是各自独立的 pillar。Liang et al.（2022）显式这样设计 HELM，是为了确保"准确率以外的 metric 不会被边缘化"。MedHELM 的 5 个顶层类别是临床任务功能（决策支持、笔记生成等），不是 bias。把 bias 提升为 pillar 反而会*降低*其测量覆盖度，因为它会被从准确率任务中剥离。**当 bias *是* pillar 的时候，那项工作就是专门的公平性探针**：EquityMedQA（Pfohl et al., Nature Medicine 2024）是多 rubric 的对抗框架；HEAL（Schaekermann et al., eClinicalMedicine 2024）是把性能与差距挂钩的公平性 *metric*；Omiye et al.（npj Digital Medicine 2023）是 8 个场景的种族医学红队；Zack et al.（Lancet Digital Health 2024）是扰动式审计。**它们都不假装是整体性 benchmark。** 

**建议：把 bias 作为横切的评估透镜处理**，对遗传祖源、患病率层（记忆代理）、语言、性别、儿科/成人发病做显式分层。这能产生可执行的发现 — "模型 X 整体 R@1 70%，但非洲祖源病例只有 45%" — 这是单独的"Bias score"做不到的。

罕见病的关键 bias 与一般医学 QA 不同。**遗传祖源偏倚**是首要关切：gnomAD v2/v3 严重偏向非芬兰欧裔；100,000 Genomes Project 显示非洲参与者 prioritize 出的变异比欧洲人多 3 倍，且非欧洲变异更不易被分类为致病；Middle East Variation database 发现 53% 的高影响编码变异不在 gnomAD 中，39 个 ClinVar/HGMD 标记为 "rare" 的变异在中东人群中实际 MAF>1%。**训练数据记忆偏倚**是第二关切，由 2026 综述的 R²=0.55（R@1 与超罕见比例的反比关系）经验确立。**语言偏倚** — HPO 在根本上以英语为锚（尽管有 HPO Internationalisation Effort），中文、日文部分覆盖、原住民语言基本无覆盖 — 直接相关于 `_zh` 框架，给你一个真正的公平性贡献，而不是泛泛的种族/性别扰动。**儿科 vs 成人、性别/X 连锁、HPO 注释密度**完成完整图景。

**Family-aware 作为顶层 pillar 是有条件可防御的。** 在临床遗传学中，"family-aware" 推理涵盖 trio 分析（先证者+父母，诊断 yield 通常从单体的 ~22% 提升到 trio 的 30–34%）、遗传方式推理（AD/AR/XL/线粒体/印记，LIRICAL 显式使用）、pedigree 整合、de novo vs 遗传变异分类。**没有任何现有罕见病 LLM benchmark 把这作为一类轴评估** — RareBench、DeepRare、SHEPHERD、RareSeek-R1、RareAgents 全都缺乏 family-aware 评估 pillar。SHEPHERD 的输入是 HPO 词项和候选基因列表，不是 pedigree。DeepRare 把家族史作为输入特征但没有按其分层性能。Exomiser/LIRICAL 中的 trio 模式是工具的*配置选项*，不是 benchmark 维度。**这是真正的 gap、可防御的新颖性主张** — 但前提是你能凑齐足够的 trio/pedigree 病例。来源包括 DDD（Sci Rep s41598-024-53461-x 用了 305 个 trio）、100KGP、Phenopacket-Store 中带 pedigree block 的病例、MyGene2。**如果可达到病例数少于 100，建议把 family-aware 折回到诊断准确率作为分层（trio vs 单体 + MOI 是否正确作为指标），避免审稿时被诟病为"薄弱 pillar"。**

---

## 推荐的 benchmark 结构

### 三轴关系说明：Pillar × MetricType × Tier

这一节先把上面 metrics 全景里的 A/B/C/D 类、三层 Tier 分类、以及这里的 Pillar/能力 scenario 三者的关系讲清楚 — 它们**不是包含关系，而是三个正交的轴**。

- **Pillar（能力 scenario）回答"评什么任务"** — 给 agent 喂什么输入、期望它做什么任务。一个 pillar 就是一个独立的评估场景。
- **MetricType（A/B/C/D 类）回答"用哪类尺子打分"** — 按 metric 的**性质**分类：A 类标准准确率、B 类罕见病专属、C 类 Agent 专属、D 类忠实度。
- **Tier（1/2/3 层）回答"这把尺子优先级多高"** — 按报告优先级分类：Tier 1 必报、Tier 2 推荐、Tier 3 探索。

A/B/C/D 是**横向**切（按性质），Tier 1/2/3 是**纵向**切（按优先级），同一批 metric 的两种切法。同一个 metric 同时落在某个 A/B/C/D 类 × 某个 Tier 上。然后这个 metric 被应用到一个或多个 Pillar 上去打分。

**举一个具体例子让关系清楚**：DeepRare 的 95.4% 参考准确率 — 它属于 **Pillar 5（临床沟通与推理）** 这个任务、是 **D 类 metric**（性质上属于忠实度）、被列为 **Tier 2** 优先级（推荐报告而非必报）。

**MetricType × Tier 的二维表**（同一批 metric 的两种切法）：

| | A 类<br>标准准确率 | B 类<br>罕见病专属 | C 类<br>Agent 专属 | D 类<br>忠实度 |
|---|---|---|---|---|
| **Tier 1<br>必报** | R@1/3/5/10、Median Rank、HPO 抽取 P/R/F1 | Gene Top-k、患病率分层准确率、HPO-only vs HPO+Gene 分层、未见疾病 holdout R@k | Task Success Rate | — |
| **Tier 2<br>推荐** | — | — | Tool Selection Acc、Tool Call Correctness、推理步数、token 成本、Cost-Normalized Accuracy、pass^k（k=4 或 8）、Progress Rate、ECE、Brier、Confidence AUROC、Information Gain per Turn | Reference/Citation Accuracy（DeepRare 风格，专家评审 100+ 病例） |
| **Tier 3<br>探索** | — | 子组分层（祖源、性别/X 连锁、儿科/成人、语言、HPO 密度） | AgentProcessBench 风格步骤评分、CoT 忠实度、混沌工程工具失败鲁棒性（Recovery Rate、Catastrophic Success）、人口扰动鲁棒性、采样一致性不确定性 | FActScore 风格的原子事实验证（对 UMLS/Orphanet/HPO/OMIM） |

### 5 个能力 Pillar（scenario）

1. **表型抽取** — EHR/自由文本 → HPO 词项。对中文临床文本做显式覆盖以服务 `_zh` 框架。可与 RareBench Task 1、PhenoTagger、RAG-HPO 惯例对比。
2. **差分诊断（仅表型）** — RareBench Task 4 的对应物，罕见病评估的核心场景。
3. **基因型感知诊断** — 变异 + 表型 → 致病基因/疾病。Exomiser/LIRICAL/AI-MARRVEL 的能力领域，LA-MARRVEL 是 LLM 前沿。
4. **Family-aware 诊断** — trio/pedigree/MOI 推理。如果能凑齐 ≥150–300 个 trio 病例，保留为独立 pillar；否则折入 pillar 3 做分层。
5. **临床沟通与推理** — 推理轨迹可追溯性、引用忠实度（DeepRare 95.4% 参考准确率 benchmark 风格）、患者解释质量。

### Pillar × MetricType 应用矩阵

下表展示每个 pillar 上需要跑哪些类别的 metric。**√ 表示该 pillar 必跑该类 metric**，"—" 表示该类不适用或不优先。每个格子里再细分到具体 Tier 1/2/3 的 metric（参见上面的二维表）。

| | A 类<br>准确率 | B 类<br>罕见病专属 | C 类<br>Agent 专属 | D 类<br>忠实度 |
|---|---|---|---|---|
| **Pillar 1**<br>表型抽取 | √ <br>(P/R/F1) | — | √ <br>(工具用对、Cost) | √ <br>(原子事实验证) |
| **Pillar 2**<br>仅表型 DDx | √ <br>(R@k, MR) | √ <br>(患病率分层、holdout) | √ <br>(pass^k, Cost, Progress) | — |
| **Pillar 3**<br>基因型感知 DDx | √ <br>(R@k) | √ <br>(Gene Top-k, MOI 分层) | √ <br>(pass^k, 工具调用图) | √ <br>(Reference Acc) |
| **Pillar 4**<br>Family-aware | √ <br>(R@k) | √ <br>(MOI 正确率、trio vs 单体) | √ <br>(pass^k) | — |
| **Pillar 5**<br>临床沟通/推理 | — | — | √ <br>(步骤评分、CoT 忠实) | √ <br>(Reference Acc 95.4%、FActScore) |

横切的 **Bias/公平性分层** 不单独占一列，而是作为评估透镜应用到**每个 pillar 的每个 A/B/C/D 类 metric 上**：报告按遗传祖源层（欧裔/东亚/非裔/拉丁/南亚/中东）、年龄层、性别/X 连锁、语言（英文/中文叙述）、患病率层（1:1k / 1:1M / 超罕见 — 训练数据记忆代理）、HPO 注释密度等子组分层的性能差距。这种处理方式与 HELM/MedHELM 一致 — bias 不是独立 pillar，而是横切透镜。

### Leaderboard 必备 baseline

DeepRare、RareAgents、MAI-DxO、MDAgents、RADAR 是最强的 5 个 agent baseline；RDMA 和 MedAgents 增加架构多样性；LA-MARRVEL 提供 RAG-rerank 对照；GPT-4o、Claude-3.7、Gemini-2.5、o3、Qwen3 单模型作为 LLM 控制；SHEPHERD、Exomiser、LIRICAL、AI-MARRVEL、PhenoBrain、RareSeek-R1、DxGPT 作为经典/非 agent baseline 提供背景。

### 必备数据集基座

Phenopacket-Store 作为干净的结构化骨架（CC-BY）；RareArena 作为规模层（CC-BY-NC-SA，注意非商用）；MIMIC-IV-Ext-Rare 与 MIMIC-RD 切片用于在 PhysioNet 凭证下的噪声真实 EHR 评估；显式的 **cutoff 后 held-out 未见疾病 split** 回应 2026 综述对所有现有数据集的数据泄漏标记 — 这本身就是可发表的贡献。

---

## 可防御性论证

最可能的 peer review 攻击是"这就是 RareBench++"。最强的防御依赖 5 个独立主张，每一个都被上面的调研经验支撑。

**主张 1：现有罕见病 benchmark 在分类上不是 agent benchmark。** 9 个专门 benchmark 中 8 个用 prompting 或 RAG 评估 base LLM；零个把工具 API、多轮信息引出、成本预算、推理轨迹作为可评估表面暴露出来。RareBench 的 4 个任务（抽取、筛查、常见 vs 罕见、DDx）是静态 input→output。Agent benchmark 需要*交互式环境* — 这是范畴差异而非渐进差异，类似代码生成中 SWE-Bench 与 HumanEval 的区别。

**主张 2：agent 系统存在但缺少共享评估基座。** DeepRare 在 9 个临时数据集上评估（部分自建）；RareAgents 自建 MIMIC-IV-Ext-Rare；RDguru 用 238 个出版病例；Almasoud 用 302 个叙述病例。**每篇 agent 论文都自建 benchmark，因为没有共享 benchmark 存在。** 这正是你要填的精确 gap。

**主张 3：2026 系统综述独立验证了 gap。** 跨 15 项研究、39,529 病例，agent 增强系统达到 R@1 = 52.5% 对 LLM 单体的 35.4%（p=0.004）；然而*所有 19 个系统-数据集条目都被标记为高数据泄漏偏倚风险*，且没有一个使用按患病率分层的评估、未见疾病 holdout 或 agent 过程 metric。仅就这些理由，回应这些缺口的 benchmark 就是可发表的。

**主张 4：metrics 创新具体而非抽象。** DeepRare 的 95.4% 参考准确率是唯一已发表的罕见病忠实度 metric；pass^k 从未应用到罕见病；工具失败鲁棒性从未在罕见病上测量过；患病率分层被呼吁但从未实现。每一项都是离散贡献。

**主张 5：语言与公平性框架是实质性的而非装饰性的。** HPO 英语锚定问题已被记录（HPOIE、日文部分努力）；Chimirri et al.（eBioMedicine 2025）展示非英语降级；`_zh` 中文语言层把 EquityMedQA 不覆盖的真实 bias 维度操作化。这同时把工作定位到 *npj Digital Medicine*（公平性强调）和 *ICLR D&B*（多语言强调）。

**论文里需要主动处理的关键 caveat**：如果不把 "Bias" pillar 重构为横切透镜，熟悉 HELM/MedHELM 的 reviewer 会理直气壮地指出整体性 benchmark 不会把 bias 提升到 pillar 地位。重构后论证也更强 — "我们的 bias 评估融入到每个 scenario 中"是比"我们有一个 bias pillar"更严谨的主张。如果你能凑齐 ≥150 个 trio 病例，family-aware 作为 pillar 站得住，并成为相对 SHEPHERD、DeepRare、RareAgents（都不评估这个维度）的干净新颖性主张。如果 trio 病例稀缺，把 family-aware 降为子任务避免薄弱 pillar 批评。**完成这两个结构修订**后，benchmark 就从"RareBench++"转变为类别上不同的贡献，填补已记录的 gap，而 reviewer 在医学 AI 和 ML 两个会场都应该认识到这一点。

## 结论

Agent 导向的罕见病 benchmark 方向可行：gap 真实存在（9 个现有 benchmark 中 8 个是 LLM-only），有足够的评估对象（8–11 个不同 agent 方法，以 DeepRare、RareAgents、MAI-DxO、MDAgents、RADAR 为锚），从 τ-bench、AgentBoard、MedAgentBench、AgentClinic 移植过来的 metrics 工具包已经成熟。**你应该推进** — 但在写稿前要做两个结构修订。**Bias 必须从 pillar 移为横切透镜**，对应 HELM/MedHELM 先例并产生更可执行的发现。**Family-aware 仅在 trio/pedigree 数据足够时保留为 pillar**，否则折入准确率作为分层。配合三轴 metrics 分类法和 held-out 未见疾病 split，benchmark 就从"RareBench++"上升到一个填补已记录 gap 的范畴上不同的贡献，医学 AI 和 ML 两边的 reviewer 都应该承认。