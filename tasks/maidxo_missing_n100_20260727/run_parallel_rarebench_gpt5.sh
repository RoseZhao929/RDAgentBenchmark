#!/usr/bin/env bash
set -uo pipefail

# Launch the fifth cell alongside the orchestrator's second wave. A temporary
# reservation marker makes the original two-cell-wave orchestrator skip this
# cell when it reaches wave 3, preventing duplicate model calls.

TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$TASK_DIR/../.." && pwd)"
LOG_DIR="$ROOT/logs/maidxo_missing_n100_20260727"
STATE_DIR="$LOG_DIR/state"
CELL_ID="rarebench_gpt5"
DONE_FILE="$STATE_DIR/$CELL_ID.done"
LOCK_DIR="$LOG_DIR/$CELL_ID.parallel.lock"
CELL_LOG="$LOG_DIR/$CELL_ID.log"
META_FILE="$STATE_DIR/$CELL_ID.meta"
OUT="$ROOT/data/round2/phase4a/predictions_rarebench_maidxo_openai_gpt-5.jsonl"
RESERVATION="parallel_reservation_pid=$$"

mkdir -p "$STATE_DIR"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "[parallel] another $CELL_ID launcher owns $LOCK_DIR"
  exit 0
fi

success=0
cleanup() {
  if [ "$success" -ne 1 ] && grep -qx "$RESERVATION" "$DONE_FILE" 2>/dev/null; then
    rm -f "$DONE_FILE"
  fi
  rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

if [ -f "$DONE_FILE" ] && ! grep -q '^parallel_reservation_pid=' "$DONE_FILE"; then
  echo "[parallel] $CELL_ID already complete"
  success=1
  exit 0
fi
printf '%s\n' "$RESERVATION" >"$DONE_FILE"

cd "$ROOT"
ENV_FILE="$ROOT/.env"
if [ ! -f "$ENV_FILE" ]; then
  ENV_FILE="$ROOT/../.env"
fi
if [ ! -f "$ENV_FILE" ]; then
  echo "[parallel] credential file missing" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

start_epoch="$(date +%s)"
{
  echo "id=$CELL_ID"
  echo "dataset=rarebench"
  echo "backbone=openai/gpt-5"
  echo "n=100"
  echo "full_target=1122"
  echo "output=$OUT"
  echo "start_epoch=$start_epoch"
  echo "start_utc=$(date -u +%FT%TZ)"
  echo "launch_mode=parallel_third_cell"
  echo "cell_concurrency=4"
} >"$META_FILE"

echo "[$(date -u +%FT%TZ)] PARALLEL START $CELL_ID" | tee -a "$LOG_DIR/orchestrator.log"
python3 scripts/phase4a_runner.py \
  --dataset rarebench \
  --agent maidxo \
  --backbone openai/gpt-5 \
  --n 100 \
  --out "$OUT" \
  --concurrency 4 \
  --resume-statuses "ok,skipped,parser_error" \
  --max-attempts-per-case 3 \
  --timeout_s 900 \
  >"$CELL_LOG" 2>&1
rc=$?
python3 "$TASK_DIR/sanitize_receipts.py" "$OUT" >>"$CELL_LOG" 2>&1 || rc=1

end_epoch="$(date +%s)"
{
  echo "end_epoch=$end_epoch"
  echo "end_utc=$(date -u +%FT%TZ)"
  echo "wall_seconds=$((end_epoch - start_epoch))"
  echo "return_code=$rc"
} >>"$META_FILE"

settled="$(python3 - "$OUT" <<'PY'
import json
import sys
from collections import Counter

rows = [json.loads(line) for line in open(sys.argv[1])]
attempts = Counter(str(row.get("case_id")) for row in rows)
terminal = {"ok", "skipped", "parser_error"}
settled = {
    str(row.get("case_id"))
    for row in rows
    if row.get("status") in terminal or attempts[str(row.get("case_id"))] >= 3
}
print(len(settled))
PY
)"

if [ "$rc" -eq 0 ] && grep -q '\[p4a\] DONE' "$CELL_LOG" && [ "$settled" -ge 100 ]; then
  {
    echo "completed_utc=$(date -u +%FT%TZ)"
    echo "return_code=0"
    echo "launch_mode=parallel_third_cell"
  } >"$DONE_FILE"
  success=1
  echo "[$(date -u +%FT%TZ)] PARALLEL DONE $CELL_ID wall=$((end_epoch - start_epoch))s" |
    tee -a "$LOG_DIR/orchestrator.log"
  exit 0
fi

echo "[$(date -u +%FT%TZ)] PARALLEL INCOMPLETE $CELL_ID rc=$rc settled=$settled/100" |
  tee -a "$LOG_DIR/orchestrator.log"
exit 1
