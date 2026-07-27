#!/usr/bin/env bash
# =============================================================================
# maidxo 4-backbone 重跑 —— 正则修复后（交给 co-author 在本机跑）
# =============================================================================
# 背景：旧 maidxo 结果全废。main.py:1486 的贪婪正则把 MIMIC 出院小结里的生命
#       体征行 "...87/35, 97% on RA" 当成诊断@0.97，触发 >0.90 自动收工短路，
#       面板第一轮就拿血氧饱和度当最终诊断。已在 mai_dx/main.py 加 vitals 过滤
#       （looks_like_vitals），冒烟确认辩论恢复正常（iters=3，不再吐垃圾）。
#       本脚本用修好的代码重跑 maidxo × 4 backbone × 416。
#
# ⚠️ DUA：MIMIC 数据受 PhysioNet 协议，只能在这台已授权机器（/home/research，
#    research 组）上跑。不要把 data/ 或 API key 拷去别的机器/笔记本。
#
# 用法（co-author 在本机、本仓库目录下）：
#     bash scripts/rerun_maidxo_after_regexfix.sh
#
# 跑完后不用你打分——告诉主作者 4 个 log 都出现 "[p4a] DONE" 即可，
# 打分并入 24-cell 主矩阵由主作者统一做（口径一致）。
# =============================================================================
set -uo pipefail
ROOT="/home/research/RDAgentBenchmark"
cd "$ROOT" || { echo "!! 必须在 $ROOT 下跑（DUA 授权机器）"; exit 1; }

# ---- gateway ----
# 不用 export 任何 key！gateway（litellm 代理）配置全在仓库根的 .env 里，
# runner 的 load_env() 会自动加载（phase4a_runner.py:33，setdefault 不覆盖）。
# 这与正在跑的 deeprare 重跑脚本口径一致。co-author 什么 key 都不用碰、不用知道。

# ---- 前置检查 ----
grep -q "looks_like_vitals" agents/maidxo/mai_dx/main.py \
  || { echo "!! 正则修复不在位（main.py 无 looks_like_vitals）——中止"; exit 1; }
[ -x agents/maidxo/.venv/bin/python ] || [ -L agents/maidxo/.venv/bin/python ] \
  || { echo "!! maidxo venv 缺失"; exit 1; }
[ -f data/mimic_iv_rd_slice/note_eval_hpo_line_v1.jsonl ] \
  || { echo "!! gold/输入 416 缺失"; exit 1; }
[ -f .env ] && grep -q "^LLM_GATEWAY_URL=" .env \
  || { echo "!! .env 缺 LLM_GATEWAY_URL —— gateway 无法配置"; exit 1; }

mkdir -p logs/mimic_note data/round2/phase4a_mimic_note

# ---- 把修复前的旧 maidxo 文件挪走（否则 --resume 会复用旧垃圾行）----
# ⚠️ 只在【首次】跑时执行：把 7/25 的 bug 版结果挪到备份目录。
#    重跑时（备份目录已存在）绝不能再挪——那会把本次已跑出的好结果误删、
#    导致 RESUME 从 0 重跑，之前几百个 ok 全白跑。所以用"备份目录是否已存在"
#    作为"是不是首次跑"的判据：已存在 = 已经挪过 = 现在原目录里是新结果，跳过。
BK="data/round2/_maidxo_prefix_backup_prefix"
if [ -d "$BK" ]; then
  echo "[backup] 备份目录已存在 —— 判定为【重跑】，跳过挪文件（保护本次已跑结果，RESUME 续跑）。"
else
  mkdir -p "$BK"
  moved=0
  for f in data/round2/phase4a_mimic_note/predictions_mimic_note_maidxo_*.jsonl; do
    [ -e "$f" ] || continue
    mv "$f" "$BK/" && { echo "[backup] 首次跑：旧 bug 版挪到 $BK/$(basename "$f")"; moved=1; }
  done
  [ "$moved" = 0 ] && echo "[backup] 首次跑：原目录无旧 maidxo 文件，无需挪。"
fi

# ---- 4 backbone 并行重跑 ----
declare -A SFX=(
  ["deepseek/deepseek-v4-pro"]="deepseek__deepseek-v4-pro"
  ["deepseek/deepseek-v4-flash"]="deepseek_deepseek-v4-flash"
  ["openai/gpt-5"]="openai_gpt-5"
  ["google/gemini-3-flash-preview"]="google_gemini-3-flash-preview-20251217"
)
CONC=8          # 2026-07-26 提速：deeprare/mdagents 已全部跑完，机器空出来了
                # （16 核 load~2、内存 47G 空闲）。实测单个 maidxo 子进程仅 ~200MB，
                # 4×8=32 子进程 ≈ 6.4GB，内存毫无压力；maidxo 是 gateway-I/O 绑，
                # 提并发靠更多 in-flight 请求填满吞吐。8 是甜点：再高可能触发 gateway
                # 429 限流（反而计 miss）。RESUME 保留已 ok 的 ~346 个，只补剩下的。
TIMEOUT=900     # 出院小结长，给足单例墙钟

# 内存护栏：起跑前若可用内存 < 8G，提示先等 deeprare 跑完
avail_g=$(free -g | awk '/^Mem:/{print $7}')
if [ "${avail_g:-99}" -lt 8 ]; then
  echo "!! 可用内存仅 ${avail_g}G（<8G）。建议等 deeprare 跑完再起 maidxo，"
  echo "   或把上面 CONC 调到 2。现在继续跑有 OOM 风险。5 秒后继续（Ctrl-C 中止）..."
  sleep 5
fi

pids=()
for bb in "deepseek/deepseek-v4-pro" "deepseek/deepseek-v4-flash" "openai/gpt-5" "google/gemini-3-flash-preview"; do
  sfx="${SFX[$bb]}"
  out="data/round2/phase4a_mimic_note/predictions_mimic_note_maidxo_${sfx}.jsonl"
  log="logs/mimic_note/maidxo_rerun_${sfx}.log"
  python3 scripts/phase4a_runner.py \
    --dataset mimic_note --agent maidxo --backbone "$bb" \
    --n 416 --out "$out" --concurrency "$CONC" --timeout_s "$TIMEOUT" \
    > "$log" 2>&1 &
  pids+=($!)
  echo "[maidxo-rerun] launched $bb pid=$! -> $out  (tail -f $log)"
done

echo "[maidxo-rerun] 4 backbone 并行跑起来了。预计几小时。"
echo "[maidxo-rerun] 看进度： tail -f logs/mimic_note/maidxo_rerun_*.log"
for p in "${pids[@]}"; do wait "$p"; done
echo "[maidxo-rerun] ALL DONE —— 4 个 log 应各有 [p4a] DONE。通知主作者打分。"
