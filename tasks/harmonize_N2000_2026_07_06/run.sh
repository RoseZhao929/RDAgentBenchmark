#!/bin/bash
# Harmonize pp + rarearena to N=2000 (same seed=42 first-2000 case_ids) for the
# 4 core agents × 4 backbones. RESUME adds only the missing cases. Gemini cells
# already >2000 are skipped (capped to first-2000 at aggregation).
set -u
cd /Users/yutianzhao/Desktop/RDAgentBenchmark
LOG=tasks/harmonize_N2000_2026_07_06/logs
PRED=data/round2/phase4a
TARGET=2000

run_cell() {
  local ds=$1 ag=$2 bb=$3 bbtag=$4 cap=$5
  local out="$PRED/predictions_${ds}_${ag}_${bbtag}.jsonl"
  # skip if already >= TARGET unique ok
  local have=$(python3 -c "import json,sys;s=set();[s.add(json.loads(l).get('case_id')) for l in open('$out') if json.loads(l).get('status')=='ok'] if __import__('os').path.exists('$out') else None;print(len(s))" 2>/dev/null || echo 0)
  if [ "$have" -ge "$TARGET" ]; then echo "[$(date +%H:%M:%S)] SKIP ${ds}/${ag}/${bbtag} (have $have>=2000)" | tee -a "$LOG/_master.log"; return; fi
  echo "[$(date +%H:%M:%S)] START ${ds}/${ag}/${bbtag} have=$have→$TARGET" | tee -a "$LOG/_master.log"
  python3 scripts/phase4a_runner.py --dataset "$ds" --agent "$ag" --backbone "$bb" \
    --n "$TARGET" --timeout_s "$cap" --out "$out" >> "$LOG/${ds}_${ag}_${bbtag}.log" 2>&1
  echo "[$(date +%H:%M:%S)] DONE ${ds}/${ag}/${bbtag} exit=$?" | tee -a "$LOG/_master.log"
}

# backbones: id + filename-tag + timeout cap
for DS in phenopacket_store rarearena_rds; do
  for AG in llm_control agentclinic mdagents medagents; do
    run_cell "$DS" "$AG" "openrouter/google/gemini-3-flash-preview-20251217" "google_gemini-3-flash-preview-20251217" 600
    run_cell "$DS" "$AG" "openrouter/deepseek/deepseek-v4-flash" "deepseek_deepseek-v4-flash" 900
    run_cell "$DS" "$AG" "openrouter/deepseek/deepseek-v4-pro" "deepseek_deepseek-v4-pro" 1200
    run_cell "$DS" "$AG" "openrouter/openai/gpt-5" "openai_gpt-5" 900
  done
done
# offline baselines (free) on pp
run_cell phenopacket_store lirical "lirical" "lirical-2.4.0" 600
run_cell phenopacket_store vc_rdagent "vc_rdagent" "vc_rdagent-offline-v1" 600
echo "[$(date +%H:%M:%S)] HARMONIZE COMPLETE" | tee -a "$LOG/_master.log"
