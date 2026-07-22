# Rare-Disease Case Review — Annotation Instructions

> **背景(简版)**:我们在构建一个罕见病诊断的评测集。已经用自动流水线从 PMC
> 开放获取(Open Access)文献里抽取 + 映射 Orphanet,产出 **1,433 个候选病例**。
> 这一步是**人工核验**:从候选里挑出 ~200 个高质量罕见病 case 作金标准。
> 自动抽取/映射会有错,所以必须人工把关。

---

## 1. 你的目标

**从 1,433 个自动筛出的候选里,人工核验挑出 ~200 个高质量的罕见病 case。**

**为什么是 ~200**:统计上够用(太少效力不足),人工成本可控(太多不划算)。
200 是同类 benchmark(75–304 例)之间的合理点。

候选**已经按质量排序**:`exact_name`(score=100)在前,`fuzzy`(≥95)在后。
从头往下审,前 ~250 个 exact_name 里大概率能挑出 200 个。

---

## 2. 包里有什么(输入)

```
HANDOFF/
├── README.md                  ← 先读这个(怎么填、填完发回什么)
├── INSTRUCTIONS.md            ← 本文件(详细标注说明)
├── review_template.csv        ← 预填好的 250 行模板,你主要填这个
├── candidates_full_pool.jsonl ← 全部 1,433 候选(CSV 不够时的完整池)
├── demo_accepted_9.jsonl      ← 参考:demo 已审的 9 个 accept
├── demo_rejected_1.jsonl      ← 参考:demo 已审的 1 个 reject
└── demo_review_summary.md     ← 参考:demo 全过程总结 + 实操 tips
```

**`candidates_full_pool.jsonl` 每行 JSON 字段**:

| 字段 | 含义 | 你怎么用 |
|---|---|---|
| `pmc_id` | PMC 文章 ID | 拼到 URL 打开 PMC 网页读全文 |
| `pmc_url` | 直接的 PMC 链接 | 一键打开 |
| `orpha_id` | Orphanet 罕见病 ID(自动匹配的)| 核对是否真对应文章里的诊断 |
| `omim_ids` | 跨映射到的 OMIM IDs | 辅助确认 |
| `matched_orpha_name` | Orphanet 标准名 | 跟文章里的诊断比对 |
| `extracted_diagnosis` | 自动从文章抽出的诊断 | 跟 matched_orpha_name 比对 |
| `match_type` | exact_name / fuzzy | exact 优先信赖,fuzzy 多核 |
| `match_score` | 100=精确,95-99=高分 fuzzy | 越高越可信 |
| `hpo_phenotypes` | 自动抽的临床表型词条 | 跟文章 case 描述比对 |
| `case_excerpt` | 自动截取的 case 段落 | 先看这个再决定要不要打开全文 |
| `age_at_presentation_years` / `sex` / `has_family_history` / `pub_year_in_text` | 病例 demographic | 验证用 |
| `top_candidates` | 自动匹配时考虑的前 3 个 ORPHA 候选 | 看是否匹配错 |

---

## 3. 核验 metrics（每个候选 5–10 分钟，4 个 check 全过才 accept)

### Check 1 — 诊断匹配正确?（must pass)

**问**:`extracted_diagnosis` 真的是文章的**最终/确诊**诊断吗?`matched_orpha_name`
真的代表同一个疾病吗?

**怎么查**:
- 打开 `pmc_url` 找文章的 "Diagnosis" / "Final diagnosis" / "Conclusion" 段
- 排除以下情况:
  - "suspected X"(疑似)
  - "final diagnosis was X but Y could not be ruled out"(诊断有争议)
  - "differential diagnosis included A, B, C"(只是鉴别诊断列表)
  - "diagnosed as X, however later confirmed to be Y"(改诊断的 case)
- 排除 Orphanet 映射错误的(fuzzy 高分但语义无关,比如 "dengue shock syndrome"
  被映射到 "CK syndrome" — 这种应该拒)

### Check 2 — HPO 表型准确?（must pass)

**问**:`hpo_phenotypes` 列表里的临床表型,**真的是这个病人有的**吗?

**怎么查**:
- 看 `case_excerpt` 段落
- 列表里**不应该**包括:鉴别诊断里提到的(不是病人有的)、化验值/影像描述、完全无关的
- 如果列表 ≤30% 噪声 → **accept + 标 `hpo_phenotypes_clean=false`(仅供参考,不阻塞 accept)**
- 如果 >30% 噪声 → ✗ 拒

**Prenatal / 家族受累 case 特殊情况**:如果 proband 是胎儿/新生儿,**亲属(父/母)的
phenotype 出现在 HPO 列表里是合理的家族诊断证据**,不算 noise,标
`hpo_phenotypes_clean=true`。识别信号:case 正文出现 "prenatal" / "the father
presents with" / "family history of"……

### Check 3 — Cutoff 时间核验?（must pass)

**问**:这个 case 真的是 **2024-01-01 之后**的新报告吗?有没有可能是 pre-2024 的
case 在 2024 年后再发?

**主判据**:文章的 PMC 发布日期 ≥ 2024-01-01(流水线已按此筛过)。

**辅助文本启发式**(拒一类隐性 pre-cutoff republication):
- 标题/abstract 含 "case series" / "literature review" / "retrospective" /
  "follow-up of ..." → 警惕
- 多 patient 表格,病例诊治日期 << 2024 → **reject**
- 正文有 "previously reported in [pre-2024 ref]" / "first described in 2019" →
  **reject**(republication / 同 case extended follow-up)
- 仅"同一 author 之前发过类似研究" → **不算 reject 理由**

**怎么查**:
1. PMC 发布日期 ≥ 2024-01-01(用 §5 的 esummary,看 `pmclivedate`)
2. abstract/introduction 末尾常见 "first reported in 2019" 之类 disclosure
3. `pub_year_in_text` 字段(病例入院/诊治年)是否 < 2022(>2 年延迟报道,警惕)
4. 若是 "case series" 且每 patient 有 individual admission date,看是否都 < 2024

### Check 4 — 真的是罕见病?（must pass)

**问**:`orpha_id` 真的对应一个罕见病(prevalence ≤ 1/2000 EU)吗?

**怎么查**(避开 orpha.net web UI,它是 JS 渲染 + 易触发 captcha):

下载 Orphadata 离线 prevalence XML(一次性,几 MB):
```
curl -sL -o en_product9_prev.xml https://www.orphadata.com/data/xml/en_product9_prev.xml
```
然后:
- `grep ORPHA:<NUM>` 或 `xmllint --xpath '//Disorder[OrphaCode="<NUM>"]' en_product9_prev.xml`
  找 prevalence band
- `<1/1,000,000` / `1-9/1,000,000` / `1-9/100,000` / `1-9/10,000` / `1-5/10,000`
  都算罕见
- 任何 `>1-5/10,000` 或 "NON RARE IN EUROPE" 标记 → ✗ 拒

**Clinical subtype 继承父 disorder prevalence**:某些 ORPHA entry 是 "clinical
subgroup" / "subtype of disorder",没有自己的 prevalence,需从父 disorder 继承。
若在 prevalence XML 里 grep 不到,先查 disorder_type,是 subtype/subgroup 就看父
disorder 的 prevalence(可在 Orphadata `en_product1.xml` 的
`<DisorderDisorderAssociation>` 里查父 disorder)。

**❌ 不要做**:
- 不要打开 `orpha.net/en/disease/detail/<NUM>` 看 prevalence(JS SPA,raw HTML 无数据)
- 不要直接 curl PMC 全文网页 — 用 §5 的 E-utilities 拿 XML 更快

---

## 4. 你要输出什么

**最简方式 — 填 `review_template.csv`**(推荐)

模板已预填 top-250 候选的基本字段,你逐行填这几列:

| 列 | 填什么 |
|---|---|
| `check1_diagnosis_match` | `pass` / `fail` |
| `check2_hpo_accurate` | `pass` / `fail` |
| `check3_cutoff_verified` | `pass` / `fail` |
| `check4_truly_rare` | `pass` / `fail` |
| `review_decision` | `accept`(4 项全 pass)/ `reject`(任一 fail)/ `uncertain`(需二次核) |
| `hpo_phenotypes_clean` | `true` / `false`(见 Check 2,仅供参考) |
| `reviewer_notes` | reject/uncertain 必填:哪个 check fail + 证据(文章哪段) |

**目标**:填到累计 ~200 个 `accept` 即可停(不必把 250 行全填完)。

> CSV 里只有 250 行 exact_name 候选。如果 250 个里凑不够 200 个 accept(一般够),
> 再从 `candidates_full_pool.jsonl` 第 251 行起补 fuzzy 候选。

**`review_decision` 三个合法值**:
- `accept`:4 个 check 全 pass
- `reject`:任一 check fail,`reviewer_notes` 写哪个 check fail + evidence
- `uncertain`:有疑问需二次核,`reviewer_notes` 写疑问点。**最终交付不能有 uncertain**,
  集中找时间走第二轮,要么转 accept 要么转 reject

填完后回传**这个 CSV** 即可(见 README "填完发回什么")。

---

## 5. 高效工作流（不要用 web UI 浏览）

orpha.net 和 pmc 网页对自动请求易触发 captcha,浏览器也慢。用下面替代,
**10 个 case 从 1 小时降到 ~30 秒**:

### 5.1 取 PMC 文章全文 — NCBI E-utilities
```bash
curl "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc&id=<PMCID>&rettype=xml&retmode=xml"
```
返回 JATS XML 含完整正文。grep `<article-title>` / `<sec sec-type="cases">` /
"Final diagnosis"。速率:无 API key 3 req/s。

取发布日期(`epubdate` / `pmclivedate` / `pubdate`):
```bash
curl "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pmc&id=<PMCID>"
```

### 5.2 查 Orphanet prevalence — XML dump
```bash
curl -sL -o en_product9_prev.xml https://www.orphadata.com/data/xml/en_product9_prev.xml
xmllint --xpath '//Disorder[OrphaCode="902"]' en_product9_prev.xml   # 例:Werner syndrome
```

### 5.3 容易混淆的 fuzzy match 陷阱
- "AMN" = Adrenomyeloneuropathy(ABCD1)或 Acute macular neuroretinopathy → **看基因**
- "JPS" = Juvenile Polyposis Syndrome(SMAD4/BMPR1A)或 Job's syndrome(STAT3)→ **看基因**
- "3M syndrome" 词面像非特异性 → **必须看基因 CUL7/OBSL1/CCDC8 确认**
- "dengue shock syndrome" 被 fuzzy 匹配到 "CK syndrome" → **拒**

---

## 6. 质控建议

**双人核验(强烈推荐)**:随机分候选给两个标注员,**外加 20 个交叉审**(两人都审)
算 Cohen's κ(inter-rater agreement)。κ ≥ 0.6 是 acceptable 阈值——这是金标准
可靠性指标,审稿人会问。

**只有 1 个标注员**:放弃 κ,但每 50 个 case 抽 5 个让有医学背景的人抽检(20% 重审率)。

**节奏**:每天审 30–50 个(2.5–4 小时,可持续)。理想 1 人 1 周 / 2 人 3–4 天完成。

---

## 7. 参考:demo 已审前 10 个

`demo_accepted_9.jsonl`(9 accept)+ `demo_rejected_1.jsonl`(1 reject)+
`demo_review_summary.md`(全过程)是一个 AI 助手按本说明做的**前 10 个候选**参考审核。

**真标注员从第 11 个候选开始**(CSV 第 11 行 / `candidates_full_pool.jsonl` row 11+),
不用重审前 10 个。看 demo 主要学:
1. `reviewer_notes` 怎么写(简洁 + 给 evidence)
2. reject 怎么 justify(指明哪个 check fail + 文章哪段)
3. 9 个 accept 的疾病覆盖(Werner / X-linked agammaglobulinemia / NPS / NF1 等)

唯一的 reject(PMC10768362,Mevalonate kinase deficiency)是 2018 年管理的回顾性
case series,典型 Check 3 fail——值得照着学怎么识别 republication。

---

## 8. 遇到问题

- 发现某类 case 全是系统性错误(pipeline bug)→ 反馈给发你这个包的人,可修流水线重跑
- 不确定是不是罕见病 → 标 `uncertain` 暂存,集中批量查 Orphadata prevalence
- 自动抽的 HPO 太离谱 → 标 `hpo_phenotypes_clean=false`(不阻塞 accept)
