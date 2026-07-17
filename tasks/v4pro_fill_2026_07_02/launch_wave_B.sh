#!/bin/bash
# Wave B — V4-Pro fill on large datasets (mimic_diverse + rarebench)
# 8 cells total, but mimic_diverse llm_control already at 951 (skip)
set -u
cd /Users/yutianzhao/Desktop/RDAgentBenchmark

BACKBONE=openrouter/deepseek/deepseek-v4-pro
LOG_DIR=tasks/v4pro_fill_2026_07_02/logs
mkdir -p "$LOG_DIR"

run_cell() {
  local ds=$1 ag=$2 n=$3
  local out="data/round2/phase4a/predictions_${ds}_${ag}_deepseek_deepseek-v4-pro.jsonl"
  local log="$LOG_DIR/${ds}_${ag}.log"
  echo "[$(date +%H:%M:%S)] launching ${ds}/${ag} n=${n}" | tee -a "$LOG_DIR/_master.log"
  python3 scripts/phase4a_runner.py \
    --dataset "$ds" --agent "$ag" --backbone "$BACKBONE" \
    --n "$n" --out "$out" >> "$log" 2>&1
  echo "[$(date +%H:%M:%S)] done ${ds}/${ag} exit=$?" | tee -a "$LOG_DIR/_master.log"
}

# mimic_diverse (all cases available ~956), llm_control already at 951 skip
for AG in agentclinic mdagents medagents; do
  run_cell mimic_diverse "$AG" 1000
done

# rarebench (1122 cases, 4 splits × ~281)
for AG in llm_control agentclinic mdagents medagents; do
  run_cell rarebench "$AG" 1200
done

echo "[$(date +%H:%M:%S)] Wave B complete" | tee -a "$LOG_DIR/_master.log"
