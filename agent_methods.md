# 罕见病 Agent Benchmark 数据集方案

## 决策上下文

- **Timeline：1 个月**（紧）
- **已拥有**：MIMIC-IV（PhysioNet **Credentialed 全权限**，可访问完整数据集，不是 demo 子集）
- **正在申请（不阻塞主线实验）**：MyGene2、DDD
- **目标**：在 1 个月内用立即可用的数据完成主线实验，MyGene2/DDD 到位后作为补充实验或 v2 加入
- **核心论证轴**：(a) 真实罕见病覆盖、(b) 多样性（含中文）、(c) 防御"训练数据泄漏"批评的 holdout split
- **评估对象**：以 agent 系统为主体，保留 **2 个 LLM 作为 no-scaffolding 控制组**用于论证 agent scaffolding 的增量价值（详见后文"评估系统阵容"小节）

---

## 最终数据集组合（v1，1 个月 timeline）

总评估规模约 **60,000 例 / 5,000+ 疾病**，分四层：

### 第一层 — 结构化 phenotype 主骨架

> 用途：Pillar 2（仅表型 DDx）/ Pillar 3（基因型感知 DDx）的核心评估，提供干净金标准

| 数据集 | 规模 | 疾病定义 | 访问 | 状态 |
|---|---|---|---|---|
| **Phenopacket-Store** (Danis et al., HGG Adv 2025) | 7,552 例 / 481 病 | OMIM 孟德尔/染色体 | CC-BY，直接下载 | ✅ 立即可用 |
| **RareBench**（5 子集合集，Chen et al. KDD'24） | ~2,764 例 / ~700 病 | Orphanet + OMIM + CCRD | Apache 2.0，直接下载 | ✅ 立即可用 |
| └─ RAMEDIS | 624 例 / 74 病 | 罕见代谢 | | |
| └─ MME (Matchmaker Exchange) | 40 例 / ~40 病 | 孟德尔 | | |
| └─ HMS (Hannover) | 88 例 / 39 病 | Orphanet | | |
| └─ LIRICAL test set | 370 例 / ~370 病 | OMIM/Orphanet | | |
| └─ **PUMCH-ADM**（中文层关键） | 75 例 / 16 病 | 中国 CCRD | | |

**为什么必选 RareBench**：KDD'24 已建立社区基准。**必须复现 RareBench 上的数字**，否则 reviewer 会问"为什么不和 RareBench 比"。

### 第二层 — 真实 EHR 噪声层

> 用途：Pillar 1（表型抽取）/ Pillar 2（仅表型 DDx）在真实场景的鲁棒性证明，回应"case report 不是真实数据"批评

| 数据集 | 规模 | 疾病定义 | 访问 | 状态 |
|---|---|---|---|---|
| **MIMIC-IV 罕见病切片**（自建） | ~1,875 例 / ~355 病 | ICD→Orphanet 映射 | PhysioNet Credentialed（全权限） | ✅ 已有访问，可直接构建 |
| **MIMIC-RD 标注子集**（复用 arXiv 2601.11559） | 145 例 | LLM 挖掘 + 4 名标注员确认 | 同上（复用其公开流水线代码） | ✅ 流水线公开可复用 |

**关键操作**：不能直接拿 MIMIC ICD 长尾当罕见病。必须做：
- 用 Orphadata 交叉引用文件做 ICD→Orphanet 映射（覆盖率 ~50% Orphanet 编码）
- 对 ICD 伞码（如 Q87.8）下的病例做 NLP 召回（参考 MIMIC-RD 流水线）
- 在论文 method 里显式报告映射类型（Exact / NTBT / BTNT）和覆盖率

### 第三层 — 规模 + holdout 层

> 用途：大规模评估 + 构造 held-out 未见疾病 split

| 数据集 | 规模 | 疾病定义 | 访问 | 状态 |
|---|---|---|---|---|
| **RareArena (RDS)** (Lancet Digit Health 2025) | 49,760 例 / 4,597 病（Orphanet 45.6%） | Orphanet | CC-BY-NC-SA，GitHub 直接下载 | ✅ 立即可用 |
| **RareArena (RDC)** | 22,901 例 / 3,522 病 | Orphanet | 同上 | ✅ 立即可用 |

**注意**：CC-BY-NC-SA 限制商用 — 学术论文 OK，但商业部署需另行授权。在论文里需要显式声明这一点。

### 第四层 — Cutoff 后 holdout split（关键防御层）

> 用途：回应"训练数据污染"批评，是 2026 系统综述指出的关键 gap

| 数据集 | 规模 | 来源 | 访问 | 状态 |
|---|---|---|---|---|
| **PMC OA Cutoff-after Novel Disease Split**（自建） | 目标 ~200 例 | 2024-01 之后 PMC 开放获取 case report | 公开 FTP/API | 🟡 需要 1-2 周流水线 + 人工核验 |

构建流程详见下方专门小节。

---

## 罕见病定义声明（论文 method 必备段落）

```
本研究采用 Orphanet 阈值（EU ≤1/2,000，Regulation (EC) No 141/2000）
作为主要罕见病定义。具体到子数据集，疾病锚定如下：

- Orphanet 锚定：RareArena (RDS/RDC), RareBench 子集 (RAMEDIS, HMS),
  MIMIC-IV 罕见病切片
- OMIM 孟德尔锚定：Phenopacket-Store, RareBench (LIRICAL test set, MME)
- 中国 CCRD（国家卫健委 207 病目录）锚定：PUMCH-ADM
- FDA <200,000 阈值：作为 US-centric 数据的次级验证

为防御"长尾 ≠ 罕见病"的方法学批评（Aymé 2015, Cavero-Carbonell 2020），
所有 EHR 派生数据（MIMIC-IV）通过 Orphadata 交叉引用文件做 
ICD→Orphanet 映射；对 ~50% 缺乏直接 ICD-10 映射的 Orphanet 编码，
使用 NLP 流水线（参考 Dong et al. 2023, MIMIC-RD 2026）从临床
自由文本召回隐藏病例。

所有 cutoff 后未见疾病 split 病例由 PMC OA 中 2024-01-01 之后
出版的 case report 派生，确保不在主流 LLM 训练数据中出现。
```

---

## 数据集组合的论证逻辑（写入 introduction / related work）

| 现有 benchmark 的 gap | 我们的方案如何回应 |
|---|---|
| RareBench 仅评估 base LLM 静态 input→output | 复用 RareBench 数据 + 加上 agent 评估维度（保持可比 + 拓展新维度） |
| RareArena 规模大但仅 Orphanet 单一定义 | 三定义并行（Orphanet / OMIM / CCRD），中文层显式 |
| 所有 benchmark 数据泄漏风险高（系统综述 2026） | 显式 cutoff 后 PMC OA holdout split |
| MIMIC 系列直接用 ICD 长尾，不是真正罕见病 | Orphanet 映射 + NLP 召回，复用 MIMIC-RD 流水线 |
| 中文罕见病评估仅 PUMCH-ADM 75 例 | 保留 PUMCH-ADM 作为中文金标准；从 PMC OA 中文期刊补 holdout |
| Family-aware 评估完全缺失 | v1 折入 Pillar 3 做 trio vs 单体分层；v2（MyGene2/DDD 申请到位后）独立成 Pillar |

---

## Cutoff 后 Novel Disease Split 自建方案

### 为什么这一层是论文最强卖点

2026 年 3 月 medRxiv 系统综述指出：所有 19 个现有 LLM 罕见病评估都被标记为**高数据泄漏偏倚风险**。这是 reviewer 必问的问题。我们做这一层就直接回应了这个 gap。

### 全自动流水线 + 最后人工核验

PMC 是公开的，NIH 提供 Open Access 子集的 FTP 和 API（**完全合规可批量下载**）。整个流程如下：

```
步骤 1：PMC OA Bulk Download         [全自动]
  - NIH FTP: https://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_bulk/
  - 过滤条件：publication_date >= 2024-01-01
  - 文章类型：case-report, clinical-case
  - 输出格式：.nxml 或 .tar.gz
  - 预计原始候选量：数千-数万篇

步骤 2：关键词 + MeSH 过滤            [全自动]
  - MeSH: "Rare Diseases", "Genetic Diseases, Inborn"
  - 标题/摘要关键词：rare, novel, undiagnosed, syndrome
  - 输出：~1,000-3,000 篇候选

步骤 3：LLM 自动抽取                   [全自动]
  - 用 GPT-4o 或 Claude 抽取每篇文章的：
    * 最终诊断（disease/syndrome name）
    * HPO 表型词项
    * 患者基本信息（年龄、性别）
    * 是否有家族史/trio 数据
  - 输出：结构化 JSON

步骤 4：Orphanet/OMIM 映射 + 去重      [全自动]
  - 自动映射诊断到 Orphanet ID 和 OMIM ID
  - 去除主流 LLM 训练数据中已存在的疾病
    （通过对比 Phenopacket-Store / RareBench / RareArena 的疾病列表）
  - 去除同一病例不同期刊的重复报告（基于 author + 临床特征哈希）
  - 输出：~300-500 篇候选

步骤 5：人工核验最终 ~200 例           [需人工]
  - 由医学背景标注员（学生 1-2 名）确认：
    * 诊断是否明确（排除 "suspected" / "differential includes"）
    * 抽取的 HPO 表型是否准确
    * 是否真的是 cutoff 后病例（出版日期 vs 病例发现日期）
  - 每例约 5-10 分钟，200 例约 1-2 周
```

### 为什么第 5 步必须人工

这是 benchmark 的**金标准**，不是训练数据。如果用 LLM 自动确认诊断，就等于"LLM 出题 → LLM 评分 → LLM 学习"循环论证，reviewer 一定攻击。

具体的人工判断点：
1. **诊断不明确的过滤**：case report 里常有 "suspected", "final diagnosis was X but Y could not be ruled out", "differential diagnosis included A, B, C" 等表述。LLM 容易把鉴别诊断里的疾病当主诊。
2. **HPO 表型精度**：LLM 可能漏掉文中关键表型，或把鉴别诊断中的表型当主诊表型。
3. **Cutoff 时间核验**：出版日期晚于 cutoff，但病例本身可能更早就在会议摘要、preprint 中出现过 — 需要查作者其他出版物。

**这其实就是 RareArena、RareBench 的标准做法** — 都是"自动抽取 + 人工核验"，不是手工从零开始。

### 1 个月内能否完成

- 步骤 1-4：脚本开发 1 周（其中包括 prompt 调试和 mapping 表准备）
- 步骤 5：人工核验 1-2 周

**结论：1 个月内完整流水线可跑完，得到 ~200 例 cutoff 后 holdout split。**

如果时间真的非常紧，可以先做 **mini 版 ~50 例**作为方法验证，论文中标注 "expanded to 200 in camera-ready" 或保留为 v2 update。

---

## v2 扩展计划（MyGene2 / DDD 到位后）

| 数据集 | 申请方式 | 周期 | 用途 |
|---|---|---|---|
| **MyGene2** | mygene2.org 注册 + 同意条款 | 几天 | Family-aware Pillar 4 — 提供 trio/pedigree |
| **DDD（Deciphering Developmental Disorders）** | EGA / 项目数据访问委员会，提交研究计划 | 2-6 周审批 | Family-aware Pillar 4 — 305+ trio（参考 Sci Rep s41598-024-53461-x 用法） |

**v1 vs v2 的关键差别**：
- v1：Family-aware 折入 Pillar 3 做 trio vs 单体分层（1 个月版本）
- v2：MyGene2 + DDD 到位后，trio 病例数 ≥150-300，Family-aware 升级为独立 Pillar 4

---

## 不纳入 v1 的数据集及理由

| 数据集 | 不纳入原因 |
|---|---|
| **UDN (Undiagnosed Diseases Network)** | dbGaP 申请 3-6 个月，需要美国机构合作。可作为 future work，或联系 SHEPHERD（Zitnik Lab）/ Shyr et al. (Vanderbilt) 合作做 external validation |
| **100,000 Genomes Project** | Genomics England Research Environment 受控访问，2-4 个月审批，需在 GE 安全环境内分析。Timeline 不允许 |
| **AI-MARRVEL Buchanan 队列** | 各自受控访问 |
| **eMERGE** | 受控访问，且非罕见病专用 |

---

## 时间线（1 个月版本）

| 周次 | 任务 |
|---|---|
| **Week 1** | 下载 + 整理：Phenopacket-Store, RareBench, RareArena 三个开源数据集；MIMIC-IV ICD→Orphanet 映射脚本搭建；申请 MyGene2 / DDD（不阻塞主线） |
| **Week 2** | MIMIC-IV 罕见病切片构建完成 + 验证；PMC OA cutoff 后下载 + 步骤 1-4 流水线开发 |
| **Week 3** | Cutoff holdout 步骤 5 人工核验启动；agent baseline 在 RareBench / Phenopacket-Store / RareArena 上跑 baseline |
| **Week 4** | MIMIC-IV 切片上 baseline + 整合所有结果；写 method 数据集小节 |

---

## 审稿防御点（提前准备）

| 可能的审稿质疑 | 我们的回应 |
|---|---|
| "数据集都是公开的，新意何在？" | (1) 第一次把这些数据组合成 agent 评估基座；(2) ICD→Orphanet 映射 + NLP 召回的 MIMIC-IV 切片是新构造；(3) Cutoff 后 PMC OA holdout split 是新构造，回应 2026 综述的数据泄漏 gap |
| "RareArena 是 NC 协议，能用吗？" | 学术研究使用合规。论文里显式声明并感谢原作者，商业部署部分作为 future work |
| "MIMIC 是 ICU 数据，不代表罕见病人群？" | 这正是为什么我们用多层数据。MIMIC 切片仅作为真实 EHR 噪声层，主结构层用 Phenopacket-Store；论文里显式承认 MIMIC 反映 ICU 转诊模式 |
| "Cutoff 后 200 例够不够？" | 这是首批 — 已公开发布构建流水线，社区可扩展。和 RareBench 的 75 例 PUMCH-ADM 量级相当 |
| "为什么不申请 UDN/100KGP？" | Timeline 限制，作为 future work / external validation 已规划 |
| "中文层只有 75 例 PUMCH-ADM 太少？" | 已从 PMC OA 中文期刊补充至 holdout split；CCRD 锚定的疾病列表覆盖完整 |
| "MIMIC-IV 的访问权限和合规性？" | 团队拥有 PhysioNet Credentialed 全权限（含 CITI Data or Specimens Only Research 培训认证 + DUA 签署），可访问完整 MIMIC-IV 数据集。所有处理脚本和派生数据集（MIMIC-IV 罕见病切片）将在论文 supplement 中提供，供其他持有 credentialed 权限的研究者复现 |

---

## 评估系统阵容（v1，10 个系统）

### 原则

benchmark 主体是 **agent 系统**。不把 LLM 当独立 baseline，但保留 **2 个 LLM 作为 no-scaffolding 控制组**，用于论证 "agent scaffolding 带来的增量价值"（这是 reviewer 必问的 — RareBench KDD'24 与 DeepRare Nature 2026 都做了这个对照）。

注意 LLM 仍然以**两种身份**出现在评估中：
1. **作为 agent 的 backbone**（绕不开 — MDAgents、DeepRare 等 agent 本身需要 LLM 后端）
2. **作为 no-scaffolding 控制组**（独立行，仅 2 个）

### 阵容（10 个系统）

| 类别 | 系统 | 角色 | 备注 |
|---|---|---|---|
| **LLM 控制组（2）** | DeepSeek V3.2 | no-scaffolding baseline（便宜端） | 已在 *Nature Medicine* 2025 罕见病评估中验证 |
| | GPT-5 | no-scaffolding baseline（高端） | OpenAI 当前旗舰，$1.25/$10 |
| **通用医学 Agent（4）** | MDAgents | 自适应多 agent 协作 | NeurIPS 2024 oral，外部已多次重新实现 |
| | MedAgents | 多学科角色扮演 | ACL 2024 Findings，最简单的多 agent baseline |
| | AgentClinic | 含患者模拟器的多模态 agent | MIT 协议，仓库内含 NEJM 病例 |
| | MAI-DxO（社区版） | 8 角色 panel + 顺序检查决策 | 用 Open-MAI-Dx-Orchestrator 移植版（53⭐ MIT），微软官方未发布 |
| **罕见病专用 Agent（4）** | DeepRare | 中央 host + 40+ 工具 + 反思 | Nature 2026，当前 SOTA，220⭐ |
| | PhenoBrain | ALBERT + 5 模型集成 | npj Digital Medicine 2025，经典 NLP baseline 对照 |
| | RDMA | 专门挖掘子 agent | 成本高效（10× 便宜），EHR 抽取 |
| | VC-RDAgent | 离线双曲-语义 HPO embedding | 隐私保护对照，无需付费 API |

每个 agent 用 **一个便宜 backbone（DeepSeek V3.2）+ 一个高端 backbone（GPT-5 或 Claude Sonnet 4.5）** 跑，以圈定性能包络。

### 关于 Gemini / AMIE / Med-Gemini / MAI-DxO 的可访问性澄清

为避免论文 method 部分被 reviewer 质疑"为什么不评 X"，把这几个常被提到的系统的访问状态显式记录在这里。

**✅ Gemini 系列 — 可用**

Gemini 2.5 Pro 和 2.5 Flash 都有公开 API（Google AI Studio + Vertex AI），可以作为任何 agent 的 backbone 使用。如需把 Gemini 当成第 3 个 LLM 控制组也是可行的（成本：Gemini 2.5 Flash 仅 $0.30/$2.50，性价比高）。

**❌ AMIE — 不可用**

AMIE（Tu, McDuff et al., Nature 2025 "Towards conversational diagnostic AI"）是 Google DeepMind 内部基于 PaLM-2 的微调模型，专门做问诊对话。**Google 从未发布权重，也没在 Vertex AI 上 host**，论文里只发了基准结果和 OSCE 评估方法论。外部研究者唯一的接触方式是和 Google DeepMind 签署合作协议。论文中可以引用其已发表数字作为参照（"AMIE 在 NEJM CPC 上 Top-10 = 59.1%"），但不能在自己的 benchmark 上跑它。

**❌ Med-Gemini — 不可用**

Med-Gemini（Saab et al., arXiv 2404.18416）是 Gemini 在医学语料上微调的版本。Google 的衍生品 **MedLM** 在 Vertex AI 上提供，但是**严格 allowlist 制 — 需申请、Google 审核通过才能使用，且只对企业客户开放，不对学术研究者开放**。Med-Gemini 本身从未作为 API 产品发布。

**⚠️ MAI-DxO 官方版 — 未发布；用社区版**

MAI-DxO（Nori et al., arXiv 2506.22405）的论文已发，但**微软只发了论文，没发代码、没发 API**。社区做了一个移植版叫 **Open-MAI-Dx-Orchestrator**（53⭐，MIT 协议）按论文重新实现了架构。我们使用的是社区版，不是微软官方实现。**论文 method 部分必须显式声明**："We use the community port of MAI-DxO (Open-MAI-Dx-Orchestrator); the official Microsoft implementation has not been released as of [submission date]." 这样可以避免被 reviewer 质疑。

### 阵容外的强候选（按需添加）

如果 timeline 或预算允许，下列系统是性价比最高的备选：

- **Gemini 2.5 Flash 作为第 3 个 LLM 控制组**：$0.30/$2.50 极便宜，加进来几乎零额外成本，能再多覆盖一个生态。
- **Claude Sonnet 4.5 作为第 3 个 LLM 控制组**：如果想覆盖三大商用 LLM 生态（OpenAI / Anthropic / 开源），加这个就齐了。
- **MedAgentBoard 作为 meta-harness 参照**：捆绑了 MDAgents+MedAgents+ColaCare+ReConcile，可以一次跑出 4 个 baseline 的对照矩阵。但因为它的捆绑 baseline 与已选的 MDAgents/MedAgents 重叠，信息增益有限。
- **LA-MARRVEL（仅基因组子集）**：当 v2 阶段 DDD/MyGene2 到位后值得加入，因为它专门做基因优先排序。

### 成本与时间线（10 个系统版本）

按 6 万病例量级，配上 batch API 50% 折扣 + prompt cache 90% 折扣：

| 类别 | 系统数 | 估计 token 总量 | 估计成本（混合 backbone） |
|---|---|---|---|
| LLM 控制组（裸调用） | 2 | ~300M | ~$200–600 |
| 通用医学 Agent | 4 × 2 backbone | ~12B | ~$3,000–6,000 |
| 罕见病 Agent | 4 × 2 backbone | ~24B | ~$5,000–10,000 |
| **总计** | **16 个跑次** | ~36B | **$8,000–17,000** |

相比上一版 16 个系统的 $12K–$25K，砍掉 6 个 LLM 后**成本下降约 30–35%，且阵容更聚焦**。

---

## 待确认事项

- [ ] PMC OA cutoff 后 200 例的人工核验由谁负责？（学生 / 标注员）
- [ ] 是否需要医学背景的 reviewer 做最后抽样验证（约 20 例）以确保金标准质量
- [ ] MyGene2 / DDD 申请提交时机和负责人
- [ ] RareArena CC-BY-NC-SA 的具体 license 措辞是否需要法务核查
- [ ] 是否把 Gemini 2.5 Flash 加为第 3 个 LLM 控制组（额外成本 <$200，能多覆盖一个生态）
- [ ] RareAgents 是否能联系作者拿到代码，决定是否纳入第 5 个罕见病 agent