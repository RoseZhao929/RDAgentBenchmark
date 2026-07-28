10% 覆盖率补跑 — 雨恬(yutian)分工

目标：DeepRare / MAI-DxO 在开发层每 cell 采样率达 10%（PP/RareArena 帧 2000 → 目标 200；RareBench 帧 1122 → 目标 113）。runner 用 --n 指定目标总数，会自动跳过已完成(ok)的 case，只补缺口，不会重复跑已有的。

审计核对结论
- 同事的统计与我们冻结审计(frozen_v2_20260728)基本一致：20 个 cell 中 17 个完全对上。
- 3 个小出入（同事偏保守，少算几条，不影响分工）：
  - mx_rb_pro 同事 129 / 我们 139 → 都已达标(>=113)，不用跑，一致
  - mx_ra_pro 同事 53 / 我们 59 → 归 V4-Pro 组(同事跑)
  - dr_rb_pro 同事 78 / 我们 82 → 归 V4-Pro 组(同事跑)
- 3 个已达标不用跑：mx_rb_pro(139)、mx_rb_flash(150)、mx_rb_gpt5(150)。确认。

我(雨恬)的 9 个 cell，合计补 685 例，约 2.0h
（现有 unique 用我们审计值；backbone id 用 gateway 全名）

| cell | agent | dataset(key) | backbone(id) | 现有 | 目标 | 补 | 并发 |
|---|---|---|---|---|---|---|---|
| mx_pp_flash | maidxo | phenopacket_store | deepseek_deepseek-v4-flash | 78 | 200 | 122 | 10 |
| dr_pp_gpt5 | deeprare | phenopacket_store | openai_gpt-5 | 100 | 200 | 100 | 5 |
| mx_pp_gem | maidxo | phenopacket_store | google_gemini-3-flash-preview-20251217 | 100 | 200 | 100 | 10 |
| mx_ra_gem | maidxo | rarearena_rds | google_gemini-3-flash-preview-20251217 | 100 | 200 | 100 | 10 |
| dr_ra_gpt5 | deeprare | rarearena_rds | openai_gpt-5 | 100 | 200 | 100 | 5 |
| mx_ra_flash | maidxo | rarearena_rds | deepseek_deepseek-v4-flash | 150 | 200 | 50 | 10 |
| mx_ra_gpt5 | maidxo | rarearena_rds | openai_gpt-5 | 150 | 200 | 50 | 8 |
| mx_pp_gpt5 | maidxo | phenopacket_store | openai_gpt-5 | 150 | 200 | 50 | 8 |
| dr_rb_gpt5 | deeprare | rarebench | openai_gpt-5 | 100 | 113 | 13 | 5 |

跑法（每个 cell 一条，--out 指向 phase4a 现有文件即续跑）

前置：进仓库根目录；确保 LLM gateway 环境变量已设（.env）。gpt-5 / v4-flash 若走 gateway 别名，导出 LLM_GATEWAY_GPT5_MODEL / 对应变量（参考分支 run_n100.sh）。

模板：
  python3 scripts/phase4a_runner.py \
    --dataset <DS> --agent <AG> --backbone <BB> \
    --n <TARGET> \
    --out data/round2/phase4a/predictions_<DS>_<AG>_<BB>.jsonl \
    --concurrency <PAR> \
    --resume-statuses "ok,skipped,parser_error" \
    --max-attempts-per-case 2 \
    --timeout_s 900

九条命令：
  # mx_pp_flash (+122, 并发10) — 关键路径 ~2.0h，先起
  python3 scripts/phase4a_runner.py --dataset phenopacket_store --agent maidxo --backbone deepseek_deepseek-v4-flash --n 200 --out data/round2/phase4a/predictions_phenopacket_store_maidxo_deepseek_deepseek-v4-flash.jsonl --concurrency 10 --resume-statuses "ok,skipped,parser_error" --max-attempts-per-case 2 --timeout_s 900

  # dr_pp_gpt5 (+100, 并发5)
  python3 scripts/phase4a_runner.py --dataset phenopacket_store --agent deeprare --backbone openai_gpt-5 --n 200 --out data/round2/phase4a/predictions_phenopacket_store_deeprare_openai_gpt-5.jsonl --concurrency 5 --resume-statuses "ok,skipped,parser_error" --max-attempts-per-case 2 --timeout_s 900

  # mx_pp_gem (+100, 并发10)
  python3 scripts/phase4a_runner.py --dataset phenopacket_store --agent maidxo --backbone google_gemini-3-flash-preview-20251217 --n 200 --out data/round2/phase4a/predictions_phenopacket_store_maidxo_google_gemini-3-flash-preview-20251217.jsonl --concurrency 10 --resume-statuses "ok,skipped,parser_error" --max-attempts-per-case 2 --timeout_s 900

  # mx_ra_gem (+100, 并发10)
  python3 scripts/phase4a_runner.py --dataset rarearena_rds --agent maidxo --backbone google_gemini-3-flash-preview-20251217 --n 200 --out data/round2/phase4a/predictions_rarearena_rds_maidxo_google_gemini-3-flash-preview-20251217.jsonl --concurrency 10 --resume-statuses "ok,skipped,parser_error" --max-attempts-per-case 2 --timeout_s 900

  # dr_ra_gpt5 (+100, 并发5)
  python3 scripts/phase4a_runner.py --dataset rarearena_rds --agent deeprare --backbone openai_gpt-5 --n 200 --out data/round2/phase4a/predictions_rarearena_rds_deeprare_openai_gpt-5.jsonl --concurrency 5 --resume-statuses "ok,skipped,parser_error" --max-attempts-per-case 2 --timeout_s 900

  # mx_ra_flash (+50, 并发10)
  python3 scripts/phase4a_runner.py --dataset rarearena_rds --agent maidxo --backbone deepseek_deepseek-v4-flash --n 200 --out data/round2/phase4a/predictions_rarearena_rds_maidxo_deepseek_deepseek-v4-flash.jsonl --concurrency 10 --resume-statuses "ok,skipped,parser_error" --max-attempts-per-case 2 --timeout_s 900

  # mx_ra_gpt5 (+50, 并发8)
  python3 scripts/phase4a_runner.py --dataset rarearena_rds --agent maidxo --backbone openai_gpt-5 --n 200 --out data/round2/phase4a/predictions_rarearena_rds_maidxo_openai_gpt-5.jsonl --concurrency 8 --resume-statuses "ok,skipped,parser_error" --max-attempts-per-case 2 --timeout_s 900

  # mx_pp_gpt5 (+50, 并发8)
  python3 scripts/phase4a_runner.py --dataset phenopacket_store --agent maidxo --backbone openai_gpt-5 --n 200 --out data/round2/phase4a/predictions_phenopacket_store_maidxo_openai_gpt-5.jsonl --concurrency 8 --resume-statuses "ok,skipped,parser_error" --max-attempts-per-case 2 --timeout_s 900

  # dr_rb_gpt5 (+13, 并发5)
  python3 scripts/phase4a_runner.py --dataset rarebench --agent deeprare --backbone openai_gpt-5 --n 113 --out data/round2/phase4a/predictions_rarebench_deeprare_openai_gpt-5.jsonl --concurrency 5 --resume-statuses "ok,skipped,parser_error" --max-attempts-per-case 2 --timeout_s 900

跑完后
1. 去重 + 重算：/tmp/paper_venv/bin/python audit_frozen/recompute_engine.py（引擎按 case_id 去重，不受续跑重复行影响）
2. 更新覆盖：重跑 frozen_v2 定版脚本，确认这些 cell unique 达标(>=200 / >=113)
3. 注意 valid 率：mx_pp_flash 之前 valid 率极低(15/78)，补到 200 unique 后要看 valid 是否也够；V4-Flash 系有 empty-content 问题
4. 更新 Table 1 + 正文（见 paper_aaai27_collab/RESULTS_UPDATE_SOP.md）

同事(V4-Pro 组)负责的 5 cell：dr_ra_pro, dr_pp_pro, mx_ra_pro, mx_pp_pro, dr_rb_pro（合计 ~546 例，关键路径 ~5.2h）。
