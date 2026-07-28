RareAgentBench 论文 — 实验数据更新 SOP

用途：每当有新实验数据（补跑 cell、扩样本、新 backbone）进来时，按本流程把冻结结果和论文同步更新。只改 main results 及以后（MainResults.tex）+ 必要时 Supplementary 的 cost 段；绝不动 AnonymousSubmission2027.tex 等前面的部分。

环境
- 依赖装在 /tmp/paper_venv（scipy/numpy/matplotlib/pandas/pydantic/requests/lxml）。系统 python 无这些包。
- 重算/画图一律用 /tmp/paper_venv/bin/python。

数据源与产物链（谁喂谁）
1. data/round2/phase4a/predictions_*.jsonl  — 每个 cell 的 case-level receipts（原始）
2. audit_frozen/recompute_engine.py  — 扫上面所有 jsonl，重算 → 写 audit_frozen/_manifest_rows.json（开发层 pp/rarearena/rarebench + pmc_oa）
   - R@1 口径：hits / n_attempted（失败/超时/空也算分母）。variant-aware 用 crossmap。
3. audit_frozen/mimic_note_experiment/agent_matrix_scores.json  — MIMIC-N（416 例 de-leaked）单独口径，denominator=416，取 hits_r1/416。不在 recompute_engine 里。
4. audit_frozen/build_deliverables.py  — 读 _manifest_rows.json → 写 frozen_main_manifest.csv 等
5. scripts/paper_main_figures.py  — 读 frozen_main_manifest.csv（+ agent_matrix_scores.json）→ 画图到 data/round2/figures/

标准更新流程（新数据进来后）
1. 把新 predictions jsonl 放进 data/round2/phase4a/（或合并去重后覆盖）
2. /tmp/paper_venv/bin/python audit_frozen/recompute_engine.py     # 重算 manifest（先备份 _manifest_rows.json）
3. /tmp/paper_venv/bin/python audit_frozen/build_deliverables.py   # 更新 csv
4. /tmp/paper_venv/bin/python scripts/paper_main_figures.py        # 重画图（输出到 data/round2/figures/）
5. 比对新图与 collab/Figures/ 里旧图（用文件大小/mtime），有变化的拷过去
6. 按下面清单更新 MainResults.tex 的数字与描述

新数字要改的地方（清单，逐项核对）
A. Table 1（tbl:main，MainResults.tex 约 L27-57）
   - 每个 cell 的 R@1_variant_aware，三位小数
   - heat 色块：<.10 heatE / .10-.20 heatA / .20-.30 heatB / .30-.40 heatC / >=.40 heatD
   - 每个 backbone 块内、每个开发层列的最大值加粗（\textbf）
   - Avg. 列 = 4 个开发层（pp/rarearena/rarebench/MIMIC-N）原始未舍入值求平均后再舍入到三位（不要用已舍入值求平均）
   - PMC-OA 现为 24/24 全填，不再有 n/r
B. 表下注释段（约 L62）：DeepRare 领先范围、MAI-DxO 表现、PMC 覆盖、MIMIC-N 说明
C. Backbone sensitivity 表（tbl:bbsens，约 L174-178）+ 其后正文段（约 L183）：PP-Store 每 agent 的 best/worst backbone 与 range
D. Cost 段（约 L189）：总预测数、总成本、每预测成本、per-backbone 单价、倍数、budget 用量%。同时改 F4（约 L207）里的 GPT-5 倍数
   - 口径：总数=sum(n_attempted)；成本=sum(total_cost_usd)；per-backbone 按 backbone 汇总
E. Findings F1-F5（约 L197-210）：F1 经典 vs 最佳 scaffold 差、RareBench 领先范围；F2 scaffold vs control 的 pp 差（PP 用 Gemini，MIMIC 用 4-backbone 均值）；F3 V4-Flash vs Gemini 每 agent 差；F4 GPT-5 相关 cell 与倍数
F. Prevalence 段（约 L213）：figM3 的 tier 值（见下方"无法本地重算"）

同步 Supplementary（仅 cost 段，需口径一致）
- Supplementary.tex 的 Cost Accounting（app:cost，约 L367-394）：scored 数、attempted 数、总成本、GPT-5 占比%、per-backbone cost 表。必须与正文 cost 段一致。
- Appendix 字母引用对照（MainResults 引用 supp 时）：A 数据 / B backbone / C fairness+adapter / D repro / E holdout / F hypotheses / G cost / H MIMIC note / I bootstrap

图分三类
- 自动读 manifest（figM1 llm-vs-classical、figM2 cost-accuracy、figF2 scaffolding）：重画即自动更新
- 硬编码独立分析（figM5 selfpref = 10-case P5 pilot，与主表无关，一般不动）
- 依赖 MIMIC cohort 无法本地重算（figM3 prevalence、figM6 hypotheses）：见下

无法本地重算的部分（缺文件）
- scripts/ablation_H1_prevalence.py 需要 data/mimic_iv_rd_slice/cases_filtered_diverse.jsonl —— 此文件名当前不存在。
  该目录下现有：cases_all_relations.jsonl、note_deleaked_v1.jsonl、note_leaked_v1_416.jsonl、note_eval_*.jsonl 等（hmmm 7-24~26 重建）。
  figM3（prevalence tier: llm=[.37,.26,.39,.22] cls=[.30,.23,.33,.50]）与 figM6（H 检验 z/rho）的 frozen 源值来自更早有完整 cohort 时的 pooled 分析。
  小样本 cell 增补对这些大样本 pooled 值影响 <0.5%，通常无需改；但若要严格重算，需要原始 cohort 文件。

去重规则（多来源同 cell 合并时）
- 按 case_id 去重；同一 case_id 多来源结果不同时的取舍规则见每次决策记录。
- MAI-DxO 重跑存在随机性：同 case 两次可能不同 top1（status 基本一致）。
