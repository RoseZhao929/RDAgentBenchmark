frozen_v2_20260728 — RareAgentBench 实验结果冻结版

建立时间：2026-07-28。取代此前散落的 N10/部分完成态快照。

内容
- predictions_deduped/          104 个去重后的 cell（每 case 一行，优先 ok；原始重复行已清）
- cell_inventory.json           每 cell 的 raw/unique/dup/valid/覆盖统计
- coverage_matrix.csv           同上，表格形式
- frozen_manifest_rows.json     recompute_engine 重算的 per-cell R@1（attempted 分母，variant-aware）
- frozen_main_manifest.csv      build_deliverables 产物（画图用）
- mimic_n_agent_matrix_scores.json  MIMIC-N 416 例 de-leaked 矩阵（单独口径）
- FREEZE_REPORT.md              定版报告：重复根源、覆盖率、需重跑清单、valid 分析

口径
- R@1 = hits / n_attempted（失败/超时/空也计入分母）；variant-aware 用 crossmap
- MIMIC-N 用固定分母 416
- 重复来自 resume/retry，非原始 dataset；去重不改变 recompute 数值（引擎本就按 case_id 去重）

复现：/tmp/paper_venv/bin/python audit_frozen/recompute_engine.py
