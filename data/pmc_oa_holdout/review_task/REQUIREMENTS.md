# PMC OA Holdout — Human Review Task

> **背景**:罕见病 Agent Benchmark(EMNLP 投稿)需要一个 cutoff-after 的 holdout split 来防御"训练数据泄漏"批评。我们已经自动跑完 PMC OA 抽取 + Orphanet 映射的 4 步流水线,产出 **1,433 个候选**。这个 task 是人工核验环节(流水线第 5 步,**金标准来源,必须人工**)。
>
> **关键背景资料**(可选读但有帮助):
> - 项目整体设计:`/Users/yutianzhao/Desktop/RDAgentBenchmark/plan.md`(完整 plan)
> - 流水线代码:`/Users/yutianzhao/Desktop/RDAgentBenchmark/harness/pmc_oa/`
> - 自动筛选 stats:`/Users/yutianzhao/Desktop/RDAgentBenchmark/data/pmc_oa_holdout/REVIEW_INSTRUCTIONS.md`(更长版的本文档)

---

## 1. 你的目标

**从 1,433 个自动筛出的候选里,人工核验挑出 ~200 个高质量的罕见病 case**,作为 benchmark holdout split 的金标准。

**为什么 200 例**:
- 太少(<100):统计效力不足,假设检验 H1-H3 跑不动
- 太多(>500):人工成本不划算 + 后续 8 个 agent × 3 backbone × 200 case ≈ $1000+ 评估成本
- 200 是 RareBench PUMCH-ADM(75 例)和 NEJM CPC benchmark(304 例)之间的合理点

---

## 2. 数据在哪里(输入)

```
/Users/yutianzhao/Desktop/RDAgentBenchmark/data/pmc_oa_holdout/
├── 06_candidates_for_review.jsonl    ← 你要审的 1,433 行,每行一个候选
├── REVIEW_INSTRUCTIONS.md            ← 详细说明 + 字段解释 + tier 排序逻辑
└── review_task/
    └── REQUIREMENTS.md               ← 本文件
```

**每行 JSON 字段**:
| 字段 | 含义 | 你怎么用 |
|---|---|---|
| `pmc_id` | PMC 文章 ID | 拼到 URL 打开 PMC 网页读全文 |
| `pmc_url` | 直接的 PMC 链接 | 一键打开 |
| `orpha_id` | Orphanet 罕见病 ID(自动匹配的)| 核对是否真的对应文章里的诊断 |
| `omim_ids` | 跨映射到的 OMIM IDs | 辅助确认 |
| `matched_orpha_name` | Orphanet 标准名 | 跟文章里的诊断比对 |
| `extracted_diagnosis` | LLM 从文章里抽出来的诊断 | 跟 matched_orpha_name 比对(自动匹配的来源)|
| `match_type` | exact_name / fuzzy | exact 优先信赖,fuzzy 多核 |
| `match_score` | 100=精确,95-99=高分 fuzzy | 越高越可信 |
| `hpo_phenotypes` | LLM 抽的临床表型词条(自然语言)| 跟文章 case 描述比对 |
| `case_excerpt` | LLM 截取的 case 段落 | 节省时间,先看这个再决定要不要打开全文 |
| `age_at_presentation_years` / `sex` / `has_family_history` / `pub_year_in_text` | 病例 demographic | 验证用 |
| `top_candidates` | 自动匹配时考虑的前 3 个 ORPHA 候选 | 看看是不是匹配错 |

候选**已经按质量排序**:exact_name(score=100)在前,fuzzy ≥95 在后。你从头往下审,前 ~250 个 exact_name 里大概率挑出 200 个就够。

---

## 3. 核验 metrics(每个候选 5-10 分钟,4 个 check)

对每个候选,**4 项必查**:

### Check 1 — 诊断匹配正确?(must pass)

**问**:`extracted_diagnosis` 真的是文章的**最终/确诊**诊断吗?`matched_orpha_name`(我们映射到的 Orphanet 标准名)真的代表同一个疾病吗?

**怎么查**:
- 打开 `pmc_url` 找文章的 "Diagnosis" / "Final diagnosis" / "Conclusion" 段
- 排除以下情况:
  - "suspected X"(疑似)
  - "final diagnosis was X but Y could not be ruled out"(诊断有争议)
  - "differential diagnosis included A, B, C"(只是鉴别诊断列表)
  - "diagnosed as X, however later confirmed to be Y"(改诊断的 case)
- 排除 Orphanet 映射错误的(fuzzy 高分但语义无关,比如 "dengue shock syndrome" 被映射到 "CK syndrome"— 这种应该拒)

**结果**:✓ 通过 / ✗ 拒(reason)

### Check 2 — HPO 表型准确?(must pass)

**问**:`hpo_phenotypes` 列表里的临床表型,**真的是这个病人有的**吗?

**怎么查**:
- 看 `case_excerpt` 段落
- 列表里**不应该**包括:
  - 鉴别诊断里提到的(不是病人有的)
  - 化验值/影像描述写成 phenotype(可以保留但标注)
  - 完全无关的(LLM 抽错)
- 如果列表里有 ≤30% 噪声/不准的,**accept + 标 `hpo_phenotypes_clean=false`(advisory only)**
- 如果 >30% 噪声 → ✗ 拒

**`hpo_phenotypes_clean` 字段语义**:**advisory only**,不阻塞 accept。
- `true`:HPO 列表干净(>70% 准),accept
- `false`:HPO 列表 30% 以下噪声,**仍 accept**,但下游 H1-H11 stratified analysis 可以分组看 "noise on agent performance" 影响
- 主实验我们不一定用 LLM-抽的 HPO 当 gold(主 gold 来自 Phenopacket-Store / RareBench;PMC holdout 主要用 final diagnosis 当 gold,HPO 是 secondary)

**Prenatal / family-affected case 特殊情况**(demo 发现):

如果 proband 是胎儿 / 新生儿,**亲属(父/母)的 phenotype 出现在 HPO 列表里是合理证据**,不算 noise。

例如 PMC10767578 (Nail-Patella Syndrome) 的 proband 是新生儿,HPO 列表里 2/3 是父亲的表型(父亲临床表现 NPS,妈妈基因检测发现 LMX1B 变异)。这些表型**是诊断的家族证据**,标 `hpo_phenotypes_clean=true`。

**标注员怎么识别**:case_excerpt / 文章正文出现 "prenatal", "the father presents with", "family history of"……

**结果**:✓ 通过 / ✗ 拒(reason)

### Check 3 — Cutoff 时间核验?(must pass)

**问**:这个 case **真的是 2024-01-01 之后的新报告**吗?有没有可能是 pre-2024 的 case 在 2024 年后再发的?

**官方 cutoff 定义**(2026-05-14 锁定):

**主判据 = PMC `pmclivedate` ≥ 2024-01-01**(PMC OA 开放访问发布日期 — 我们 pipeline 已经按这个筛过)

**辅助文本启发式**(text-based,拒一类隐性 pre-cutoff republication):
- 文章标题 / abstract 含"case series" / "literature review" / "retrospective" / "follow-up of ..." → 警惕
- 多 patient 表格,病例诊治日期 << 2024 → **reject**(典型如 demo 拒的 PMC10768362 MKD,2018 年 admitted 患者的回顾性 follow-up)
- 文章正文有"previously reported in [pre-2024 reference]" / "this patient was first described in 2019" → **reject**(republication / 同 case extended follow-up)
- 仅依靠 author 之前发表过类似研究 → **不算 reject 理由**(同一 author 可以有多个 patient cohort)

**怎么查**:
1. 看 NCBI eutils 给的 `pmclivedate` ≥ 2024-01-01(必须通过,pipeline 已经筛)
2. 看文章 abstract / introduction 末尾,常见 disclosure "first reported in 2019" 之类
3. 看 case 内文写的入院 / 诊治年份(`pub_year_in_text` 字段)是否 < 2022(超过 2 年延迟报道,警惕 republication)
4. 如果是 "case series" 且每个 patient 都有 individual admission date,看是否所有 date < 2024

**为什么 pmclivedate 是主判据**(论文 method 章节 reproducibility):
- 三个候选日期(`epub` / `pmclivedate` / 病人诊治年)各有问题:`epub` 过严(很多 2024-Q1 collection 论文 epub 在 2023-Q4)、病人诊治年过严(回顾性 case report 全 reject 不现实)、`pmclivedate` 是"PMC 开放访问首次可见"日期,**是 LLM training data 可访问性的 hard boundary**,reviewer 角度最 defensible

**结果**:✓ 通过(`pmclivedate` ≥ 2024-01-01 AND 不是 republication / 长 follow-up 隐性 pre-cutoff)/ ✗ 拒(任一 fail)

### Check 4 — 真的是罕见病?(must pass)

**问**:`orpha_id` 真的对应一个**罕见病**(prevalence ≤ 1/2000 EU)吗?

**主流程**(推荐 — 避开 orpha.net web UI):

下载 Orphadata 离线 XML(一次性,几 MB):
```
data/orphadata/en_product1.xml        — 我们 pipeline 已下,11,456 disorders + cross-refs
data/orphadata/en_product9_prev.xml   — 需下载,prevalence 表
```
download 命令:`curl -sL -o data/orphadata/en_product9_prev.xml https://www.orphadata.com/data/xml/en_product9_prev.xml`

然后:
- `grep ORPHA:<NUM>` 在 `en_product9_prev.xml` 找 prevalence band(`<1/1,000,000` / `1-9/1,000,000` / `1-9/100,000` / `1-9/10,000` / `1-5/10,000` 都算罕见)
- 任何 `>1-5/10,000` 或 "NON RARE IN EUROPE" 标记 → ✗ 拒

**特别 — Clinical subtype 继承父 disorder prevalence**(demo 发现):

某些 ORPHA entry 是"clinical subgroup" / "subtype of disorder"(`disorder_type` 字段),它们**没有自己的 prevalence**,需要从父 disorder 继承。比如:
- ORPHA:139399 Adrenomyeloneuropathy 是 ORPHA:43 X-linked adrenoleukodystrophy 的临床亚型,继承父 disorder rare 状态
- 这种情况在 `en_product1.xml` 里 `<DisorderDisorderAssociation>` 字段查父 disorder

如果 `en_product9_prev.xml` 里 grep 不到 ORPHA 号,**先查 disorder_type**,如果是 subtype/subgroup → 看父 disorder 的 prevalence。

**结果**:✓ 通过(prevalence ≤ 1-5/10,000 EU,自己的或继承的)/ ✗ 拒(非罕见 / "NON RARE IN EUROPE" 标记)

**❌ 不要做的事**:
- 不要打开 `orpha.net/en/disease/detail/<NUM>` 看 prevalence — 那是 JS 渲染的 SPA,raw HTML 没数据 + 经常被 captcha 阻塞
- 不要直接 curl PMC 全文页面 `pmc.ncbi.nlm.nih.gov/articles/PMC<id>/` — 用 NCBI E-utilities `efetch?db=pmc&id=<PMCID>` 拿 JATS XML 更快(下面 §5 详述)

---

## 4. 你需要输出什么

### 4.1 主输出 — `07_curated_holdout.jsonl`

放在 `/Users/yutianzhao/Desktop/RDAgentBenchmark/data/pmc_oa_holdout/07_curated_holdout.jsonl`

**只包含 ✓ accept 的 case**(目标 ~200)。每行 JSON 是原 `06_candidates_for_review.jsonl` 那行 **再加 5 个字段**:

```json
{
  // ... 原 06 那行所有字段 (pmc_id, orpha_id, omim_ids, ... ) ...
  "review_decision": "accept",
  "reviewer_id": "annotator_01",
  "review_timestamp": "2026-05-15T14:23:00Z",
  "hpo_phenotypes_clean": true,
  "reviewer_notes": "Definitive diagnosis on page 3, HPO accurate, pub date 2024-06"
}
```

`review_decision` 字段三个合法值:
- **`accept`**:4 个 check 全 ✓ pass → 写到 `07_curated_holdout.jsonl`
- **`reject`**:任一 check ✗ fail → 写到 `08_rejected_cases.jsonl`
- **`uncertain`**:有疑问、需要第二轮 review / 跨 reviewer 协商 → 写到 `10_uncertain_cases.jsonl`(临时桶,周末集中过)

### 4.2 拒审记录 — `08_rejected_cases.jsonl`

记录 ✗ 拒的 case。同 4.1 schema,`review_decision: "reject"`,`reviewer_notes` 写**哪个 check fail + evidence**。

### 4.3 不确定桶 — `10_uncertain_cases.jsonl`(新增)

把 ?标的 case 放这里,字段同上,`review_decision: "uncertain"`,`reviewer_notes` 写**疑问点**(比如"prevalence 边缘:Orphadata 标 1-9/100k 但近年 NORD 估 1/15k,需 PI 决定")。

集中找时间(每天结束 / 每周末)走第二轮,要么转 accept 要么转 reject。**最终交付的 holdout 必须没有 uncertain 状态。**

### 4.4 汇总 — `09_review_summary.md`

简短一页:
- 审了多少个 / 接受多少 / 拒多少
- 4 个 check 各 fail 多少
- 疾病分布(top-20 ORPHA ID)
- 任何 systematic 发现(比如 "fuzzy match 比 exact 拒得多" / "某个 journal 来源全是 republication")

---

## 5. 高效工作流(demo 验证过的)— **不要用 web UI 浏览**

orpha.net 和 pmc.ncbi.nlm.nih.gov 都对自动 HTTP 请求触发 captcha,浏览器查也慢。用下面替代方案,**10 个 case 从 1 小时降到 30 秒**:

### 5.1 取 PMC 文章全文 — NCBI E-utilities

```bash
curl "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc&id=<PMCID>&rettype=xml&retmode=xml"
```

返回 JATS XML 含完整正文。grep `<article-title>` / `<sec sec-type="cases">` / "Final diagnosis" 等。
速率限制:无 API key 3 req/s,有 key 10 req/s。

取 publication date metadata(`epubdate` / `pmclivedate` / `pubdate`):

```bash
curl "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pmc&id=<PMCID>"
```

### 5.2 查 Orphanet prevalence — XML dump

```bash
# 一次性下:
mkdir -p data/orphadata
curl -sL -o data/orphadata/en_product9_prev.xml https://www.orphadata.com/data/xml/en_product9_prev.xml

# 查 ORPHA:902 (Werner syndrome):
xmllint --xpath '//Disorder[OrphaCode="902"]' data/orphadata/en_product9_prev.xml
# 或 grep 也能用
```

### 5.3 容易混淆的 fuzzy match 陷阱(从 demo 学到的)

- "AMN" = Adrenomyeloneuropathy(ABCD1)或 Acute macular neuroretinopathy → **看基因**
- "JPS" = Juvenile Polyposis Syndrome(SMAD4/BMPR1A)或 Job's syndrome(STAT3)→ **看基因**
- "3M syndrome" 词面像非特异性诊断 → **必须看基因 CUL7/OBSL1/CCDC8 确认**
- "dengue shock syndrome" 被自动 fuzzy 匹配到 ORPHA:251383 "CK syndrome" → **拒 + Check 1 fail**

---

## 6. 怎么并行 / 怎么质控

### 双人核验(强烈推荐)

随机分 200 个候选 → 两个标注员各审 100,**外加 20 个交叉审**(两人都审)用于算 Cohen's κ(inter-rater agreement)。κ ≥ 0.6 是 acceptable 阈值,这是 benchmark 论文里 reviewer 必问的"金标准可靠性"指标。

如果只有 1 个标注员,放弃 κ,但 → **每 50 个 case 抽 5 个让医学背景 reviewer 抽检**(20% 重审率)。

### 操作建议

- **每天审 30-50 个**(2.5-4 小时,可持续)
- 用一个简单的 Google Sheet / Excel 当 worklog,每行一个 case + 4 个 check 列 + notes 列
- 审完后跑一个简单 Python 脚本把 sheet 导成 `07_curated_holdout.jsonl`
- 我可以提供这个导出脚本 — 你确定 spreadsheet 列名后告诉我

---

## 7. 时间预期 + 阻塞

- **理想**:200 个 accept × 5-10 min/审 = 17-33 工时,1 个人 1 周内 / 2 个人 3-4 天
- **必须在 Round 2 主实验 unblind holdout 前完成** — 也就是 OSF preregistration submit 之前,见 `osf_preregistration.md`
- **任何不确定的 case 标 `?` 不要瞎拒**,然后周末抽时间集中过一遍二次决定

---

## 8. 参考输出(demo subagent 跑出来的,看格式 + 学风格)

我们让一个 AI subagent 按本文 spec 做了**前 10 个候选**的参考审核(用 NCBI E-utilities + Orphadata XML),输出在:

- `data/pmc_oa_holdout/07_curated_holdout.jsonl`(9 accept,demo)
- `data/pmc_oa_holdout/08_rejected_cases.jsonl`(1 reject:PMC10768362 — Mevalonate kinase deficiency 是 2018 年管理的回顾性 case series,典型 Check 3 fail)
- `data/pmc_oa_holdout/09_review_summary.md`(demo 全过程总结 + tips)

**真标注员从这 3 份文件可以**:
1. 看 `reviewer_notes` 格式怎么写(简洁 + 给 evidence)
2. 看 reject 怎么 justify(指明哪个 check fail + 文章哪段证据)
3. 看 9 个 accept 的疾病覆盖 → Werner / X-linked agammaglobulinemia / NPS / NF1 等

**真标注员开始正式 review 时**,**从第 11 个候选开始**(`06_candidates_for_review.jsonl` row 11+),不用重审前 10 个 — demo 已经做了。

---

## 9. 联系人 / 问题反馈

如果在审的过程中:
- 发现 pipeline 系统性 bug(某类 case 全是错的)→ 反馈我,我修 pipeline 重跑(代价是几小时,你只需要审重跑后的差量)
- 不确定 Orphanet 是不是罕见 → 写 `?` 暂存,我可以批量查 Orphadata prevalence band
- LLM 抽的 HPO 太离谱 → 标 `hpo_phenotypes_clean=false`,我们后续主实验跑 P1 端到端时不用 LLM-抽的当 gold

---

## 附录:候选池前 5 个 sneak peek

```
PMC13074162: Werner syndrome             → ORPHA:902  (exact)
PMC13076136: X-linked agammaglobulinemia → ORPHA:47   (exact)
PMC10766305: Lhermitte-Duclos disease    → ORPHA:65285 (exact)
... (在 06_candidates_for_review.jsonl 里全部 1,433 行,按 quality 排序)
```
