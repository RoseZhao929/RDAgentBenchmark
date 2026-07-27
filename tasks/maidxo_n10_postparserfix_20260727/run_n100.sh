#!/usr/bin/env bash
set -euo pipefail

TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$TASK_DIR/../.." && pwd)"
OUT_DIR="$ROOT/data/round2/phase4a"
STATE_DIR="$ROOT/logs/maidxo_n100_20260727"
LOG_DIR="$STATE_DIR/cell_logs"
mkdir -p "$OUT_DIR" "$LOG_DIR"
cd "$ROOT"

ENV_FILE="$ROOT/.env"
if [ ! -f "$ENV_FILE" ]; then
  ENV_FILE="$ROOT/../.env"
fi
if [ ! -f "$ENV_FILE" ]; then
  echo "[fatal] no .env at repository root or parent"
  exit 2
fi
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

: "${LLM_GATEWAY_URL:?LLM_GATEWAY_URL is required}"
GATEWAY_KEY_ENV="${LLM_GATEWAY_KEY_ENV:-OPENROUTER_API_KEY}"
GATEWAY_KEY_VALUE="${!GATEWAY_KEY_ENV-}"
if [ -z "$GATEWAY_KEY_VALUE" ]; then
  echo "[fatal] gateway credential $GATEWAY_KEY_ENV missing"
  exit 2
fi

python3 - <<'PY'
import json
import os
import sys

import httpx

url = os.environ["LLM_GATEWAY_URL"]
key = os.environ[os.environ.get("LLM_GATEWAY_KEY_ENV", "OPENROUTER_API_KEY")]
models = (
    os.environ.get("LLM_GATEWAY_GPT5_MODEL", "openai/gpt-5"),
    os.environ.get(
        "LLM_GATEWAY_V4FLASH_MODEL", "deepseek/deepseek-v4-flash"
    ),
)
for model in models:
    response = httpx.post(
        url,
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": "Reply OK."}],
            "max_tokens": 512,
            "temperature": 0,
            "reasoning_effort": "minimal",
        },
        timeout=60,
    )
    if response.status_code != 200:
        print(
            json.dumps(
                {
                    "model": model,
                    "status": response.status_code,
                    "body": response.text[:300],
                }
            )
        )
        sys.exit(2)
    payload = response.json()
    choices = payload.get("choices") or []
    content = (
        ((choices[0].get("message") or {}).get("content") or "")
        if choices
        else ""
    )
    if not str(content).strip():
        print(
            json.dumps(
                {
                    "model": model,
                    "status": 200,
                    "gateway_preflight": "failed_empty_content",
                }
            )
        )
        sys.exit(2)
    print(
        json.dumps(
            {
                "model": model,
                "status": 200,
                "gateway_preflight": "passed",
            }
        )
    )
PY

CELLS=(
  "pp_gpt5|phenopacket_store|openai/gpt-5|predictions_phenopacket_store_maidxo_openai_gpt-5.jsonl"
  "rarearena_v4flash|rarearena_rds|deepseek/deepseek-v4-flash|predictions_rarearena_rds_maidxo_deepseek_deepseek-v4-flash.jsonl"
  "rarearena_gpt5|rarearena_rds|openai/gpt-5|predictions_rarearena_rds_maidxo_openai_gpt-5.jsonl"
  "rarebench_v4flash|rarebench|deepseek/deepseek-v4-flash|predictions_rarebench_maidxo_deepseek_deepseek-v4-flash.jsonl"
  "rarebench_gpt5|rarebench|openai/gpt-5|predictions_rarebench_maidxo_openai_gpt-5.jsonl"
)

pids=()
for spec in "${CELLS[@]}"; do
  IFS='|' read -r id dataset backbone filename <<<"$spec"
  if [ -n "${CELL_FILTER:-}" ] && [ "$id" != "$CELL_FILTER" ]; then
    continue
  fi
  gateway_model="$backbone"
  if [[ "$backbone" == *"gpt-5"* ]] && [ -n "${LLM_GATEWAY_GPT5_MODEL:-}" ]; then
    gateway_model="$LLM_GATEWAY_GPT5_MODEL"
  elif [[ "$backbone" == *"deepseek-v4-flash"* ]] && \
    [ -n "${LLM_GATEWAY_V4FLASH_MODEL:-}" ]; then
    gateway_model="$LLM_GATEWAY_V4FLASH_MODEL"
  fi
  if [[ "$gateway_model" != */* ]]; then
    gateway_model="openai/$gateway_model"
  fi
  log="$LOG_DIR/${id}.log"
  echo "[$(date -u +%FT%TZ)] launching $id N=100" | tee -a "$log"
  MAIDXO_MODEL_OVERRIDE="$gateway_model" \
    python3 scripts/phase4a_runner.py \
      --dataset "$dataset" \
      --agent maidxo \
      --backbone "$backbone" \
      --n 100 \
      --out "$OUT_DIR/$filename" \
      --concurrency "${CELL_CONCURRENCY:-2}" \
      --resume-statuses "ok,skipped" \
      --max-attempts-per-case 2 \
      --timeout_s 900 \
      >>"$log" 2>&1 &
  pids+=("$!")
  echo "$id pid=$!"
done

failures=0
for pid in "${pids[@]}"; do
  if ! wait "$pid"; then
    failures=$((failures + 1))
  fi
done
if [ "$failures" -ne 0 ]; then
  echo "[fatal] $failures N=100 cell runner(s) exited nonzero"
  exit 2
fi

python3 "$TASK_DIR/audit_n10.py" \
  --phase4a-dir "$OUT_DIR" \
  --expected-n 100 \
  --allow-model-abstentions \
  --report "$STATE_DIR/audit_n100.json"
