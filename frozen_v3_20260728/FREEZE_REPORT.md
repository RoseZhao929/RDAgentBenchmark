RareAgentBench frozen_v3_20260728 — 当前现状定版

口径: 与 frozen_v2 一致 (R@1=hits/attempted, variant-aware, MIMIC-N 分母416)。
本版 = phase4a 当前合并态(含同事 V4-Pro 补跑合并 + Gemini maidxo 退回低-pe 100例版)。

一、可用 ready cell: 97 个,已 >=10% 且 valid,可直接进表

二、待重跑/待补 (5 个) — 暂不作为最终结果:
  phenopacket_store  maidxo    20251217 unique=100 valid_pct=81.0  -> rerun_needed: gemini bad-batch, at 100/200
  rarearena_rds      deeprare  k-v4-pro unique=127 valid_pct=92.1  -> pending_fill_73 (coworker running)
  rarearena_rds      maidxo    k-v4-pro unique=200 valid_pct=88.0  -> rerun_needed: v4pro timeout cases
  rarearena_rds      maidxo    20251217 unique=100 valid_pct=88.0  -> rerun_needed: gemini bad-batch, at 100/200
  rarebench          maidxo    k-v4-pro unique=143 valid_pct=48.3  -> rerun_needed: 71 timeout (600s wall)

三、承认为模型特性 (2 个) — 不重跑, caption 说明:
  rarearena_rds      medagents v4-flash valid_pct=64.6 (V4-Flash long-input empty-content)
  rarebench          medagents v4-flash valid_pct=69.8 (V4-Flash long-input empty-content)

改 MainResults.tex: ready cell 用本版数字; 待重跑/待补 cell 的数字标临时,等重跑定版后更新。