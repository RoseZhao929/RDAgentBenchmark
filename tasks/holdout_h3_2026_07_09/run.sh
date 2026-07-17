#!/bin/bash
set -u
cd /Users/yutianzhao/Desktop/RDAgentBenchmark
LOG=tasks/holdout_h3_2026_07_09/logs
PRED=data/round2/phase4a
for BB in "openrouter/google/gemini-3-flash-preview-20251217:google_gemini-3-flash-preview-20251217:600" \
          "openrouter/deepseek/deepseek-v4-flash:deepseek_deepseek-v4-flash:900"; do
  bb="${BB%%:*}"; rest="${BB#*:}"; tag="${rest%%:*}"; cap="${rest##*:}"
  for AG in llm_control agentclinic mdagents medagents; do
    OUT="$PRED/predictions_pmc_oa_holdout_${AG}_${tag}.jsonl"
    echo "[$(date +%H:%M:%S)] START ${AG}/${tag}" | tee -a "$LOG/_master.log"
    python3 scripts/phase4a_runner.py --dataset pmc_oa_holdout --agent "$AG" --backbone "$bb" \
      --n 1000 --timeout_s "$cap" --concurrency 6 --out "$OUT" >> "$LOG/${AG}_${tag}.log" 2>&1
    echo "[$(date +%H:%M:%S)] DONE ${AG}/${tag} exit=$?" | tee -a "$LOG/_master.log"
  done
done
echo "[$(date +%H:%M:%S)] HOLDOUT H3 ALL DONE" | tee -a "$LOG/_master.log"
