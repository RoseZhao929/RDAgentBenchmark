#!/usr/bin/env bash
set -uo pipefail

TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$TASK_DIR/../.." && pwd)"
LOG_DIR="$ROOT/logs/maidxo_missing_n100_20260727"
DONE_FILE="$LOG_DIR/state/rarebench_gpt5.done"
OUT="$ROOT/data/round2/phase4a/predictions_rarebench_maidxo_openai_gpt-5.jsonl"
WATCH_LOG="$LOG_DIR/rarebench_gpt5_watchdog.log"
STALL_SECONDS=1500
last_count=-1
last_progress="$(date +%s)"

count_unique() {
  python3 - "$OUT" <<'PY'
import json
import sys

seen = set()
try:
    for line in open(sys.argv[1], errors="replace"):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("case_id") is not None:
            seen.add(str(row["case_id"]))
except FileNotFoundError:
    pass
print(len(seen))
PY
}

while true; do
  now="$(date +%s)"
  count="$(count_unique)"
  if [ "$count" -gt "$last_count" ]; then
    last_count="$count"
    last_progress="$now"
  fi
  echo "[$(date -u +%FT%TZ)] unique=$count/100 idle=$((now - last_progress))s" >>"$WATCH_LOG"

  if [ "$count" -ge 100 ] && ! grep -q '^parallel_reservation_pid=' "$DONE_FILE" 2>/dev/null; then
    exit 0
  fi
  screen_output="$(screen -list 2>/dev/null || true)"
  if ! grep -q 'maidxo_rb_gpt5_parallel' <<<"$screen_output"; then
    if grep -q '^parallel_reservation_pid=' "$DONE_FILE" 2>/dev/null; then
      rm -f "$DONE_FILE"
      echo "[$(date -u +%FT%TZ)] launcher vanished; cleared reservation" >>"$WATCH_LOG"
    fi
    exit 1
  fi
  if [ $((now - last_progress)) -gt "$STALL_SECONDS" ]; then
    echo "[$(date -u +%FT%TZ)] stalled >25m; stopping parallel launcher" >>"$WATCH_LOG"
    screen -S maidxo_rb_gpt5_parallel -X quit 2>/dev/null || true
    sleep 2
    if grep -q '^parallel_reservation_pid=' "$DONE_FILE" 2>/dev/null; then
      rm -f "$DONE_FILE"
    fi
    rmdir "$LOG_DIR/rarebench_gpt5.parallel.lock" 2>/dev/null || true
    exit 2
  fi
  sleep 60
done
