#!/bin/bash
# Usage: run_agent.sh <agent>
# Runs one agent × 4 datasets on V4-Pro reasoning-OFF, full-N. (bash 3.2 safe)
set -u
cd /Users/yutianzhao/Desktop/RDAgentBenchmark
AG="$1"
BB=openrouter/deepseek/deepseek-v4-pro
LOG=tasks/v4pro_reasoning_off_2026_07_03/logs
PRED=data/round2/phase4a
CAP=1200
for DS in phenopacket_store rarearena_rds mimic_diverse rarebench; do
  case "$DS" in
    phenopacket_store) N=500 ;;
    rarearena_rds)     N=500 ;;
    mimic_diverse)     N=1000 ;;
    rarebench)         N=2500 ;;  # =>full 1122 (88+370+40+624), matches gemini
  esac
  OUT="$PRED/predictions_${DS}_${AG}_deepseek_deepseek-v4-pro.jsonl"
  echo "[$(date +%H:%M:%S)] START ${AG}/${DS} n=$N" | tee -a "$LOG/_master.log"
  python3 scripts/phase4a_runner.py --dataset "$DS" --agent "$AG" \
    --backbone "$BB" --n "$N" --timeout_s "$CAP" \
    --out "$OUT" >> "$LOG/${AG}_${DS}.log" 2>&1
  echo "[$(date +%H:%M:%S)] DONE ${AG}/${DS} exit=$?" | tee -a "$LOG/_master.log"
done
echo "[$(date +%H:%M:%S)] AGENT ${AG} COMPLETE" | tee -a "$LOG/_master.log"
