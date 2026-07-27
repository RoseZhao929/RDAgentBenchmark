#!/usr/bin/env bash
# ACCELERATED deeprare end_to_end 补跑: all 4 backbones IN PARALLEL, high
# per-backbone concurrency. Supersedes the serial rerun_deeprare_e2e.sh.
#
# WHY it's safe to parallelize (measured 2026-07-26):
#   - deeprare is gateway-I/O-bound, NOT CPU/RAM-bound: per-proc RSS ~0.5GB,
#     machine load ~3 on 16 cores, per-case median 279s is almost all spent
#     awaiting LLM calls. The old "serial to avoid OOM" assumption was wrong.
#   - 4 backbones × concurrency 10 = up to 40 in-flight gateway calls. RAM
#     headroom: 62GB total, ~25GB used → fine. CPU stays idle-bound.
# Serial estimate was ~20h (4 × 5h). Parallel target: ~5-6h (max of the 4).
#
# Resume: keeps already-ok case_ids (v4-pro already has ~52).
set -uo pipefail
ROOT="/home/research/RDAgentBenchmark"; cd "$ROOT"
mkdir -p logs/mimic_note data/round2/phase4a_mimic_note

declare -A SFX=(
  ["deepseek/deepseek-v4-pro"]="deepseek__deepseek-v4-pro"
  ["deepseek/deepseek-v4-flash"]="deepseek_deepseek-v4-flash"
  ["openai/gpt-5"]="openai_gpt-5"
  ["google/gemini-3-flash-preview"]="google_gemini-3-flash-preview-20251217"
)
CONC=6

pids=()
for bb in "deepseek/deepseek-v4-pro" "deepseek/deepseek-v4-flash" "openai/gpt-5" "google/gemini-3-flash-preview"; do
  sfx="${SFX[$bb]}"
  out="data/round2/phase4a_mimic_note/predictions_mimic_note_deeprare_${sfx}.jsonl"
  log="logs/mimic_note/deeprare_e2e_${sfx}.log"
  python3 scripts/phase4a_runner.py \
    --dataset mimic_note --agent deeprare --backbone "$bb" \
    --n 416 --out "$out" --concurrency "$CONC" --timeout_s 900 \
    > "$log" 2>&1 &
  pids+=($!)
  echo "[deeprare-par] launched $bb pid=$! conc=$CONC -> $out"
done
echo "[deeprare-par] waiting for ${#pids[@]} backbones @ $(date +%H:%M:%S)..."
for p in "${pids[@]}"; do wait "$p"; done
echo "[deeprare-par] ALL DONE @ $(date +%H:%M:%S)"
