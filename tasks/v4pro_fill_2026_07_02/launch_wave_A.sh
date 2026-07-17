#!/bin/bash
# Wave A — V4-Pro fill on small datasets (pp_store + rarearena_rds, cap 500)
# 8 cells: agentclinic, mdagents, medagents, llm_control × 2 datasets
# RESUME will skip already-done case_ids automatically
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

# Wave A: pp_store + rarearena_rds, n=500 (RESUME picks up new cases)
for AG in llm_control agentclinic mdagents medagents; do
  run_cell phenopacket_store "$AG" 500
  run_cell rarearena_rds     "$AG" 500
done

echo "[$(date +%H:%M:%S)] Wave A complete" | tee -a "$LOG_DIR/_master.log"
