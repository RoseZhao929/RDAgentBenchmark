# 罕见病病例人工核验 — 医生交接包 (v3)

> **给医学专业标注人员**:你只填两列原始标注 — 错的诊断写正确,错的 HPO terms 列出来。
> 198 行,每行 2–4 分钟。
>
> **想了解这个 paper 在做什么、你的标注怎么用** → 先读 `PROJECT_INTRO.md` (1 页)

---

## 1. 这些病例哪里来的?(必读 — 3 分钟)

我们做罕见病诊断 AI 评测集,需要 ~200 个金标准病例评测各家 LLM agent。

**金标准从哪来**:从 PMC Open Access 2024 年起发表的英文罕见病病例报告。

**自动化流水线**(已跑完):

```
PubMed 罕见病关键词搜索, 2024-01-01+ 发表
       ↓  PMC E-utilities 下全文 XML
2,394 篇文章
       ↓  ⭐ Gemini 3 Flash LLM 读全文 → 抽出:
           - final_diagnosis (字符串, LLM 认为的最终诊断)
           - hpo_phenotypes (LLM 抽的临床表型 list)
           - age / sex / has_family_history
       ↓  Fuzzy-match final_diagnosis → Orphanet 6,443 个标准病名
1,433 候选 → 取 top 250 → 自动筛掉 52 个非 2024+ 新报告
198 行 → 这就是你的表
```

**⚠️ 重点**:xlsx 里 `disease_name` (D 列) 是 **LLM 抽的诊断**,不是文章作者直接写的。
LLM 可能错:
1. **混淆主诊断与鉴别诊断**:"suspected A, later confirmed B" → LLM 抽 A
2. **多 patient case series**:LLM 只关注其中一例
3. **改诊断没跟上**:"initial A, then B" → LLM 抽 A
4. **同名异病**:AMN 是 Acute macular neuroretinopathy 还是 Adrenomyeloneuropathy?LLM 撞错
5. **诊断不确定**:"novel form of X" → 不算金标准

`hpo_phenotypes_extracted` (K 列) 同理,LLM 可能把鉴别诊断的症状 / 化验值 /
无关词混进列表。

**你的工作 = 替我们抓出这些错误,直接写下正确答案**。

---

## 2. 你要填的两列(L 和 M)

| 列 | header 指引 | 怎么填 |
|---|---|---|
| **L** | `正确诊断 (LLM 抽错时填; 对则空)` | LLM 抽的 `disease_name` 对 → **留空**;错 → 直接写正确的疾病名(英文,跟文章一致) |
| **M** | `错误 HPO terms (用 ; 分隔; 全对则空)` | HPO 列表全对 → **留空**;有错 → 把错的 term **原样列出来**,用 `;` 分隔(比如 `cardiac arrest; aortic root dilatation`) |

**举例**:
- 文章是 Werner syndrome 病例,LLM 抽对了,HPO 也全对 → **L 空,M 空**
- 文章是 Adrenomyeloneuropathy (ABCD1),LLM 误抽 "AMN" → Acute macular neuroretinopathy →
  **L 填 `Adrenomyeloneuropathy`,M 空**
- 文章是 Loeys-Dietz 但 LLM 抽成 Marfan,且 LLM 把鉴别诊断里 "ectopia lentis" 混进了 HPO →
  **L 填 `Loeys-Dietz syndrome`,M 填 `ectopia lentis`**
- 整行没法判(文章读不出来 / 太诡异):L 写 `?`,M 留空,跳到下一行

---

## 3. 工作流(每行 2–4 分钟)

1. 看 **D 列 `disease_name`**(LLM 抽的诊断)+ **E 列 `omim_ids`** (cross-ref)
2. 看 **I 列 `case_excerpt`** — 已自动定位到 "final diagnosis" 段(~2000 字符)
   - J 列 `has_final_dx_string = yes` → excerpt 命中关键短语,高可信
   - `= no` → excerpt 是文章前 1800 字 fallback,**双击 C 列 `local_xml` 路径**
     打开 `pmc_fulltext/PMC<id>.xml.gz` 看全文
3. 判断诊断 → 错就在 **L 列** 写对的
4. 看 **K 列 `hpo_phenotypes_extracted`** 对照 case_excerpt
5. HPO 有错 → 在 **M 列** 列出错的 term

---

## 4. 常见陷阱

**同名异病**(看基因 / 主轴 disambiguate):
- AMN = Adrenomyeloneuropathy (ABCD1) **vs** Acute macular neuroretinopathy
- JPS = Juvenile Polyposis Syndrome (SMAD4) **vs** Job's syndrome (STAT3)
- 3M syndrome → 必须看基因 CUL7 / OBSL1 / CCDC8
- "dengue shock syndrome" 误映射到 "CK syndrome"

**Case series 多 patient**:LLM 可能把不同 patient 的信息混在一起。
如果 excerpt 明显混乱 → M 列直接列错的 HPO,L 列可写 `(case series, multiple patients)`。

**改诊断**:"initially diagnosed as A, but genetic testing confirmed B" →
L 写正确的(B),即使 A 也是 Orphanet 词。

**HPO 噪声判断**:
- 不该出现:鉴别诊断里别人的症状、化验值/影像描述、完全无关
- 可出现:Prenatal/家族受累 case 里亲属的 phenotype(算合理家族证据)

---

## 5. 包里有什么

```
HANDOFF_v3/
├── README.md                       ← 本文件
├── review_workbook.xlsx            ← 你的工作文件
│      Sheet `review`:198 行 × 13 列 (11 自动 + L M 两列你填)
│      Sheet `demo_examples`:6 个填法示范
├── pmc_fulltext/                   ← 198 篇 PMC 全文 (.xml.gz)
└── candidates_full_pool.jsonl      ← 1,433 候选完整池 (备用)
```

不需要联网。

---

## 6. 输出 — 完成后回传

只回传填好的 `review_workbook.xlsx`。

我们后台直接读 L 和 M 列:L 空 = 诊断对,L 非空 = 诊断错(新诊断已知);
M 空 = HPO 全对,M 非空 = 错的 term 列表已知。

---

## 7. 有问题

- 诊断对/错都不确定 → L 写 `?`
- 发现某类病例系统性错误(几个 case 同一个 pipeline bug)→ 告诉我们
- 自动 case_excerpt 截得不对 → 打开 `local_xml` 看全文
