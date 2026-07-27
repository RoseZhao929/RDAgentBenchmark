#!/usr/bin/env bash
# MIMIC-note 416 line — FULL 4-backbone matrix on THIS machine, auto-relay.
#
# Runs the whole matrix without OOM by never letting more than 2 backbones'
# API-agents run at once, and serializing the RAM-heavy deeprare across all 4.
#
# Relay plan:
#   Wave 1 (already launched externally): v4-pro + v4-flash API agents.
#           This script WAITS for their API-agent files to reach 416 (or their
#           runners to exit), then:
#   Wave 2: gpt-5 + gemini API agents (5 agents x 2 bb; maidxo x gpt-5 auto-skips).
#   Wave 3: deeprare across all 4 backbones, strictly serialized (~2GB/proc).
#
# Resumable everywhere (phase4a_runner skips done case_ids). Safe to re-run.
# Failures/timeouts/parser_errors are KEPT in the R@1 denominator.
set -uo pipefail

ROOT="/home/research/RDAgentBenchmark"
cd "$ROOT"
N=416
OUTDIR="data/round2/phase4a_mimic_note"
LOGDIR="logs/mimic_note"
mkdir -p "$OUTDIR" "$LOGDIR"

declare -A SUFFIX=(
  ["deepseek/deepseek-v4-pro"]="deepseek__deepseek-v4-pro"
  ["deepseek/deepseek-v4-flash"]="deepseek_deepseek-v4-flash"
  ["openai/gpt-5"]="openai_gpt-5"
  ["google/gemini-3-flash-preview"]="google_gemini-3-flash-preview-20251217"
)
API_AGENTS=(llm_control medagents mdagents agentclinic maidxo)

lines () { wc -l < "$1" 2>/dev/null || echo 0; }

run_agent () {  # agent backbone conc timeout
  local agent="$1" backbone="$2" conc="$3" tmo="$4"
  local suf="${SUFFIX[$backbone]}"
  local out="$OUTDIR/predictions_mimic_note_${agent}_${suf}.jsonl"
  local logf="$LOGDIR/${agent}_${suf}.log"
  echo "[launch $(date +%H:%M:%S)] $agent @ $backbone conc=$conc -> $(basename "$out")"
  python3 scripts/phase4a_runner.py \
    --dataset mimic_note --agent "$agent" --backbone "$backbone" \
    --n "$N" --out "$out" --concurrency "$conc" --timeout_s "$tmo" \
    > "$logf" 2>&1
  echo "[done $(date +%H:%M:%S)] $agent @ $backbone rc=$?"
}

# maidxo x gpt-5 is a documented INCOMPAT (runner auto-skips). Treat its target
# file as "complete" so the wait loop below doesn't hang forever on it.
is_api_done () {  # backbone -> 0 if all its API agents are done
  local bb="$1"
  local suf="${SUFFIX[$bb]}"
  for a in "${API_AGENTS[@]}"; do
    if [ "$a" = "maidxo" ] && [ "$bb" = "openai/gpt-5" ]; then continue; fi
    local out="$OUTDIR/predictions_mimic_note_${a}_${suf}.jsonl"
    # done if file has >=N lines AND no live runner for this (agent,backbone)
    local n; n=$(lines "$out")
    local alive; alive=$(pgrep -fc "agent $a --backbone $bb" 2>/dev/null); alive=${alive:-0}
    # take only the first token in case pgrep emitted anything unexpected
    alive=${alive%%$'\n'*}
    if [ "$n" -lt "$N" ] || [ "$alive" -gt 0 ]; then return 1; fi
  done
  return 0
}

api_batch () {  # launch API agents for the given backbones concurrently, wait
  local -a bbs=("$@")
  echo "===== API BATCH backbones=[${bbs[*]}] @ $(date +%H:%M:%S) ====="
  for bb in "${bbs[@]}"; do
    run_agent llm_control "$bb" 10 180 &
    run_agent medagents   "$bb" 8  360 &
    run_agent mdagents    "$bb" 8  360 &
    run_agent agentclinic "$bb" 8  480 &
    run_agent maidxo      "$bb" 12 900 &
  done
  wait
  echo "===== API BATCH DONE [${bbs[*]}] @ $(date +%H:%M:%S) ====="
}

# ---- Wave 1: WAIT for the externally-launched v4-pro + v4-flash API agents ----
echo "[relay] waiting for wave-1 (v4-pro + v4-flash) API agents to finish..."
while true; do
  if is_api_done "deepseek/deepseek-v4-pro" && is_api_done "deepseek/deepseek-v4-flash"; then
    echo "[relay] wave-1 API agents complete @ $(date +%H:%M:%S)"
    break
  fi
  sleep 120
done

# ---- Wave 2: gpt-5 + gemini API agents ----
api_batch "openai/gpt-5" "google/gemini-3-flash-preview"

# ---- Wave 3: deeprare for gpt-5 + gemini, serialized ----
# (v4-pro deeprare is owned by run_mimic_note_agents.sh; v4-flash deeprare by
# run_mimic_note_matrix.sh — this script only fills the two closed-model bb.)
for bb in "openai/gpt-5" "google/gemini-3-flash-preview"; do
  echo "===== DEEPRARE @ $bb $(date +%H:%M:%S) ====="
  run_agent deeprare "$bb" 6 600
done

echo "=== FULL LOCAL MATRIX DONE @ $(date +%H:%M:%S) ==="
