# 第一轮细节方案(Round 1 Detailed Plan)

> **范围**:从今天起到"主实验 Step 2 可以开跑"之间的所有动作 — 对应 `plan.md` Step 0 前置 + Step 1 基础跑。
>
> **设计原则**:最大化并行,把人(人工核验、申请审批)和外部依赖(数据下载、agent 代码可用性)推到关键路径之外。

---

## 0. 已固化的决策(第一轮回应之后)

| 项 | 决策 |
|---|---|
| **EMNLP 时间限制** | 不考虑 — 按 200 例完整 holdout 做 |
| **API 预算** | 不限制 — 双 pass(gold-HPO + 端到端)都跑,Backbone × Scaffolding 完整 2×N 网格跑 |
| **PMC OA 200 例人工核验** | 有人,不阻塞 |
| **PUMCH-ADM 中文** | 假设未授权 — 中文层完全依赖 PMC OA 中文期刊子集 + RareBench 公开部分 |
| **MyGene2 / DDD** | 立即提交申请(见 `applications.md`);v1 Pillar 4 折入 Pillar 3 做 trio vs 单体分层 |
| **LLM 控制组阵容** | 3 个:DeepSeek V3.2(便宜端)、GPT-5(高端)、**Gemini 最新 Flash GA 版本**(覆盖第 3 个生态) |
| **文档整理** | `dataset.md` 已删除(是 `agent_methods.md` 的真子集) |

### 仍待你最后确认

- [ ] **Gemini Flash 具体版本**:你说的"3 Flash"是否已 GA。我的知识截止 2026-01,知道的最新是 Gemini 2.5 系列。**建议你选 Google AI Studio 当前的最新 GA Flash 模型**(避免 preview/experimental,因 EMNLP reviewer 会查可复现性),把模型 ID + 训练 cutoff 日期 + 价格告诉我,我再固化进文档
- [ ] PMC OA 人工核验**具体由谁**做(姓名/邮箱,论文 Author Contribution 需要)
- [ ] MyGene2 / DDD **申请负责人**(见 `applications.md` 末尾的 checkbox)

---

## 1. 同步并行工作流(P0 — 今天就启动)

7 条工作流彼此**完全独立**,可以同时推进。每条标了"产出"和"所有者位置"(代码层 / 人工层 / 申请层)。

### Stream A — 三大开源数据集下载与整理 【代码层】

**目标**:把 Phenopacket-Store / RareBench / RareArena 全量拉到本地,统一目录结构。

```
数据 root: /Users/yutianzhao/Desktop/RDAgentBenchmark/data/
├── phenopacket_store/      # CC-BY, 7,552 例
├── rarebench/              # Apache 2.0, 5 子集
│   ├── ramedis/
│   ├── mme/
│   ├── hms/
│   ├── lirical/
│   └── pumch_adm/          # 中文,75 例 — 状态待定(假设未授权)
└── rarearena/              # CC-BY-NC-SA, RDS + RDC
    ├── rds/                # 49,760 例
    └── rdc/                # 22,901 例
```

**产出**:三个数据集本地完整副本 + 每个的原始 schema 字段清单(用于设计规范案例对象)
**预计耗时**:1-2 天
**关键卡点**:RareArena 体积大,需要确认本地磁盘空间(预估 5-15 GB)

### Stream B — 规范案例对象 schema 设计 【代码层】

**目标**:定义"所有 agent 都吃同一种输入"的 canonical case object,作为下游所有 adapter shim 的契约。

**初稿 schema**(Phenopacket-style,JSON):
```json
{
  "case_id": "PS_2024_00123",
  "source_dataset": "phenopacket_store",
  "language": "en",
  "demographics": {
    "age_onset_years": 3.0,
    "sex": "M",
    "ancestry": "European"
  },
  "free_text_vignette": "A 3-year-old boy presented with...",
  "gold_hpo_terms": ["HP:0001250", "HP:0001263", ...],
  "vcf_path": "/data/.../patient.vcf.gz",   // optional
  "family": {                                 // optional
    "pedigree_json": {...},
    "trio_mode": true,
    "moi_label": "AR"
  },
  "gold_label": {
    "omim_id": "OMIM:300100",
    "orphanet_id": "ORPHA:79277",
    "disease_name": "Adrenoleukodystrophy"
  },
  "metadata": {
    "publication_date": "2024-05-12",   // for cutoff filtering
    "license": "CC-BY"
  }
}
```

**产出**:`schema/canonical_case.schema.json` + Python pydantic model + 验证器
**预计耗时**:1-2 天(草稿) + 1 天(基于实际数据集字段调整)
**依赖**:需要 Stream A 部分完成后才能验证 schema 覆盖度

### Stream C — MIMIC-IV 罕见病切片构建 【代码层 + 数据】

**目标**:从你的 PhysioNet credentialed 全权限,构建 ~1,875 例 / ~355 病的罕见病切片。

**MIMIC-IV 数据如何提供给我**(关键):

我**不能**直接拿 MIMIC-IV 完整数据 — PhysioNet DUA 禁止把 credentialed 数据分享给非 credentialed 第三方(包括 AI 模型/服务)。**正确做法**:

```
1. 你在自己机器上下载 MIMIC-IV(你已有 credentialed access)
2. 解压到本地:/Users/yutianzhao/Desktop/RDAgentBenchmark/data/mimic-iv-raw/
   (这个目录我能读,但数据物理上只在你本机)
3. 我写的所有处理脚本都本地运行,数据不出你的机器
4. 派生的"罕见病切片"也存在本地;论文 supplement 里发布的是
   *构建脚本*,其他 credentialed 用户在自己机器上跑同样脚本得到同样切片
```

**你需要下载的具体表(MIMIC-IV v3.1+)**:
| 模块 | 文件 | 必要性 | 大小估计 |
|---|---|---|---|
| `hosp/` | `admissions.csv.gz` | 必须 | ~30 MB |
| `hosp/` | `patients.csv.gz` | 必须 | ~3 MB |
| `hosp/` | `diagnoses_icd.csv.gz` | 必须 | ~150 MB |
| `hosp/` | `d_icd_diagnoses.csv.gz` | 必须 | ~2 MB |
| `note/` | `discharge.csv.gz` | 必须(自由文本主体) | ~3-5 GB |
| `note/` | `radiology.csv.gz` | 可选(影像报告) | ~5 GB |

**总下载量**:约 8-13 GB

**额外 metadata 资源**(公开,不需 credentialed):
- Orphadata ICD↔Orphanet 交叉引用文件:https://www.orphadata.com/data/xml/en_product1.xml
- HPO ontology:http://purl.obolibrary.org/obo/hp.obo
- OMIM↔Orphanet 映射:https://www.orphadata.com/data/xml/en_product1.xml

**产出**:
1. ICD→Orphanet 映射表(Exact/NTBT/BTNT 标注)
2. NLP 召回流水线(对 ICD 伞码下的病例从 discharge.csv 召回隐藏病例)
3. ~1,875 例 / ~355 病的罕见病切片 + per-case canonical_case.json
4. MIMIC-RD 145 例标注子集复用(从 arXiv 2601.11559 公开流水线)

**预计耗时**:1 周(脚本开发 3-4 天 + 跑全量映射 + NLP 召回 + 验证)

### Stream D — PMC OA cutoff 后 holdout 流水线 【代码层 + 人工层】

**目标**:200 例 cutoff 后(2024-01-01 之后)novel disease case 的 holdout split。

**子步骤分工**:
- **步骤 1-4(全自动)**:bulk download + MeSH 过滤 + LLM 抽取 + Orphanet 映射 — 代码层,1 周
- **步骤 5(人工核验)**:人工层,1-2 周,有人专门负责

**为什么这是 Round 1 必启动**:人工核验是关键路径上最长的串行段,**步骤 1-4 跑出 300-500 候选必须在 Stream D 第 1 周末完成**,人工核验才能 Week 2-3 启动并赶在主实验前完成。

**预计耗时**:3 周(1 周代码 + 2 周人工核验)

### Stream E — 10 个 Agent 代码可用性侦察 【代码层】

**目标**:每个 agent 拉代码、装依赖、跑 5-10 个 canary case,确认能跑通。

**风险等级评估**(基于已发表信息,实际跑通才知道):

| Agent | License | 代码状态 | 风险 |
|---|---|---|---|
| DeepRare | 公开 220⭐ | Nature 2026 配套 repo | 低 |
| MDAgents | NeurIPS 2024 oral 公开 | 多次外部复现 | 低 |
| MedAgents | ACL 2024 公开 | 简单 prompt 框架 | 低 |
| AgentClinic | MIT 公开 | 含 NEJM 病例 | 低 |
| MAI-DxO 社区版 | MIT 53⭐ | 第三方移植,非官方 | **中** — 行为可能与论文偏差 |
| RareAgents | 待定 — 需联系作者 | AAAI 2026 接收 | **高** — 可能拿不到代码 |
| PhenoBrain | npj DM 2025 | ALBERT 集成,有 model checkpoint? | **中** — 经典 NLP 流水线,部署复杂 |
| RDMA | arXiv 2507.15867 | 开源否? | **中** |
| VC-RDAgent | 离线 HPO embedding | 开源否? | **中** |

**回退策略**:如果某个 agent 跑不起来(尤其是 PhenoBrain/RDMA/VC-RDAgent),按可用性裁掉,**保 10 个系统总数**靠加 Gemini 控制组(已加)+ 备选 RareSeek-R1 / LA-MARRVEL。

**产出**:每个 agent 的 docker image + 一份"侦察报告"(实际跑得起来/坑/依赖/默认 backbone 等)
**预计耗时**:5-7 天,**这是最容易踩坑的 stream,优先级最高**

### Stream F — 评估基础设施(metric + 日志 + Docker) 【代码层】

**目标**:Step 2 主实验跑之前,所有 metric 计算、日志记录、cost/latency 捕获、可复现性容器化都就位。

**组件清单**:
- Recall@k / Median Rank / MRR — Python 函数库
- Pillar 1 P/R/F1 — HPO 词项级 + ontology 距离容差
- Brier / ECE / Confidence AUROC — 校准 metric 库
- pass^k — k 次重复跑统计
- Cost-Normalized Accuracy — 接入 OpenAI/Anthropic/Google token 计费表
- Per-call 日志 schema(JSON Lines): `{case_id, agent_id, backbone_id, pillar_id, prompt, response, tools_called, tokens_in, tokens_out, latency_ms, cost_usd, timestamp}`
- Deterministic seed + 固定模型版本快照
- Docker base image(每个 agent 一份)

**产出**:`harness/` Python package + 一份共享 prediction log schema
**预计耗时**:1 周

### Stream G — 申请提交 【申请层】

**目标**:今天就把 MyGene2 + DDD 申请发出去,DDD 启动机构 IRB exempt 并行流程。

详见 `applications.md`。
**预计耗时**:1 周(申请表准备 + 提交)+ 2-6 周(审批)

---

## 2. 工作流依赖图

```
Day 1 ─────► Day 7 ─────► Day 14 ────► Day 21 ────► Day 28
 │
 ├─ Stream A (3 数据集) ──┐
 ├─ Stream B (schema) ────┼─► canonical_case.json 全数据集 ready
 ├─ Stream C (MIMIC) ─────┘     │
 │                              │
 ├─ Stream D 步骤 1-4 ──► 候选 → 步骤 5 (人工 2 周)
 │
 ├─ Stream E (10 agents) ──► agent 阵容固化
 │                              │
 ├─ Stream F (harness) ──┐      │
 │                       ▼      ▼
 │                  Sanity-check run (LLM 控制组 + 200 例) ──► 全量 Step 2
 │
 └─ Stream G (申请) ──► 审批中 ──► v2 数据(后置)
```

**关键路径**(最长串行链):**Stream E(7 天)→ Sanity-check(2 天)→ 全量主实验**。Stream D 的 holdout 人工核验是并行支线 — holdout 评估只在主实验数据集列表里,不阻塞主实验框架启动。

---

## 3. 同步执行的具体节奏(Day-by-Day)

### Day 1(今天)

**你做的**:
- [ ] 回复 Gemini 版本确认
- [ ] 启动 MIMIC-IV 表下载(后台跑,约 8-13 GB)
- [ ] 注册 MyGene2 账号并发 bulk export 邮件
- [ ] 起草 DDD 申请表 lay summary 草稿(可用 `applications.md` 的模板)
- [ ] 通知人工核验负责人 PMC OA 任务即将启动

**我做的**(只要你确认开始):
- 创建项目 Python 包结构 `harness/`
- 写规范案例 schema(Stream B 草稿)
- 写 Phenopacket-Store ingest 脚本(Stream A)
- 写 RareBench ingest 脚本(Stream A)
- 写 ICD→Orphanet 映射框架(Stream C,等 MIMIC 数据)
- 起草 10 个 agent 的侦察清单 + repo 拉取脚本(Stream E)

### Day 2-3

- MIMIC-IV 数据到位 → 我跑 ICD→Orphanet 映射 + NLP 召回流水线开发
- 10 个 agent 的 docker image 构建 + canary 测试 全部启动
- PMC OA bulk download 启动

### Day 4-7

- 三大数据集 → canonical_case.json 转换完成
- MIMIC-IV 罕见病切片 v0(脚本可跑,数字可能要迭代)
- 全部 10 个 agent canary 测试报告 → 阵容固化(裁掉跑不起来的)
- PMC OA 步骤 1-4 跑完 → 300-500 候选交给人工核验
- Harness 主体(metric + 日志)就位

### Day 8-10

- Sanity-check 跑:3 个 LLM 控制组 × 200 例小子集 × 5 个 pillar → 验证整个 pipeline end-to-end
- 修 bug,固化 prompt 模板
- 预注册 H1-H11 假设到 OSF(必须在 unblind holdout 之前,所以这个节点必须在 PMC OA 人工核验完成前)

### Day 11+

- Sanity-check 通过 → 开 4 通用医学 agent 全量跑
- Sanity-check 通过 → 开 4 罕见病 agent 全量跑
- PMC OA 人工核验进行中 → Day 21 左右完成 → 加入主数据集

---

## 4. MIMIC-IV 数据具体接入指引(给你的操作手册)

### Step 1 — 在你机器上下载

PhysioNet 提供 `wget` 命令(在数据集页面有完整模板):

```bash
# 在你的机器上,不是我跑的
mkdir -p /Users/yutianzhao/Desktop/RDAgentBenchmark/data/mimic-iv-raw
cd /Users/yutianzhao/Desktop/RDAgentBenchmark/data/mimic-iv-raw

wget -r -N -c -np \
  --user=<你的PhysioNet用户名> --ask-password \
  https://physionet.org/files/mimiciv/3.1/

# 或者更精准,只下需要的子集
wget --user=YOURNAME --ask-password \
  https://physionet.org/files/mimiciv/3.1/hosp/admissions.csv.gz \
  https://physionet.org/files/mimiciv/3.1/hosp/patients.csv.gz \
  https://physionet.org/files/mimiciv/3.1/hosp/diagnoses_icd.csv.gz \
  https://physionet.org/files/mimiciv/3.1/hosp/d_icd_diagnoses.csv.gz

# Notes 表在独立的 MIMIC-IV-Note 包(需要单独 credentialed sign-off)
wget --user=YOURNAME --ask-password \
  https://physionet.org/files/mimic-iv-note/2.2/note/discharge.csv.gz \
  https://physionet.org/files/mimic-iv-note/2.2/note/radiology.csv.gz
```

### Step 2 — 告诉我路径

下载完成后,在我们的会话里说"数据放在 `/Users/yutianzhao/Desktop/RDAgentBenchmark/data/mimic-iv-raw/`",我会写脚本从那里读。

### Step 3 — 我做的处理

我的脚本会做的事:
1. 从 `diagnoses_icd.csv.gz` 拉出所有 (hadm_id, icd_code, icd_version)
2. 对照 Orphadata 交叉引用,标记每条 ICD 是否是 Orphanet 编码
3. 对 Q87.8 类伞码,从 `discharge.csv.gz` 取出对应 hadm 的自由文本
4. 跑 NLP 召回(基于 MIMIC-RD 流水线 + HPO 词项匹配)
5. 输出每个被识别为罕见病的 hadm → canonical_case.json
6. 输出统计报告:覆盖了多少 Orphanet 编码、Exact vs NTBT vs BTNT 各占多少、最终 case 数

### Step 4 — DUA 合规检查

- ✅ 数据物理上只在你本机,不上传任何云
- ✅ 派生切片(canonical_case.json)只在你本机
- ✅ 论文 supplement 只发布构建脚本,不发布派生数据
- ✅ 任何调用 LLM API 跑评估时,**只传入 de-identified 的临床描述 + HPO 词项**,不传 raw discharge note 全文(避免身份残留)
- ⚠️ 关键:跑 agent 评估时,如果某 agent 需要"原文 vignette",需要先用 HIPAA Safe Harbor 18 项标识符过滤器或 Microsoft Presidio / Stanza i2b2 等工具做一次 de-id 二次过滤(MIMIC 自带 de-id 但有残留)。这一步加到 Stream C 的产出里。

---

## 5. 关键阻塞 / 风险登记

| # | 风险 | 触发条件 | 缓解 |
|---|---|---|---|
| R1 | Gemini Flash 版本未确认 | 你回复前 | 文档里先占位 "Gemini Flash (latest GA)" |
| R2 | RareAgents 拿不到代码 | 联系作者无回应 | 用 4 个罕见病 agent(裁 1 个) — DeepRare/PhenoBrain/RDMA/VC-RDAgent |
| R3 | PhenoBrain/RDMA/VC-RDAgent 跑不起来 | Stream E canary 失败 | 用 LA-MARRVEL + RareSeek-R1 补 |
| R4 | MIMIC ICD→Orphanet 映射覆盖率太低 | <30% | 加大 NLP 召回权重,降低主结构层依赖 |
| R5 | PMC OA 200 例人工核验跟不上 | Day 21 仍未完成 | mini 版 50 例先用,full 200 进 camera-ready |
| R6 | DDD 申请被拒 | Week 5-6 | v2 Pillar 4 仅靠 MyGene2 + Phenopacket trio 子集 |
| R7 | API 速率限制 | 全量跑时 | 用 batch API + 分时段调度 |

---

## 6. 下一个决策点

Day 7 结束(Stream A-G 第一周结束)做一次 **checkpoint**,届时确认:
- 10 个 agent 阵容是否固化(基于 canary 结果裁/补)
- canonical_case schema 是否需要调整
- MIMIC 切片初步统计是否符合预期
- PMC OA 候选 300-500 数量是否在预期

如果上述任一不符合,在 Sanity-check(Day 8-10)之前调整 — 这是动主实验之前**最后**的调整窗口。

---

## 7. 我现在等你回复的事

1. **Gemini 版本**:你查一下 Google AI Studio 当前最新 GA Flash 模型 ID + cutoff date,告诉我
2. **PMC OA 人工核验负责人**:姓名/角色
3. **MyGene2/DDD 申请负责人**:姓名
4. **是否授权我开始动手**:确认后我立刻启动 Stream A(数据集 ingest)+ Stream B(schema)+ Stream F(harness)三条不需要外部数据的线 — 这三条 1 周内能跑完

确认后我会按 Day 1 那栏的 "我做的" 部分立刻执行。
