#!/usr/bin/env bash
# Full 6-agent x 416 HPO-line x DeepSeek-V4-Pro run on the de-leaked MIMIC-note probe.
#
# - Resumable: phase4a_runner skips already-done case_ids in each --out file.
# - Failures/timeouts/parser_errors are KEPT in the R@1 denominator (count as misses).
# - Concurrency tuned per agent weight (maidxo/deeprare are the heavy tails).
# - Each agent logged to logs/mimic_note/<agent>.log; predictions to
#   data/round2/phase4a_mimic_note/predictions_mimic_note_<agent>_deepseek__deepseek-v4-pro.jsonl
#
# Resource classes:
#   API/IO-bound (low RAM): llm_control, medagents, mdagents, agentclinic, maidxo
#   RAM/CPU-bound (torch + 326MB embed CSV per subprocess): deeprare
# All agents launched concurrently; wall-clock ~= maidxo (the 403s/case long pole).
#
# vc_rdagent + lirical are HPO_ONLY agents; mimic_note is a NO_HPO dataset, so
# they auto-skip and are intentionally NOT launched here (declared skipped in docs).
set -uo pipefail

ROOT="/home/research/RDAgentBenchmark"
cd "$ROOT"

BACKBONE="deepseek/deepseek-v4-pro"
N=416
OUTDIR="data/round2/phase4a_mimic_note"
LOGDIR="logs/mimic_note"
mkdir -p "$OUTDIR" "$LOGDIR"

run_agent () {
  local agent="$1" conc="$2" tmo="$3"
  local out="$OUTDIR/predictions_mimic_note_${agent}_deepseek__deepseek-v4-pro.jsonl"
  echo "[launch $(date +%H:%M:%S)] $agent conc=$conc timeout=${tmo}s -> $out"
  python3 scripts/phase4a_runner.py \
    --dataset mimic_note --agent "$agent" --backbone "$BACKBONE" \
    --n "$N" --out "$out" --concurrency "$conc" --timeout_s "$tmo" \
    > "$LOGDIR/${agent}.log" 2>&1
  echo "[done $(date +%H:%M:%S)] $agent rc=$? -> $LOGDIR/${agent}.log"
}

run_agent llm_control 10 180 &
run_agent medagents   8  360 &
run_agent mdagents    8  360 &
run_agent agentclinic 8  480 &
run_agent deeprare    6  600 &
run_agent maidxo      12 900 &
wait
echo "=== ALL AGENTS DONE $(date +%H:%M:%S) ==="
