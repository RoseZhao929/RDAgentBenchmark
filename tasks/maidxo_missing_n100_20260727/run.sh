#!/usr/bin/env bash
set -uo pipefail

TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$TASK_DIR/../.." && pwd)"
LOG_DIR="$ROOT/logs/maidxo_missing_n100_20260727"
STATE_DIR="$LOG_DIR/state"
LOCK_DIR="$LOG_DIR/orchestrator.lock"
ORCH_LOG="$LOG_DIR/orchestrator.log"
CELL_CONCURRENCY="${CELL_CONCURRENCY:-4}"

mkdir -p "$STATE_DIR"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "[orchestrator] another instance owns $LOCK_DIR; exiting"
  exit 0
fi
cleanup() {
  rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

cd "$ROOT"

# Prefer the repository-local .env. On this workstation the credential file is
# one directory above the repository. Never copy or print it.
ENV_FILE="$ROOT/.env"
if [ ! -f "$ENV_FILE" ]; then
  ENV_FILE="$ROOT/../.env"
fi
if [ ! -f "$ENV_FILE" ]; then
  echo "[orchestrator] no .env found at $ROOT/.env or $ROOT/../.env" | tee -a "$ORCH_LOG"
  exit 1
fi
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
if [ -z "${LLM_GATEWAY_URL:-}" ]; then
  echo "[orchestrator] LLM_GATEWAY_URL is required; refusing silent OpenRouter fallback" | tee -a "$ORCH_LOG"
  exit 1
fi
GATEWAY_KEY_ENV="${LLM_GATEWAY_KEY_ENV:-OPENROUTER_API_KEY}"
GATEWAY_KEY_VALUE="${!GATEWAY_KEY_ENV-}"
if [ -z "$GATEWAY_KEY_VALUE" ]; then
  echo "[orchestrator] gateway key env $GATEWAY_KEY_ENV is unset" | tee -a "$ORCH_LOG"
  exit 1
fi

if [ ! -x agents/maidxo/.venv/bin/python ]; then
  echo "[orchestrator] MAI-DxO venv missing" | tee -a "$ORCH_LOG"
  exit 1
fi
if ! grep -q "looks_like_vitals" agents/maidxo/mai_dx/main.py; then
  echo "[orchestrator] regex fix missing; refusing to run" | tee -a "$ORCH_LOG"
  exit 1
fi
if ! grep -q 'case_workdir = tempfile.mkdtemp' harness/agents/maidxo.py; then
  echo "[orchestrator] MAI-DxO per-case workspace isolation missing; refusing concurrent run" | tee -a "$ORCH_LOG"
  exit 1
fi
if ! agents/maidxo/.venv/bin/python -c "import litellm, httpx, socksio" \
    >/dev/null 2>&1; then
  echo "[orchestrator] MAI-DxO LiteLLM/httpx/SOCKS imports failed" | tee -a "$ORCH_LOG"
  exit 1
fi

# id|dataset|backbone|output filename|full target
CELLS=(
  "pp_gpt5|phenopacket_store|openai/gpt-5|predictions_phenopacket_store_maidxo_openai_gpt-5.jsonl|2000"
  "rarearena_v4flash|rarearena_rds|deepseek/deepseek-v4-flash|predictions_rarearena_rds_maidxo_deepseek_deepseek-v4-flash.jsonl|2000"
  "rarearena_gpt5|rarearena_rds|openai/gpt-5|predictions_rarearena_rds_maidxo_openai_gpt-5.jsonl|2000"
  "rarebench_v4flash|rarebench|deepseek/deepseek-v4-flash|predictions_rarebench_maidxo_deepseek_deepseek-v4-flash.jsonl|1122"
  "rarebench_gpt5|rarebench|openai/gpt-5|predictions_rarebench_maidxo_openai_gpt-5.jsonl|1122"
)

run_cell() {
  local spec="$1"
  local id dataset backbone filename full_target
  IFS='|' read -r id dataset backbone filename full_target <<<"$spec"
  local done_file="$STATE_DIR/$id.done"
  local meta_file="$STATE_DIR/$id.meta"
  local cell_log="$LOG_DIR/$id.log"
  local out="$ROOT/data/round2/phase4a/$filename"

  if [ -f "$done_file" ]; then
    echo "[$(date -u +%FT%TZ)] SKIP done $id" | tee -a "$ORCH_LOG"
    return 0
  fi

  local start_epoch
  start_epoch="$(date +%s)"
  {
    echo "id=$id"
    echo "dataset=$dataset"
    echo "backbone=$backbone"
    echo "n=100"
    echo "full_target=$full_target"
    echo "output=$out"
    echo "start_epoch=$start_epoch"
    echo "start_utc=$(date -u +%FT%TZ)"
  } >"$meta_file"
  echo "[$(date -u +%FT%TZ)] START $id dataset=$dataset backbone=$backbone" | tee -a "$ORCH_LOG"

  python3 scripts/phase4a_runner.py \
    --dataset "$dataset" \
    --agent maidxo \
    --backbone "$backbone" \
    --n 100 \
    --out "$out" \
    --concurrency "$CELL_CONCURRENCY" \
    --resume-statuses "ok,skipped,parser_error" \
    --max-attempts-per-case 3 \
    --timeout_s 900 \
    >"$cell_log" 2>&1
  local rc=$?
  # MAI-DxO's upstream regex occasionally emits copied vignette/lab fragments
  # as nominal diagnoses. Sanitize completed receipts without repeating model
  # calls; raw output, trace, latency, and cost remain in the audit envelope.
  python3 "$TASK_DIR/sanitize_receipts.py" "$out" >>"$cell_log" 2>&1
  local sanitize_rc=$?
  if [ "$sanitize_rc" -ne 0 ]; then
    echo "[$(date -u +%FT%TZ)] SANITIZE FAILED $id rc=$sanitize_rc" | tee -a "$ORCH_LOG"
    rc=1
  fi
  local end_epoch
  end_epoch="$(date +%s)"
  {
    echo "end_epoch=$end_epoch"
    echo "end_utc=$(date -u +%FT%TZ)"
    echo "wall_seconds=$((end_epoch - start_epoch))"
    echo "return_code=$rc"
  } >>"$meta_file"

  local counts
  counts="$(python3 - "$out" <<'PY'
import json
import sys
from collections import Counter, defaultdict

rows = []
try:
    with open(sys.argv[1]) as handle:
        for line in handle:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
except FileNotFoundError:
    pass
attempts = Counter(str(row.get("case_id")) for row in rows if row.get("case_id") is not None)
terminal = {"ok", "skipped", "parser_error"}
settled = set()
n_ok = 0
for row in rows:
    case_id = row.get("case_id")
    if case_id is None:
        continue
    if row.get("status") == "ok":
        n_ok += 1
    if row.get("status") in terminal or attempts[str(case_id)] >= 3:
        settled.add(str(case_id))
print(f"{n_ok} {len(settled)}")
PY
)"
  local n_ok n_settled
  read -r n_ok n_settled <<<"$counts"
  if [ "$rc" -eq 0 ] && grep -q "\\[p4a\\] DONE" "$cell_log" && [ "$n_settled" -ge 100 ]; then
    {
      echo "completed_utc=$(date -u +%FT%TZ)"
      echo "return_code=$rc"
    } >"$done_file"
    echo "[$(date -u +%FT%TZ)] DONE $id wall=$((end_epoch - start_epoch))s" | tee -a "$ORCH_LOG"
  else
    echo "[$(date -u +%FT%TZ)] INCOMPLETE $id rc=$rc ok=$n_ok settled=$n_settled/100; rerun run.sh to resume" | tee -a "$ORCH_LOG"
    return 1
  fi
}

echo "[$(date -u +%FT%TZ)] ORCHESTRATOR START pid=$$" >>"$ORCH_LOG"

# At most two cells at once. The supervisor selects per-cell concurrency from
# memory pressure (2--4), for at most 4--8 MAI-DxO subprocesses.
for ((i=0; i<${#CELLS[@]}; i+=2)); do
  pids=()
  run_cell "${CELLS[$i]}" &
  pids+=("$!")
  if ((i + 1 < ${#CELLS[@]})); then
    run_cell "${CELLS[$((i + 1))]}" &
    pids+=("$!")
  fi
  wave_rc=0
  for pid in "${pids[@]}"; do
    wait "$pid" || wave_rc=1
  done
  if [ "$wave_rc" -ne 0 ]; then
    echo "[$(date -u +%FT%TZ)] ORCHESTRATOR PAUSED after incomplete wave" | tee -a "$ORCH_LOG"
    exit 1
  fi
done

python3 "$TASK_DIR/summarize.py" >>"$ORCH_LOG" 2>&1
echo "[$(date -u +%FT%TZ)] ORCHESTRATOR ALL DONE" | tee -a "$ORCH_LOG"
