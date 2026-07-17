#!/bin/bash
# Usage: run_agent.sh <agent>  — harmonize one agent's pp+rarearena to N=2000
# across 4 backbones (backbones sequential within this stream). bash 3.2 safe.
set -u
cd /Users/yutianzhao/Desktop/RDAgentBenchmark
AG="$1"
LOG=tasks/harmonize_N2000_2026_07_06/logs
PRED=data/round2/phase4a
TARGET=2000

run_cell() {
  local ds=$1 bb=$2 bbtag=$3 cap=$4
  local out="$PRED/predictions_${ds}_${AG}_${bbtag}.jsonl"
  local have=0
  if [ -f "$out" ]; then
    have=$(python3 -c "import json;s=set();[s.add(json.loads(l).get('case_id')) for l in open('$out') if json.loads(l).get('status')=='ok'];print(len(s))" 2>/dev/null || echo 0)
  fi
  if [ "$have" -ge "$TARGET" ]; then echo "[$(date +%H:%M:%S)] SKIP ${ds}/${AG}/${bbtag} (have $have)" | tee -a "$LOG/_master.log"; return; fi
  echo "[$(date +%H:%M:%S)] START ${ds}/${AG}/${bbtag} $have→$TARGET" | tee -a "$LOG/_master.log"
  python3 scripts/phase4a_runner.py --dataset "$ds" --agent "$AG" --backbone "$bb" \
    --n "$TARGET" --timeout_s "$cap" --concurrency 8 --out "$out" >> "$LOG/${ds}_${AG}_${bbtag}.log" 2>&1
  echo "[$(date +%H:%M:%S)] DONE ${ds}/${AG}/${bbtag} exit=$?" | tee -a "$LOG/_master.log"
}

for DS in phenopacket_store rarearena_rds; do
  run_cell "$DS" "openrouter/google/gemini-3-flash-preview-20251217" "google_gemini-3-flash-preview-20251217" 600
  run_cell "$DS" "openrouter/deepseek/deepseek-v4-flash" "deepseek_deepseek-v4-flash" 900
  run_cell "$DS" "openrouter/deepseek/deepseek-v4-pro" "deepseek_deepseek-v4-pro" 1200
  run_cell "$DS" "openrouter/openai/gpt-5" "openai_gpt-5" 900
done
echo "[$(date +%H:%M:%S)] AGENT ${AG} HARMONIZE DONE" | tee -a "$LOG/_master.log"
