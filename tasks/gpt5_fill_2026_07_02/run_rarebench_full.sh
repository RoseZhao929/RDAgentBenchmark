#!/bin/bash
# Extend GPT-5 rarebench from n_per_split=300 (728) to full 1122 for 4 main agents.
# RESUME skips the ~728 already-done, adds the remaining ~394 per cell.
set -u
cd /Users/yutianzhao/Desktop/RDAgentBenchmark
BB=openrouter/openai/gpt-5
LOG=tasks/gpt5_fill_2026_07_02/logs
PRED=data/round2/phase4a
for AG in llm_control agentclinic mdagents medagents; do
  OUT="$PRED/predictions_rarebench_${AG}_openai_gpt-5.jsonl"
  echo "[$(date +%H:%M:%S)] GPT5-rareb-full START ${AG} n=2500" | tee -a "$LOG/_master.log"
  python3 scripts/phase4a_runner.py --dataset rarebench --agent "$AG" \
    --backbone "$BB" --n 2500 --timeout_s 900 \
    --out "$OUT" >> "$LOG/rarebfull_${AG}.log" 2>&1
  echo "[$(date +%H:%M:%S)] GPT5-rareb-full DONE ${AG} exit=$?" | tee -a "$LOG/_master.log"
done
echo "[$(date +%H:%M:%S)] GPT5 rarebench-full COMPLETE" | tee -a "$LOG/_master.log"
