#!/bin/bash
# deeprare harmonize: pp→3000, rarebench→1122; Gem/V4F/V4P only (skip GPT-5 = $148 prohibitive).
set -u
cd /Users/yutianzhao/Desktop/RDAgentBenchmark
LOG=tasks/harmonize_N2000_2026_07_06/logs
PRED=data/round2/phase4a
run_cell() {
  local ds=$1 tgt=$2 bb=$3 bbtag=$4 cap=$5
  local out="$PRED/predictions_${ds}_deeprare_${bbtag}.jsonl"
  local have=0
  [ -f "$out" ] && have=$(python3 -c "import json;s=set();[s.add(json.loads(l).get('case_id')) for l in open('$out') if json.loads(l).get('status')=='ok'];print(len(s))" 2>/dev/null || echo 0)
  if [ "$have" -ge "$tgt" ]; then echo "[$(date +%H:%M:%S)] SKIP deeprare/${ds}/${bbtag} (have $have)" | tee -a "$LOG/_master.log"; return; fi
  echo "[$(date +%H:%M:%S)] START deeprare/${ds}/${bbtag} $have→$tgt" | tee -a "$LOG/_master.log"
  python3 scripts/phase4a_runner.py --dataset "$ds" --agent deeprare --backbone "$bb" \
    --n "$tgt" --timeout_s "$cap" --out "$out" >> "$LOG/${ds}_deeprare_${bbtag}.log" 2>&1
  echo "[$(date +%H:%M:%S)] DONE deeprare/${ds}/${bbtag} exit=$?" | tee -a "$LOG/_master.log"
}
for BB in "openrouter/google/gemini-3-flash-preview-20251217:google_gemini-3-flash-preview-20251217" \
          "openrouter/deepseek/deepseek-v4-flash:deepseek_deepseek-v4-flash" \
          "openrouter/deepseek/deepseek-v4-pro:deepseek_deepseek-v4-pro"; do
  bb="${BB%%:*}"; tag="${BB##*:}"
  run_cell phenopacket_store 3000 "$bb" "$tag" 900
  run_cell rarebench 1122 "$bb" "$tag" 900
done
echo "[$(date +%H:%M:%S)] deeprare HARMONIZE DONE" | tee -a "$LOG/_master.log"
