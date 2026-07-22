# 罕见病病例人工核验 — 交接包 (v2)

> **给医学专业标注人员**:本包**只保留需要医学判断的工作**。
> 出版日期(Check 3)和疾病罕见度(Check 4)已自动完成,你只做 Check 1 + Check 2。

---

## 1. 一句话任务

打开 `review_workbook.xlsx`,**审~200 行病例**,对每行的两个临床问题打 `pass` / `fail`,
最后给出 `accept` / `reject`。预计每行 3–5 分钟(无需写 fail 类的解释,通过 `pass/fail`
+ decision 三个下拉就够了)。

---

## 2. 包里有什么

```
HANDOFF_v2/
├── README.md                       ← 本文件,只读这一份就够
├── review_workbook.xlsx            ← 你的工作文件(3 个 Sheet,见 §3)
├── pmc_fulltext/                   ← 250 篇 PMC 文章本地全文(.xml.gz)
│   ├── PMC13074162.xml.gz
│   ├── PMC10766305.xml.gz
│   └── ... (250 个)
└── candidates_full_pool.jsonl      ← 1,433 候选完整池(250 不够时翻这个)
```

**不需要联网**。所有 PMC 文章都已下载到 `pmc_fulltext/`,xlsx 主表里有 `local_xml`
列直接指向本地路径。

---

## 3. xlsx 的 3 个 Sheet

### Sheet 1: `review` — 主表,250 行,你在这里填

每行一个候选病例。19 列**自动填好(灰底,只读)**,5 列**等你填(橙色表头)**。

**自动填好的关键列**(你审时主要看这几个):

| 列 | 是什么 |
|---|---|
| `pmc_id` / `pmc_url` / `local_xml` | 文章 ID + 在线链接 + 本地全文路径 |
| `orpha_id` / `disease_name` / `omim_ids` | 自动匹配到的罕见病及交叉引用 |
| `age` / `sex` / `has_family_history` | 病人基本信息 |
| `pub_pmc_date` | PMC 发布日期(自动从 XML 抽) |
| `prevalence_band` | Orphadata 验证过的疾病流行率(如 `1-9 / 1 000 000`) |
| **`auto_check3_decision`** | **自动判定:这是 2024+ 新报告吗?** `pass` / `fail` / `uncertain` |
| `auto_check3_reason` | LLM 给的判定理由 |
| **`auto_check4_decision`** | **自动判定:真的是罕见病吗?** 同上 |
| `auto_check4_reason` | Orphadata 查表理由 |
| `case_excerpt` | **PMC 全文中包含"Final diagnosis"那段**(已自动定位,2000 字符内) |
| `has_final_dx_string` | excerpt 里是否真的找到 "final diagnosis" 字样(`yes` = 高可信,`no` = excerpt 是 fallback 前 1800 字) |
| `hpo_phenotypes_extracted` | 自动抽出的临床表型(`;` 分隔) |
| `top_alternatives` | 自动匹配时考虑过的前 3 个 ORPHA 候选 |

**等你填的 5 列**(橙色表头,带下拉):

| 列 | 选项 | 你做什么 |
|---|---|---|
| `check1_diagnosis_match` | `pass` / `fail` | 看 `case_excerpt` 末尾,文章给的诊断**真的是病人的 final / 确诊**吗?(排除 suspected / 鉴别诊断 / 改过的诊断 / 同名异病) |
| `check2_hpo_accurate` | `pass` / `fail` | 看 `hpo_phenotypes_extracted` 对照 `case_excerpt`,这些表型**真的是这个病人有的**吗?(>30% 噪声 = fail) |
| `hpo_phenotypes_clean` | `true` / `false` | 辅助列,**不阻塞 accept**。≤30% 噪声 = true。Prenatal/家族案例的亲属表型不算噪声 |
| `review_decision` | `accept` / `reject` / `uncertain` | 4 个 check 全 pass(2 人工 + 2 自动) → accept;任一 fail → reject;有疑问 → uncertain |
| `reviewer_notes` | 自由文本 | reject / uncertain / 想 override 自动 check 时**必填**(说明哪个 check fail + 证据) |

### Sheet 2: `prevalence_reference` — 只读参考

250 行候选用到的 ORPHA 流行率全表(已查 Orphadata `en_product9_prev.xml`)。
当 `auto_check4_decision = uncertain` 时(常见原因:这个 ORPHA 是某个 disorder
的 *clinical subtype* / *subgroup*,本身没单独 prevalence),来这表查它的
`all_bands_seen` / `disorder_type`,然后:
- 如果是 subtype 且父 disorder 是罕见病 → Check 4 **override 成 pass**,在 notes 注明
- 如果非 subtype 但 Orphadata 干脆没数据 → 标 `uncertain` 留二轮

### Sheet 3: `demo_examples` — 只读参考

前 10 个候选的 demo 审核(9 accept + 1 reject)。看 `reviewer_notes` 学风格。

---

## 4. 工作流(每行 3–5 分钟)

> **核心简化**:Check 3 + Check 4 自动了。你**只看 Check 1 + Check 2**。

每行按这个顺序:

1. **先看 `auto_check3_decision`**:
   - = `fail` → 该行**整行可跳过**(自动认定为非 2024+ 新报告)。你直接 `review_decision = reject`,notes 写 `"auto_check3_fail: <reason 摘要>"`,下一行。
   - = `pass` → 进 step 2。
   - = `uncertain` → 罕见,人工看一眼 `auto_check3_reason`,自己判。

2. **再看 `auto_check4_decision`**:
   - = `pass` → 直接进 step 3,不用查 Orphadata。
   - = `uncertain` → 翻 Sheet 2 `prevalence_reference` 看 disorder_type 是不是 subtype,
     给 Check 4 一个 override(详见 §3 Sheet 2)。
   - = `fail` → 整行 reject(理论上不该出现,因为我们前置只挑罕见病,但 Orphadata 数据更新会发生)。

3. **Check 1 — 诊断匹配正确?** (`check1_diagnosis_match`)
   读 `case_excerpt`。该 excerpt **已经自动定位到包含 "final diagnosis" 等关键短语
   的段落**(如果 `has_final_dx_string = yes`),你直接看这段就够。
   - excerpt 末尾找到 "A final diagnosis of X was made" / "the patient was diagnosed
     with X" / "definitive diagnosis of X" ,且 X 等于 `disease_name` → **pass**
   - excerpt 写 "suspected X but ..." / "differential diagnosis included A, B, C" /
     "later confirmed to be Y" → **fail**
   - 同名异病陷阱(看 `top_alternatives` 是否提示):
     - "AMN" = Adrenomyeloneuropathy(ABCD1)或 Acute macular neuroretinopathy → 看基因
     - "JPS" = Juvenile Polyposis Syndrome(SMAD4)或 Job's syndrome(STAT3) → 看基因
     - "3M syndrome" → 必须看基因 CUL7/OBSL1/CCDC8 确认
   - `has_final_dx_string = no` 时,自动 excerpt 是文章前 1800 字 fallback,可能不含
     final dx 段。这时打开 `local_xml`(双击 `pmc_fulltext/PMC<id>.xml.gz` 解压
     或用浏览器打开 `pmc_url`)定位 Diagnosis / Conclusion 段。

4. **Check 2 — HPO 表型准确?** (`check2_hpo_accurate`)
   对照 `hpo_phenotypes_extracted` 和 `case_excerpt`:
   - 列表里的临床表型**真的是这个病人有的**吗?
   - **不应该包括**:鉴别诊断里提到的他人/其他病的症状、化验值/影像描述、完全无关词
   - 噪声 ≤30% → **pass + `hpo_phenotypes_clean = true`**
   - 噪声 >30% → **fail**
   - Prenatal/家族受累 case:proband 是胎儿/新生儿时,父母/兄弟姐妹的 phenotype
     出现在列表里是合理的家族诊断证据,不算噪声(`has_family_history = True` 时尤其检查)

5. **填 `review_decision`**:
   - Check 1 = pass **AND** Check 2 = pass **AND** auto check 3 = pass **AND**
     auto check 4 = pass (或被你 override 成 pass) → **`accept`**
   - 任一 fail → **`reject`**(简单 case 不用写 notes;复杂的写一句)
   - 有疑问 → **`uncertain`**,notes 必填疑问点

---

## 5. 颜色 / 视觉提示

- **橙色表头** = 你要填的 5 列
- **蓝色表头** = 自动填的列(灰底,只读)
- **绿色单元格** = 自动 check 通过(pass)
- **黄色单元格** = 自动 check 不确定(uncertain),你需要判
- **红/粉单元格** = 自动 check 失败(fail),通常直接 reject

---

## 6. 预期工作量

```
总候选 250 行
 ├── 自动 Check 3 fail (出版日期/republication 问题): 52   → 你直接 reject,~30 秒/行
 ├── Check 3 pass + Check 4 pass (干净候选):       153  → 完整 Check 1+2,3–5 分钟/行
 └── Check 3 pass + Check 4 uncertain (需查 subtype): 45   → +1 分钟查 prevalence sheet
```

**目标**:累计 ~200 个 `accept` 即停;若 250 行不够,从 `candidates_full_pool.jsonl`
第 251 行起补 fuzzy 候选(本目录已附该 jsonl,可用任何文本编辑器打开,每行一个 JSON)。

**理想节奏**:每天 40–60 行(3 小时),~5 天完成。

**质控建议**:每 50 个 case 抽 5 个让有医学背景的同事抽检(20% 重审率),
或随机交叉 20 个让另一个标注员审,算 Cohen's κ ≥ 0.6。

---

## 7. 自动 check 怎么生成的 (供你审计 / 不放心时核)

### Check 3 (出版日期 / republication)

- 工具:Gemini 3 Flash LLM (`google/gemini-3-flash-preview-20251217`),`temperature=0`
- 输入:文章 title + abstract + 正文前 3000 字 + 用 regex 预筛出的可疑短语
  (e.g. "previously reported in", "case series of", "follow-up of")
- 输出:`{decision, reason, evidence_quote}`
- pass 判据:PMC 发布日期 ≥ 2024-01-01 **且** 无 republication 信号
- fail 判据:发布日期 < 2024-01-01,**或**正文里有清晰的 pre-2024 cohort/回顾性
  指标

LLM 不完美,**如果你发现明显误判**(比如把一个真正的 2024+ 新报告判 fail),
直接在 `reviewer_notes` 写 `"override auto_check3: <reason>"`,然后 review_decision
按你自己的判断填。

### Check 4 (是否罕见病)

- 工具:**本地 Orphadata 查表**(`data/orphadata/en_product9_prev.xml`,6,443 条
  disorders,2025-Q1 dump),无 LLM 调用
- 算法:取每个 ORPHA 所有 **Validated** 的 prevalence class,选 rarest
  (tie-break 优先 Point prevalence)
- pass:rarest validated band 在 `{<1/1M, 1-9/1M, 1-9/100k, 1-5/10k, 6-9/10k}`
- fail:band = `>1/1000`(Orphadata 标的"非罕见")
- uncertain:没找到 validated entry / 是某 disorder 的 clinical subtype
  (subtype 不带独立 prevalence,需查父 disorder)

uncertain 主要打到 subtype。Sheet 2 `prevalence_reference` 提供该 ORPHA 的
`disorder_type` 列辅助判断。

---

## 8. 输出 — 完成后回传

只回传 `review_workbook.xlsx`(填好的 Sheet 1)。其他文件不变。
对方会从 Sheet 1 的 `review_decision` 列直接读取结果。
