#!/bin/bash
# H6 thinking-mode ablation: llm_control × V4-Pro reasoning-ON, N=500/dataset.
# Output to a separate dir so it never merges into the main reasoning-OFF matrix.
set -u
cd /Users/yutianzhao/Desktop/RDAgentBenchmark
BB=openrouter/deepseek/deepseek-v4-pro
LOG=tasks/v4pro_reasoning_off_2026_07_03/logs
OUTDIR=data/round2/phase4a_h6_reasoning_on
mkdir -p "$OUTDIR"
for DS in phenopacket_store rarearena_rds mimic_diverse rarebench; do
  OUT="$OUTDIR/predictions_${DS}_llm_control_deepseek_deepseek-v4-pro_reasoningON.jsonl"
  echo "[$(date +%H:%M:%S)] H6 START ${DS} n=500" | tee -a "$LOG/_master.log"
  python3 scripts/phase4a_runner.py --dataset "$DS" --agent llm_control \
    --backbone "$BB" --n 500 --reasoning_on --timeout_s 600 \
    --out "$OUT" >> "$LOG/h6_${DS}.log" 2>&1
  echo "[$(date +%H:%M:%S)] H6 DONE ${DS} exit=$?" | tee -a "$LOG/_master.log"
done
echo "[$(date +%H:%M:%S)] H6 COMPLETE" | tee -a "$LOG/_master.log"
