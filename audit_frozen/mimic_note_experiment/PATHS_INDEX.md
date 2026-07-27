# MIMIC-IV 实验 — 筛选过程 & 所有结果的绝对路径索引

> 一站式路径清单（可复制）。生成于 2026-07-26。
> 仓库根：`/home/research/RDAgentBenchmark`
> ⚠️ `data/` 全目录 gitignored（PhysioNet DUA）；行级 MIMIC 文本/ID 绝不入库，仅聚合指标/hash/路径可分享。

---

## 一、数据筛选过程记录（文档）

| 内容 | 绝对路径 |
|---|---|
| **权威筛选流程**（150,033 → 491 → 416 全漏斗 + 每步脚本 + sha256） | `/home/research/RDAgentBenchmark/audit_frozen/mimic_note_experiment/README.md` |
| 数据准备阶段状态（解压/cohort/去泄露自检） | `/home/research/RDAgentBenchmark/audit_frozen/mimic_note_experiment/mimic_note_v2_status.md` |
| 泄露量化（为什么旧 0.35–0.38 不可信，逐行代码证据） | `/home/research/RDAgentBenchmark/audit_frozen/mimic_frozen_audit/mimic_leakage_quantification.md` |
| MIMIC 冻结审计总结 | `/home/research/RDAgentBenchmark/audit_frozen/mimic_frozen_audit/mimic_final_audit.md` |
| 泄露审计（case-level） | `/home/research/RDAgentBenchmark/audit_frozen/leakage_audit/leakage_summary.md` |

## 二、结果（打分 + 文档）

> **状态（2026-07-26 闭环）**：24-cell 全部完成，每格 present=416/416；全矩阵 9984 样本中
> 计入分母的 fail = **1118（11.2%）**（parser_error 598 / timeout 362 / agent_error 136 /
> empty_ok 22），全部按 miss 计入 416 分母，无 success-only 灌水。maidxo×4 已用正则修复版重跑完毕。

| 内容 | 绝对路径 |
|---|---|
| **打分结果 manifest**（24-cell 主矩阵，score-only，raw 口径，含逐格 status 明细） | `/home/research/RDAgentBenchmark/audit_frozen/mimic_note_experiment/agent_matrix_scores.json` |
| **before/after 去泄露 manifest**（4 backbone 裸 LLM，同案 416） | `/home/research/RDAgentBenchmark/audit_frozen/mimic_note_experiment/before_after_scores.json` |
| **结果文字版**（新增「24-cell agent 矩阵」节 = R@1 表 + 主结论精确措辞 + 三红旗定性 + 限定语 caveat；另含 before/after 表 + 2-model 探针 + H7 分层） | `/home/research/RDAgentBenchmark/audit_frozen/mimic_note_experiment/mimic_note_v2_results.md` |

## 三、逐案预测（receipt，gitignored）

| 内容 | 绝对路径（目录） |
|---|---|
| **去泄露后 24-cell 主矩阵**（6 agent × 4 backbone × 416） | `/home/research/RDAgentBenchmark/data/round2/phase4a_mimic_note/` |
| **before 泄露版**（llm_control × 4 backbone × 416，新增） | `/home/research/RDAgentBenchmark/data/round2/phase4a_mimic_note_leaked/` |
| 2-model 探针原始预测（DeepSeek/Opus） | `/home/research/RDAgentBenchmark/data/mimic_iv_rd_slice/predictions_mimic_note_deepseek_v4.jsonl`<br>`/home/research/RDAgentBenchmark/data/mimic_iv_rd_slice/predictions_mimic_note_opus48.jsonl` |
| **maidxo 旧 bug 版备份**（正则修复前的废结果，留档供审计追溯，不进打分） | `/home/research/RDAgentBenchmark/data/round2/_maidxo_prefix_backup_prefix/` |

> **maidxo 打分用的是重跑版，不是旧 bug 版**（曾被质疑过）。自证在结果文档
> `mimic_note_v2_results.md` §「自证：maidxo 打分用的是正则修复后重跑版」：manifest 的
> `hits_r1` 4 格 = 1/2/0/2、`n_ok` = 272/256/357/262，**精确等于现役文件**；旧 bug 版为
> 2/0/0/3 与 352/363/391/279，一格未匹配。行均值同为 0.003 只是显示精度巧合。

## 四、冻结输入数据（gitignored）

| 内容 | 绝对路径 | 说明 |
|---|---|---|
| **去泄露 416 探针**（主矩阵用） | `/home/research/RDAgentBenchmark/data/mimic_iv_rd_slice/note_eval_hpo_line_v1.jsonl` | sha256 67d156aa… |
| **before 泄露版 416**（同案，全文不截断不 mask） | `/home/research/RDAgentBenchmark/data/mimic_iv_rd_slice/note_leaked_v1_416.jsonl` | sha256 df7b8f40… |
| cap10 491（2-model 探针用） | `/home/research/RDAgentBenchmark/data/mimic_iv_rd_slice/note_eval_cap10_v2.jsonl` | |
| 严格 A 类 359 | `/home/research/RDAgentBenchmark/data/mimic_iv_rd_slice/note_eval_strict_A_v1.jsonl` | |

## 五、关键脚本（可复现，除打分外均无 LLM 调用、确定性）

| 步骤 | 绝对路径 |
|---|---|
| 去泄露 + 造 before 泄露版（`--leaked --restrict-to`） | `/home/research/RDAgentBenchmark/scripts/build_mimic_note_deleaked.py` |
| 四门可评测过滤 | `/home/research/RDAgentBenchmark/scripts/build_mimic_note_eval_subset.py` |
| 剔既往已知病型 | `/home/research/RDAgentBenchmark/scripts/filter_mimic_note_prior_known.py` |
| 严格 A 类（堵同义词泄露） | `/home/research/RDAgentBenchmark/scripts/build_mimic_note_strict_A.py` |
| HPO 线 416（器官系统分层对齐） | `/home/research/RDAgentBenchmark/scripts/build_mimic_note_hpo_line.py` |
| 24-cell 打分器（score-only） | `/home/research/RDAgentBenchmark/scripts/score_mimic_note_matrix.py` |
| **before/after 打分器**（4 backbone 裸 LLM，同案 416） | `/home/research/RDAgentBenchmark/scripts/score_mimic_note_before_after.py` |
| 2-model 打分器 | `/home/research/RDAgentBenchmark/scripts/score_mimic_note_llm.py` |
| 实验 runner（跑 agent×backbone） | `/home/research/RDAgentBenchmark/scripts/phase4a_runner.py` |
| **限定语清洗敏感性分析**（只读，量化清洗对 24-cell 净影响，产出 caveat 表） | `/home/research/RDAgentBenchmark/scripts/_audit_qualifier_cleaning_sim.py` |
| maidxo 重跑脚本（正则修复后，含首跑/重跑备份保护） | `/home/research/RDAgentBenchmark/scripts/rerun_maidxo_after_regexfix.sh` |

---

### 两个 case 集口径（重要）
- **416**（`note_eval_hpo_line_v1`）：6-agent × 4-backbone 主矩阵 + 器官系统分层 + before/after 前后对比。
- **491**（`note_eval_cap10_v2`）：2-model（DeepSeek/Opus）均衡评测集。
- 两者仅重叠 253 例，**不是子集**。前后对比锁 416。
