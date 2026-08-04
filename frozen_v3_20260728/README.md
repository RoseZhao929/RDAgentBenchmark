frozen_v3_20260728 — phase4a 当前现状定版(排除待补73 + 待重跑4)

- predictions_deduped/ 去重后 104 cell
- cell_inventory.json / coverage_matrix.csv 每 cell 统计 + status
- frozen_manifest_rows.json 重算 R@1
- mimic_n_agent_matrix_scores.json MIMIC-N 416
- FREEZE_REPORT.md 可用/待重跑/承认特性 三类清单

复现: /tmp/paper_venv/bin/python audit_frozen/recompute_engine.py
