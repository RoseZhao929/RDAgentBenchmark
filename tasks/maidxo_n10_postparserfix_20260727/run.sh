#!/usr/bin/env bash
set -euo pipefail

TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$TASK_DIR/../.." && pwd)"
OUT_DIR="$ROOT/logs/maidxo_n10_postparserfix_20260727/receipts"
RUN_LOG="$ROOT/logs/maidxo_n10_postparserfix_20260727/run.log"
mkdir -p "$OUT_DIR"
cd "$ROOT"

ENV_FILE="$ROOT/.env"
if [ ! -f "$ENV_FILE" ]; then
  ENV_FILE="$ROOT/../.env"
fi
if [ ! -f "$ENV_FILE" ]; then
  echo "[fatal] no .env at repository root or parent" | tee -a "$RUN_LOG"
  exit 2
fi
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

if [ -z "${LLM_GATEWAY_URL:-}" ]; then
  echo "[fatal] LLM_GATEWAY_URL missing; silent OpenRouter fallback forbidden" |
    tee -a "$RUN_LOG"
  exit 2
fi
GATEWAY_KEY_ENV="${LLM_GATEWAY_KEY_ENV:-OPENROUTER_API_KEY}"
GATEWAY_KEY_VALUE="${!GATEWAY_KEY_ENV-}"
if [ -z "$GATEWAY_KEY_VALUE" ]; then
  echo "[fatal] gateway credential $GATEWAY_KEY_ENV missing" | tee -a "$RUN_LOG"
  exit 2
fi

# A real, tiny chat request catches exhausted keys, bad routes, and model ACLs
# before any clinical case is attempted.
python3 - <<'PY' | tee -a "$RUN_LOG"
import json
import os
import sys

import httpx

url = os.environ["LLM_GATEWAY_URL"]
key_name = os.environ.get("LLM_GATEWAY_KEY_ENV", "OPENROUTER_API_KEY")
key = os.environ[key_name]
for model in ("openai/gpt-5", "deepseek/deepseek-v4-flash"):
    response = httpx.post(
        url,
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": "Reply OK."}],
            "max_tokens": 8,
            "temperature": 0,
        },
        timeout=60,
    )
    if response.status_code != 200:
        try:
            detail = response.json().get("error", {})
        except Exception:
            detail = {"body": response.text[:200]}
        print(json.dumps({"model": model, "status": response.status_code, "error": detail}))
        sys.exit(2)
    print(json.dumps({"model": model, "status": 200, "gateway_preflight": "passed"}))
PY

CELLS=(
  "pp_gpt5|phenopacket_store|openai/gpt-5"
  "rarearena_v4flash|rarearena_rds|deepseek/deepseek-v4-flash"
  "rarearena_gpt5|rarearena_rds|openai/gpt-5"
  "rarebench_v4flash|rarebench|deepseek/deepseek-v4-flash"
  "rarebench_gpt5|rarebench|openai/gpt-5"
)

run_stage() {
  local id="$1" dataset="$2" backbone="$3" n="$4" min_ok="$5"
  local out="$OUT_DIR/${id}.jsonl"
  echo "[$(date -u +%FT%TZ)] $id stage_n=$n" | tee -a "$RUN_LOG"
  python3 scripts/phase4a_runner.py \
    --dataset "$dataset" \
    --agent maidxo \
    --backbone "$backbone" \
    --n "$n" \
    --out "$out" \
    --concurrency 2 \
    --resume-statuses "ok,skipped,parser_error" \
    --max-attempts-per-case 1 \
    --timeout_s 900 \
    >>"$RUN_LOG" 2>&1
  python3 "$TASK_DIR/gate.py" "$out" \
    --expected-unique "$n" \
    --min-ok "$min_ok" | tee -a "$RUN_LOG"
}

# Each cell must prove at least one valid disease prediction in its first two
# deterministic cases before the remaining eight are authorized.
for spec in "${CELLS[@]}"; do
  IFS='|' read -r id dataset backbone <<<"$spec"
  run_stage "$id" "$dataset" "$backbone" 2 1
  run_stage "$id" "$dataset" "$backbone" 10 1
done

echo "[$(date -u +%FT%TZ)] ALL FIVE N=10 SEMANTIC GATES PASSED" |
  tee -a "$RUN_LOG"
