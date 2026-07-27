#!/usr/bin/env bash
# MIMIC-note 416 HPO-line — parameterized runner for splitting the 4-backbone
# matrix across machines/people. Each operator runs this with the backbone(s)
# they own; predictions are named per-backbone so there is NO merge conflict.
#
# USAGE:
#   bash scripts/run_mimic_note_matrix.sh <backbone> [<backbone> ...]
# EXAMPLES:
#   # Machine A (owns deepseek family):
#   bash scripts/run_mimic_note_matrix.sh deepseek/deepseek-v4-pro deepseek/deepseek-v4-flash
#   # Machine B (owns closed models):
#   bash scripts/run_mimic_note_matrix.sh openai/gpt-5 google/gemini-3-flash-preview
#
# SAFETY (learned the hard way): pass AT MOST 2 backbones per machine. Each
# backbone spins up ~5 API-agent runners x 8-12 concurrency; 2 backbones ~= 10
# runners, which is safe on a 16-core/62GB box. 4 at once spiked to load~35 /
# 0 free RAM. deeprare (~2GB/proc) is serialized across the given backbones and
# run LAST, so it never overlaps another deeprare instance.
#
# DUA NOTE: the 416 line contains de-identified MIMIC-IV discharge-summary text
# (PhysioNet DUA). Only run on a machine that is already a credentialed copy of
# this repo (data + venvs + .env in place). Do NOT copy the data/key elsewhere.
#
# Resumable: phase4a_runner skips done case_ids per --out file. Re-run anytime.
# Failures/timeouts/parser_errors are KEPT in the R@1 denominator (count as misses).
# maidxo x openai/gpt-5 auto-skips inside the runner (documented INCOMPAT).
set -uo pipefail

ROOT="/home/research/RDAgentBenchmark"
cd "$ROOT"
N=416
OUTDIR="data/round2/phase4a_mimic_note"
LOGDIR="logs/mimic_note"
mkdir -p "$OUTDIR" "$LOGDIR"

if [ "$#" -lt 1 ]; then
  echo "usage: $0 <backbone> [<backbone> ...]" >&2
  echo "backbones: deepseek/deepseek-v4-pro deepseek/deepseek-v4-flash openai/gpt-5 google/gemini-3-flash-preview" >&2
  exit 2
fi
if [ "$#" -gt 2 ]; then
  echo "REFUSING: >2 backbones per machine risks OOM. Split across machines." >&2
  exit 2
fi

declare -A SUFFIX=(
  ["deepseek/deepseek-v4-pro"]="deepseek__deepseek-v4-pro"
  ["deepseek/deepseek-v4-flash"]="deepseek_deepseek-v4-flash"
  ["openai/gpt-5"]="openai_gpt-5"
  ["google/gemini-3-flash-preview"]="google_gemini-3-flash-preview-20251217"
)

BACKBONES=("$@")
for BB in "${BACKBONES[@]}"; do
  if [ -z "${SUFFIX[$BB]:-}" ]; then
    echo "unknown backbone: $BB" >&2; exit 2
  fi
done

run_agent () {  # agent backbone conc timeout
  local agent="$1" backbone="$2" conc="$3" tmo="$4"
  local suf="${SUFFIX[$backbone]}"
  local out="$OUTDIR/predictions_mimic_note_${agent}_${suf}.jsonl"
  local logf="$LOGDIR/${agent}_${suf}.log"
  echo "[launch $(date +%H:%M:%S)] $agent @ $backbone conc=$conc -> $out"
  python3 scripts/phase4a_runner.py \
    --dataset mimic_note --agent "$agent" --backbone "$backbone" \
    --n "$N" --out "$out" --concurrency "$conc" --timeout_s "$tmo" \
    > "$logf" 2>&1
  echo "[done $(date +%H:%M:%S)] $agent @ $backbone rc=$?"
}

# ---- Phase 1: API-bound agents. All given backbones' API agents run together
# (<=2 backbones => <=10 runners, safe). ----
echo "===== PHASE 1 (API agents) backbones=[${BACKBONES[*]}] @ $(date +%H:%M:%S) ====="
for BB in "${BACKBONES[@]}"; do
  run_agent llm_control "$BB" 10 180 &
  run_agent medagents   "$BB" 8  360 &
  run_agent mdagents    "$BB" 8  360 &
  run_agent agentclinic "$BB" 8  480 &
  run_agent maidxo      "$BB" 12 900 &
done
wait
echo "===== PHASE 1 DONE @ $(date +%H:%M:%S) ====="

# ---- Phase 2: deeprare (RAM-heavy ~2GB/proc), serialized across the backbones. ----
for BB in "${BACKBONES[@]}"; do
  echo "===== DEEPRARE @ $BB $(date +%H:%M:%S) ====="
  run_agent deeprare "$BB" 6 600
done

echo "=== MATRIX SLICE DONE [${BACKBONES[*]}] $(date +%H:%M:%S) ==="
