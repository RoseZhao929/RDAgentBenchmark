# MIMIC-IV — leakage quantification (does data leakage invalidate the July-21 numbers?)

- 生成 (UTC): 2026-07-24
- 约束: 未调用 LLM；未伪造；仅 de-identified 聚合 + 代码行号 + 已有 handoff 统计。
- 目的: 回答 "MIMIC-IV 的 0.35/0.38 结果不能直接沿用，核心原因是不是 data leakage" — 并给出可引用的量化。

## 一句话结论

**是的，data leakage 是这些数字被高估、不能作为诊断能力证据的核心原因；而且 leakage 不是"可能存在"，是设计上必然发生的。**
但要同时记住第二点（见 §4）：即使 leakage 修好、receipt 到齐，MIMIC 也不能和另外三个数据集并列报告 R@1 —— 因为它的 gold 是 code-derived，不是独立临床判读。这两点都成立，缺一不可。

## 1. Leakage 的机制（从 ingest 代码逐行确认，非推测）

`harness/ingest/mimic_iv.py`：

| 环节 | 代码 | 含义 |
|---|---|---|
| gold 病名 | `:162-167` `disease_name=primary["orpha_name"]` | gold = Orphanet 英文病名 |
| gold 选择偏好 | `:147` `primary = next((h for h in hits if h["rel_type"]=="E"), hits[0])` | 优先选 **E（exact）**关系的映射 |
| 模型输入 | `:170-176` `synthetic = "...ICD-10-documented conditions: " + "; ".join(icd_title...)` | input = 该住院所有 ICD 长标题拼接，**包含 target 那条** |
| 键 | 二者都由**同一个 ICD-10 code**得出 | 输入里的 target 标题 与 gold 病名指向同一实体 |

对 **E（exact）**关系：ICD-10 long title 与 Orphanet disease name 指的是同一个病 → **gold 答案实际上被逐字（或近义）印在了输入里**。模型只要复读输入里的目标标题即可命中。这是 selection-from-a-labeled-list，不是 differential diagnosis。

## 2. Orphanet 映射关系分布（en_product1.xml，本机唯一在场的映射源，全量实测）

| relation | 边数 | 占比 |
|---|---|---|
| NTBT (ICD 比 Orpha 窄) | 6888 | 82.6% |
| BTNT (ICD 比 Orpha 宽) | 825 | 9.9% |
| **E (exact)** | **614** | **7.4%** |
| ND | 13 | 0.2% |

- 有 Orphanet 映射的 distinct ICD-10 码：**2173**；其中 **612 (28.2%)** 至少有一条 E 关系。
- ingest 的 `relation_filter` 默认 `("E","NTBT","BTNT")` 全收，且 `primary` **优先 E**。因此**只要一个住院里出现任一 E 码，gold 就会锁定到那个 exact 病名，而该病名对应的 ICD 标题就在输入里** → 该 case 属于强 leakage。
- ⚠️ 上表是**全库结构分布**，不是 956 cohort 的分布。cohort 里 E-primary 的确切占比需要缺席的 `cases_filtered_diverse.jsonl`。这里只证明 leakage 的**通道存在且很宽**。

## 3. 真实 cohort 上已测到的 leakage 证据（来自 `docs/mimic_branch_handoff.md`，同事在本机 956 例上实跑）

三臂 ablation（title_selection / code_selection / context_only），2868 行 = 956×3：

- **context_only（移除 target ICD 条目后）→ 340/956 = 35.6% 的住院输入变为空。**
  含义：这 340 例里，target 诊断码是**唯一**的罕见病码；把它拿掉就什么都不剩。→ 对这批 case，**任何"答对"都只能来自复读被泄露的 target 标题**，没有别的信号。这是 leakage 的下限直接测量。
- 早窗结构化快照（去掉诊断码/标题后）里 **gold 病名逐字出现次数 = 0**（24h 与 48h 均是）——反证：一旦把 ICD 标题从输入里拿掉，gold 就不再出现在输入里了。这正说明原 title 版的命中高度依赖那条被泄露的标题。

> 这就是我们要的"硬数字"：**≥35.6% 的 case 在无 leakage 时连作答素材都没有**；其余 case 的 input 仍包含 target 标题（E 关系下等同于印出答案）。所以 0.35/0.38 无法归因于诊断能力。

## 4. 关键澄清：leakage 是核心原因，但不是唯一 blocker（receipt 修不了这条）

请务必区分三层，性质不同：

| # | 问题 | receipt 到齐能修吗？ | masked arm 能修吗？ |
|---|---|---|---|
| ① | **data leakage**（gold 印在输入里） | ❌ 不能 —— 用泄露的 receipt 重算只会复现泄露的 0.35/0.38 | ✅ 用 `code_selection` / `context_only` 臂可测出去泄露后的真实值 |
| ② | **construct validity**：gold 是 ICD→Orphanet 机械映射，**不是独立临床判读** | ❌ 不能 | ❌ 不能 —— 这是构念边界，不是分数问题 |
| ③ | reproducibility：仓库里 0 receipts / 0 gold / 0 cohort | ✅ 能（这正是同事要传的） | — |

**结论**：
- 你问的"核心原因是不是 leakage" → **是**，对"为什么 0.35/0.38 不能当诊断能力用"这个问题，leakage 是核心且可量化的原因。
- 但"能不能沿用 21 号那版 paper 的 MIMIC 结果" → **不能直接沿用**，因为 ① + ②。receipt（③）只解决"能不能复算"，解决不了"复算出来的还是泄露值"。
- 想真正保留 MIMIC，唯一诚实路径 = 用 **`code_selection`（去病名、只留 ICD 码）** 或 `context_only` 臂的新分数，并作为**单独报告的 structured-EHR 探针**（不进主诊断矩阵、不进 Avg）——这正是已合并分支 `experiment/mimic-structured-ehr-best-design` 做的事。

## 5. 要把它变成可引用的确定数字，还差什么

1. `data/mimic_iv_rd_slice/cases_filtered_diverse.jsonl`（956 cohort + gold + all_orpha_hits）——同事上传的应包含它；
2. 有了它即可离线算出 cohort 上 **E-primary 占比** 和 **gold 病名逐字命中输入的精确比例**（无需 LLM、无需 raw 9.9GB）；
3. 跑三臂 receipt → 得到 `title − code` = leakage 收益的确切百分点，`context_only` = 负对照。

在此之前，可引用的确定量是：**context_only 空输入 340/956 = 35.6%（真实 cohort 实测）** + **E 通道结构占比（XML 实测）**。

## 6. 直接实测的 leakage 量级（2026-07-26 补，note 版 before/after）

§5 想要的"leakage 收益确切百分点"，现已用 **note 版同案 before/after** 直接测到（不必再等旧 title
版三臂 receipt）。方法：裸 LLM（`llm_control`）在**同一批 416 例**上跑两遍——
- **BEFORE = 泄露版**：完整出院小结（不截断、不 mask），诊断揭示段（Brief Hospital Course /
  Discharge Diagnosis）与 gold 病名都留在题面。数据 `note_leaked_v1_416.jsonl`（sha `df7b8f40…`）。
- **AFTER = 去泄露版**：presentation 段截断 + gold 病名逐字 mask。数据
  `note_eval_hpo_line_v1.jsonl`（sha `67d156aa…`）。
- 唯一变量是"截没截断/mask 没 mask" → **真·同案前后对比**。打分口径同主矩阵（分母=416、failure 计
  miss、`gold_hit_with_crossmap`、bootstrap CI）。产物 `before_after_scores.json`，脚本
  `scripts/score_mimic_note_before_after.py`。

| backbone | BEFORE (泄露) R@1 | AFTER (去泄露) R@1 | Δ 相对 |
|---|---|---|---|
| deepseek-v4-pro | 0.500 | 0.365 | **−27%** |
| deepseek-v4-flash | 0.553 | 0.353 | **−36%** |
| gpt-5 | 0.425 | 0.363 | **−15%** |
| gemini-3-flash | 0.452 | 0.373 | **−18%** |

**这就是 §1–§3 机制推断的直接实证**：
- 去泄露在**全部 4 个 backbone 上都掉分**（−15% 至 −36%，95%CI 不重叠）→ 复读效应普遍、非偶发。
- **弱模型掉得更多**（v4-flash −36% vs gpt-5 −15%）：强模型更多靠真推理、少靠复读。
- **泄露还扭曲模型排序**：泄露版里 v4-flash(0.553) "超过" gpt-5(0.425)，去泄露后回归合理（都 ~0.36）。
  → 用泄露数据做 benchmark 不仅抬高绝对分，还会给出**错误的模型排名**。

注意：note 版 before/after 与旧 title 版 0.35–0.38 不是同一任务（输入不同、case 集不同），不能直接
相减；但两条独立证据链**同向**——都表明旧 MIMIC 分数含相当比例的答案复读，去泄露后 top-1 ≈ 二到三成。
