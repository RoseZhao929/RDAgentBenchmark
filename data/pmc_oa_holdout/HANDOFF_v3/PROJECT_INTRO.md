# 项目介绍 — 给医生标注员

> 1 页讲清:这是什么 paper、为什么要标注、你的工作怎么用。

---

## 1. 我们在做什么

我们在 **Nature 子刊** 投一篇 paper, 题目大致是:

> *罕见病诊断 AI agent 的统一评测基准*

简单说: 过去两年涌现了 ~10 个用大语言模型 (LLM) 来辅助诊断罕见病的"AI agent"
系统 (DeepRare, MAI-DxO, RDMA, MedAgents 等), 但**每家用自己的数据**评测,
**互相不可比**。临床方读 paper 时根本不知道哪家真的更好,因为评分基准不一样。

我们做一个**统一的评测集 + 跑分平台**, 让所有罕见病 AI agent 在**同一批病例**
上比拼,临床方可以一眼看出哪家在哪类病例上表现更好/差。

---

## 2. 评测覆盖什么

我们拼了 **4 个数据层** 跨 ~85,000 个罕见病病例:

| 层 | 数据来源 | 规模 | 用来回答什么 |
|---|---|---|---|
| L1 表型主干 | Phenopacket-Store + RareBench HF | 11,173 | "HPO 表型 → 疾病"的核心能力 |
| L2 真实 EHR | MIMIC-IV ICU 病例切片 | 956 | 真实 EHR 噪声里能不能识别罕见病 |
| L3 海量自由文本 | RareArena | 72,661 | 从病历叙事里诊断罕见病 |
| **L4 截止后病例 (你标的)** | **PMC OA 2024+ 论文** | **~200** | **AI 训练数据见不到的"新鲜"病例, 真测泛化** |

L4 — 也就是**你正在标的部分** — 是最关键的一层, 原因见 §3。

我们评了 **8 个主流 agent** (DeepRare, MDAgents, MedAgents, AgentClinic,
MAI-DxO, RDMA, VC-RDAgent, LIRICAL) × **4 个 LLM 主干** (Gemini, DeepSeek
V4-Pro/Flash, GPT-5)。

---

## 3. 你标的这 200 例为啥这么重要 (核心动机)

**问题: LLM 可能"背诵"训练数据里的诊断**

LLM 训练 cutoff 通常在 2024-Q3 左右。如果我们拿一个 2022 年发表的病例去测,
LLM 可能在训练时**已经见过**这篇论文 — 它"答对"诊断,不一定是它会推理,
可能是它在背。这叫**数据污染** (data contamination), 是 AI 评测里最严重的
attack surface。

**解决方案: 拿 2024-01-01 以后发表的全新病例做"holdout"**

这种病例 LLM 训练时一定没见过。如果它还能答对, 才证明真有推理能力。

**这就是你看到的 198 个候选**: 全部是 PMC Open Access 2024 年起发表的
真实罕见病病例报告。我们自动流水线已从 ~万篇文章里筛出最像样的 250 个,
你帮我们**确认 LLM 抽出的诊断和表型是不是真的对**, 形成可信的金标准。

你标完 → 我们把 8 个 agent 跑到这 200 例上 → R@1 命中率 = paper 里的核心数字。

---

## 4. paper 现在有哪些初步结论 (供你参考)

(摘自 paper draft `1_abstract.md`)

1. **经典/离线方法 (如 LIRICAL Bayesian) 比所有 LLM agent 都强** — 在 HPO 输入
   数据集上, LIRICAL 0.46 R@1, 最强 LLM 0.33。这是**最反直觉的结论**, 也是
   paper 最大卖点: "LLM 不是万能, 经典工具仍重要"
2. **多 agent scaffolding 增益很小** (2-5 pp), 不是各家 paper 暗示的"质变"
3. **DeepSeek V4-Flash ~10x 便宜但准确性掉 2-16 pp** — 性价比, 但不等价
4. **GPT-5 关掉 reasoning 后 brittle** — 价钱最贵但效果不稳, 在某些 scaffold 上
   崩盘 (-14 pp on AgentClinic)
5. **基因变异通道普涨 ~20 pp** — 不是 DeepRare 特有, 任何能吃 variants 的 agent
   都能从中受益

第 4 层 (你标的 holdout) 会决定上述结论是不是"训练数据巧合"。

---

## 5. 你的工作具体怎么用 (closed loop)

```
你标完 review_workbook.xlsx
        ↓
我们读 L 列 (正确诊断) + M 列 (错误 HPO terms)
        ↓
~150-180 个高质量金标准病例
        ↓
8 个 agent × 4 backbone 各跑这 ~150 个病例
        ↓
计算 R@1 / R@5 → paper §6 主表 (最右一列)
        ↓
跟 L1/L2/L3 三个老数据层对比 — 看 agent 在"新鲜"病例上是否还行
        ↓
**回答 "LLM 是不是在背训练集" 这个 reviewer attack** (§7.6 + §8.6 反污染分析)
```

如果你最终标出 **诊断错误率高 + HPO 噪声高** → paper 里会说 "LLM extraction
pipeline 在 holdout 上不可靠, 需手工金标准" (这本身也是一个 contribution);
如果**错误率低** → paper 里说 "LLM 抽取在新鲜病例上质量稳定, agent 评测可用"。

任一种结果都对 paper 有意义, **不需要"标对"或"标错"达到某个比例**。
最重要的是**抓出 LLM 真的犯的错误**, 写下你认为正确的答案。

---

## 6. 你需要的 reference

- 标注工作流: `README.md`
- xlsx 工作文件: `review_workbook.xlsx`
- demo 标注示范: xlsx 的 `demo_examples` sheet
- 198 篇 PMC 全文: `pmc_fulltext/`

有任何问题直接回复给我。
