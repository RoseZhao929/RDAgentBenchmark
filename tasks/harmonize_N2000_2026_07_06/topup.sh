#!/bin/bash
set -u
cd /Users/yutianzhao/Desktop/RDAgentBenchmark
LOG=tasks/harmonize_N2000_2026_07_06/logs
BB=openrouter/deepseek/deepseek-v4-flash; TAG=deepseek_deepseek-v4-flash
topup() {
  local ds=$1 ag=$2 cap=$3
  local out="data/round2/phase4a/predictions_${ds}_${ag}_${TAG}.jsonl"
  echo "[$(date +%H:%M:%S)] TOPUP ${ds}/${ag}" | tee -a "$LOG/_topup.log"
  python3 scripts/phase4a_runner.py --dataset "$ds" --agent "$ag" --backbone "$BB" \
    --n 2000 --timeout_s "$cap" --concurrency 3 --out "$out" >> "$LOG/topup_${ds}_${ag}.log" 2>&1
  echo "[$(date +%H:%M:%S)] TOPUP DONE ${ds}/${ag}" | tee -a "$LOG/_topup.log"
}
topup rarearena_rds medagents 900
topup phenopacket_store medagents 900
topup rarearena_rds agentclinic 1200
topup phenopacket_store agentclinic 1200
echo "[$(date +%H:%M:%S)] TOPUP ALL DONE" | tee -a "$LOG/_topup.log"
