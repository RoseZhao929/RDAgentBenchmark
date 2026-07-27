#!/usr/bin/env bash
# BEFORE-de-leak baseline: bare LLM (llm_control) × 4 paper backbones on the
# LEAKED 416 (full note, no truncation/mask). Pairs 1:1 with the de-leaked 416
# so Table 1 becomes a true same-case before/after across all 4 backbones.
#
# llm_control is in-process + fast (median 3-18s/case), so all 4 run
# concurrently WITHOUT contending with the deeprare subprocess job (deeprare is
# CPU/RAM heavy; llm_control is I/O-bound on the gateway). ~10-20 min total.
set -uo pipefail
ROOT="/home/research/RDAgentBenchmark"; cd "$ROOT"
mkdir -p logs/mimic_note_leaked data/round2/phase4a_mimic_note_leaked

declare -A SFX=(
  ["deepseek/deepseek-v4-pro"]="deepseek__deepseek-v4-pro"
  ["deepseek/deepseek-v4-flash"]="deepseek_deepseek-v4-flash"
  ["openai/gpt-5"]="openai_gpt-5"
  ["google/gemini-3-flash-preview"]="google_gemini-3-flash-preview-20251217"
)

pids=()
for bb in "deepseek/deepseek-v4-pro" "deepseek/deepseek-v4-flash" "openai/gpt-5" "google/gemini-3-flash-preview"; do
  sfx="${SFX[$bb]}"
  out="data/round2/phase4a_mimic_note_leaked/predictions_mimic_note_leaked_llm_control_${sfx}.jsonl"
  log="logs/mimic_note_leaked/llm_control_${sfx}.log"
  python3 scripts/phase4a_runner.py \
    --dataset mimic_note_leaked --agent llm_control --backbone "$bb" \
    --n 416 --out "$out" --concurrency 8 --timeout_s 300 \
    > "$log" 2>&1 &
  pids+=($!)
  echo "[before] launched $bb pid=$! -> $out"
done
echo "[before] waiting for ${#pids[@]} backbones..."
for p in "${pids[@]}"; do wait "$p"; done
echo "[before] ALL DONE @ $(date +%H:%M:%S)"
