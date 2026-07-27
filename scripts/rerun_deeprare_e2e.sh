#!/usr/bin/env bash
# Re-run deeprare on the MIMIC-note 416 HPO-line for ALL 4 backbones, using the
# new end_to_end free-text→HPO extraction path (deeprare.py _extract_hpo_from_free_text).
#
# WHY: mimic_note is NO_HPO (free text); deeprare's input projection only read
# gold_hpo_terms, so it got EMPTY HPO → PubCaseFinder no-results → zero-shot
# guessing → false 0.000 R@1. The stale empty-HPO predictions were backed up to
# audit_frozen/mimic_note_experiment/deeprare_empty_hpo_v0/ and removed, so this
# runs each case fresh.
#
# SERIAL across backbones (deeprare ~2GB/proc; never 2 instances at once).
# Resumable within a backbone. Failures/timeouts kept in the R@1 denominator.
set -uo pipefail
ROOT="/home/research/RDAgentBenchmark"; cd "$ROOT"
N=416
OUTDIR="data/round2/phase4a_mimic_note"; LOGDIR="logs/mimic_note"
mkdir -p "$OUTDIR" "$LOGDIR"

declare -A SUFFIX=(
  ["deepseek/deepseek-v4-pro"]="deepseek__deepseek-v4-pro"
  ["deepseek/deepseek-v4-flash"]="deepseek_deepseek-v4-flash"
  ["openai/gpt-5"]="openai_gpt-5"
  ["google/gemini-3-flash-preview"]="google_gemini-3-flash-preview-20251217"
)

for BB in "deepseek/deepseek-v4-pro" "deepseek/deepseek-v4-flash" "openai/gpt-5" "google/gemini-3-flash-preview"; do
  suf="${SUFFIX[$BB]}"
  out="$OUTDIR/predictions_mimic_note_deeprare_${suf}.jsonl"
  log="$LOGDIR/deeprare_e2e_${suf}.log"
  echo "===== DEEPRARE e2e @ $BB $(date +%H:%M:%S) ====="
  python3 scripts/phase4a_runner.py \
    --dataset mimic_note --agent deeprare --backbone "$BB" \
    --n "$N" --out "$out" --concurrency 6 --timeout_s 600 \
    > "$log" 2>&1
  echo "[done $(date +%H:%M:%S)] deeprare @ $BB rc=$? -> $out"
done
echo "=== DEEPRARE e2e ALL 4 BACKBONES DONE $(date +%H:%M:%S) ==="
