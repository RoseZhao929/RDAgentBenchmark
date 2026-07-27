# MIMIC-IV slice — Final Audit (post-merge)

- 生成时间 (UTC): 2026-07-24T07:53:13Z
- 冻结 commit (HEAD): `e8c2d19f8c7f1dbfa89fe7df1b6ad8a1ab876fe1`（已合并分支 `experiment/mimic-structured-ehr-best-design`）
- 约束: 未调用任何 LLM；未伪造任何预测/分数；未输出受限 MIMIC 原文（仅 de-identified 聚合与 hash）。

## 一句话结论

**当前仓库中不存在任何可打分的 MIMIC 结果。** 唯一残留的是 22 个 legacy 聚合 cell，且**彼此矛盾**（22 中 13 个两源直接冲突），只能作为 provenance 保留、**不可作为有效证据**。合并后的分支已把 MIMIC 从主诊断矩阵下架、重设为"另行报告的结构化 EHR (S-EHR) 探针"，但**新的 replacement 分数尚未跑出**。

状态：`NOT_REPRODUCIBLE`（旧诊断分数） → 合并后升级为 `RE-SPECIFIED / PENDING-SCORING`（S-EHR 探针）。

## 硬证据（全机器核实，非仅本 checkout）

| 项 | 数量 | 来源 |
|---|---|---|
| MIMIC prediction receipts (`predictions_mimic_*.jsonl`) | **0** | `find / ` 全机器 0 命中 |
| cohort 文件 (`cases_filtered_diverse.jsonl`) | **0** | `find /` 0 命中（gitignore + credentialed，本机不存在） |
| gold labels | **0** | `recompute_engine.load_gold()` 硬编码 `mimic_diverse n_gold_cases=0` |
| `frozen_main_manifest.csv` 中 MIMIC 行 | **0** | 83 行全为其余 5 数据集 |
| 可打分 case-level 行 | **0** | 无 receipts × gold，无法打分 |
| legacy 聚合 cell | 22 | `data/round2/phase4a_receipts.csv` |
| legacy cell 两源冲突 | **13 / 22** | round2 vs `new_version_paper/headline_results.csv` |

## legacy 聚合互相矛盾（示例）

同一 cell `llm_control | deepseek-v4-pro`：
- `round2/phase4a_receipts.csv`：**attempted 956, R@1v 0.248**
- `new_version_paper/headline_results.csv`：**attempted 402, R@1v 0.264**

无 receipts 无法对账 → 两者都不可信。round2 多个 cell 还有 `n_err=0 & n_ok=956` 的 success-denominator 迹象，与"failures 计入分母"的评测口径不一致。

provenance hash（round2 MIMIC 块 sha256）：`fe3257e4123f84e916ff6583da12e9904927066208544f77506f8104ff8cf656`

## 三层问题（性质不同）

1. **synthetic vignette 把 ICD 长标题渲染进输入** — 实验**设计 bug**，可修（分支的三臂 ablation：title/code/context_only 正是修复方案）。
2. **无 MIMIC-IV-Note**（本机仅 hosp/+icu/） — 数据可得性，需另申请。
3. **gold 是 code-derived**（ICD→Orphanet 机械映射） — 构念效度边界，修不掉，只能诚实降级为 S-EHR 探针单独报告。

## 合并后的论文状态（已核实）

- 主诊断矩阵（`6_main_results.tex`）**不含 MIMIC 列**：明写 "MIMIC-IV is not a column in this diagnostic matrix … reported separately"。
- abstract / §2 / §4.2 保留 MIMIC 为 **S-EHR 探针**（956 code-supervised admissions；no clinical notes；replacement scoring **pending**）。
- 旧 MIMIC 点估计（0.38/0.39/0.56/0.248 等）在主表/成本/消融中 **grep 0 命中**，已清除。
- figM1 标题改为中性 "comparison scope: 3 of 5 datasets"；figM5 的 mdagents 画虚线 + "(trace repaired)"，§7.5 更名 "Coupled Family/Trace Confounds"。
- ablation 单元测试 4/4 通过（合成 fixture）。

## 本目录产物说明（诚实标注）

| 文件 | 内容 | 真实性 |
|---|---|---|
| `mimic_final_audit.md` | 本审计报告 | 审计事实 |
| `mimic_frozen_manifest.csv` | 22 legacy cell，每行标 `scorable_receipt_rows=0`、`gold_available=NO`、两源冲突标记 | provenance-only，**非结果** |
| `mimic_results_summary.json` | 审计状态摘要 + 冲突示例 + 补齐路径 | 审计事实 |
| `mimic_case_level_results.csv` | **空**（表头 + `__NO_DATA__` sentinel 行） | 0 真实 case，无法打分 |
| `predictions_mimic_PLACEHOLDER.jsonl` | 1 条 `__status__=NO_RECEIPTS` 记录 | **占位**，0 条预测；拒绝伪造 |
| `mimic_frozen_audit.md` / `mimic_evidence_inventory.csv` / `mimic_paper_patch.md` | 前序审计（合并前） | 审计事实 |

> ⚠️ `predictions_mimic_*.jsonl` 与 `mimic_case_level_results.csv` **无法产出真实内容**：需要不存在的 receipts × gold。我给出的是明确标注的占位/空壳，绝不冒充结果。合成预测行等于伪造，已拒绝。

## 补齐为真实结果所需（无需 raw 9.9GB）

1. `data/mimic_iv_rd_slice/cases_filtered_diverse.jsonl`（956 cohort + gold）—— 向原作者 `yutianzhao` 索取（credentialed）；
2. 按 `docs/mimic_structured_ehr_experiment.md` 跑三臂 + 早窗模型矩阵（付费模型调用，需授权），写出带 task-version / cohort-hash / prompt-hash 的新 receipt；
3. 用 `audit_frozen/recompute_engine.py` 同口径（failures 计入分母）打分。

有了 ① + receipts 即可离线打分，**无需重跑模型**。
