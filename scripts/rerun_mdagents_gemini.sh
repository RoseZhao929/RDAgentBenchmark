#!/usr/bin/env bash
# Re-run ONLY mdagents × gemini on the MIMIC-note 416 line with a HIGH timeout.
#
# WHY: the original run used --timeout_s 360, but mdagents on gemini-3-flash is
# 10-30x slower than on other backbones (ok-case median ~179s, max ~360s) — so
# 253/416 cases hit the 360s wall and were cut off mid-run (false timeouts, not
# real failures). Other 3 backbones (median 6-17s) are healthy and NOT re-run.
#
# Resume: phase4a_runner skips the 162 already-ok cases; only the ~254 non-ok
# get re-attempted. Timeout raised to 1200s so slow-but-real cases can finish.
# Failures/timeouts that REMAIN after this are kept in the R@1 denominator.
#
# WAITS for the deeprare e2e rerun to finish first (they'd contend for CPU).
set -uo pipefail
ROOT="/home/research/RDAgentBenchmark"; cd "$ROOT"

# ---- gate: wait until the deeprare e2e rerun is done ----
echo "[mdagents-gemini] waiting for deeprare e2e rerun to finish..."
while pgrep -f "rerun_deeprare_e2e.sh" >/dev/null 2>&1 || pgrep -f "agent deeprare --backbone" >/dev/null 2>&1; do
  sleep 120
done
echo "[mdagents-gemini] deeprare done; starting @ $(date +%H:%M:%S)"

OUT="data/round2/phase4a_mimic_note/predictions_mimic_note_mdagents_google_gemini-3-flash-preview-20251217.jsonl"
LOG="logs/mimic_note/mdagents_gemini_rerun.log"
python3 scripts/phase4a_runner.py \
  --dataset mimic_note --agent mdagents --backbone google/gemini-3-flash-preview \
  --n 416 --out "$OUT" --concurrency 8 --timeout_s 1200 \
  > "$LOG" 2>&1
echo "[mdagents-gemini] done rc=$? @ $(date +%H:%M:%S) -> $OUT"
