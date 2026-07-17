#!/bin/bash
# Wave C — GPT-5 fill on small datasets (pp_store + rarearena_rds, cap 500)
# 4 light agents × 2 datasets = 8 cells
set -u
cd /Users/yutianzhao/Desktop/RDAgentBenchmark

BACKBONE=openrouter/openai/gpt-5
LOG_DIR=tasks/gpt5_fill_2026_07_02/logs
mkdir -p "$LOG_DIR"

run_cell() {
  local ds=$1 ag=$2 n=$3
  local out="data/round2/phase4a/predictions_${ds}_${ag}_openai_gpt-5.jsonl"
  local log="$LOG_DIR/${ds}_${ag}.log"
  echo "[$(date +%H:%M:%S)] launching ${ds}/${ag} n=${n}" | tee -a "$LOG_DIR/_master.log"
  python3 scripts/phase4a_runner.py \
    --dataset "$ds" --agent "$ag" --backbone "$BACKBONE" \
    --n "$n" --out "$out" >> "$log" 2>&1
  echo "[$(date +%H:%M:%S)] done ${ds}/${ag} exit=$?" | tee -a "$LOG_DIR/_master.log"
}

for AG in llm_control agentclinic mdagents medagents; do
  run_cell phenopacket_store "$AG" 500
  run_cell rarearena_rds     "$AG" 500
done

echo "[$(date +%H:%M:%S)] Wave C complete" | tee -a "$LOG_DIR/_master.log"
