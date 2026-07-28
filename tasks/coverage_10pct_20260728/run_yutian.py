#!/usr/bin/env python3
"""Resumable, resource-bounded runner for PLAN_yutian.md.

The filename encoding (``openai_gpt-5``) is intentionally separate from the
canonical backbone ID passed to the runner (``openrouter/openai/gpt-5``).
MAI-DxO uses an explicit AIHubMix wire-model override while receipts retain the
canonical ID already used by each existing Phase 4a file.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "round2" / "phase4a"
STATE_DIR = ROOT / "logs" / "coverage_10pct_20260728"
CELL_LOG_DIR = STATE_DIR / "cell_logs"
STATE_PATH = STATE_DIR / "state.json"


@dataclass(frozen=True)
class Cell:
    cell_id: str
    dataset: str
    agent: str
    backbone: str
    target: int
    concurrency: int
    filename: str
    wire_model: str | None = None


CELLS = (
    Cell(
        "mx_pp_flash",
        "phenopacket_store",
        "maidxo",
        "openrouter/deepseek/deepseek-v4-flash",
        200,
        10,
        "predictions_phenopacket_store_maidxo_deepseek_deepseek-v4-flash.jsonl",
        "openai/deepseek-v4-flash",
    ),
    Cell(
        "dr_pp_gpt5",
        "phenopacket_store",
        "deeprare",
        "openrouter/openai/gpt-5",
        200,
        5,
        "predictions_phenopacket_store_deeprare_openai_gpt-5.jsonl",
    ),
    Cell(
        "mx_pp_gem",
        "phenopacket_store",
        "maidxo",
        "openrouter/google/gemini-3-flash-preview-20251217",
        200,
        10,
        "predictions_phenopacket_store_maidxo_google_gemini-3-flash-preview-20251217.jsonl",
        "openai/gemini-3-flash-preview",
    ),
    Cell(
        "mx_ra_gem",
        "rarearena_rds",
        "maidxo",
        "openrouter/google/gemini-3-flash-preview-20251217",
        200,
        10,
        "predictions_rarearena_rds_maidxo_google_gemini-3-flash-preview-20251217.jsonl",
        "openai/gemini-3-flash-preview",
    ),
    Cell(
        "dr_ra_gpt5",
        "rarearena_rds",
        "deeprare",
        "openrouter/openai/gpt-5",
        200,
        5,
        "predictions_rarearena_rds_deeprare_openai_gpt-5.jsonl",
    ),
    Cell(
        "mx_ra_flash",
        "rarearena_rds",
        "maidxo",
        "deepseek/deepseek-v4-flash",
        200,
        10,
        "predictions_rarearena_rds_maidxo_deepseek_deepseek-v4-flash.jsonl",
        "openai/deepseek-v4-flash",
    ),
    Cell(
        "mx_ra_gpt5",
        "rarearena_rds",
        "maidxo",
        "openai/gpt-5",
        200,
        8,
        "predictions_rarearena_rds_maidxo_openai_gpt-5.jsonl",
        "openai/gpt-5",
    ),
    Cell(
        "mx_pp_gpt5",
        "phenopacket_store",
        "maidxo",
        "openai/gpt-5",
        200,
        8,
        "predictions_phenopacket_store_maidxo_openai_gpt-5.jsonl",
        "openai/gpt-5",
    ),
    Cell(
        "dr_rb_gpt5",
        "rarebench",
        "deeprare",
        "openrouter/openai/gpt-5",
        113,
        5,
        "predictions_rarebench_deeprare_openai_gpt-5.jsonl",
    ),
)

TERMINAL = {"ok", "skipped", "parser_error"}
RETRYABLE = {"agent_error", "timeout"}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_dotenv() -> None:
    for path in (ROOT / ".env", ROOT.parent / ".env"):
        if not path.exists():
            continue
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))
        return
    raise RuntimeError("no .env at repository root or parent")


def gateway_preflight() -> None:
    import httpx

    url = os.environ["LLM_GATEWAY_URL"]
    key = os.environ[os.environ["LLM_GATEWAY_KEY_ENV"]]
    for model in ("gpt-5", "deepseek-v4-flash", "gemini-3-flash-preview"):
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": "Reply with exactly OK."}
            ],
            "max_tokens": 512,
            "temperature": 0,
        }
        if model == "gpt-5":
            payload["reasoning_effort"] = "minimal"
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
            timeout=90,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"gateway preflight failed for {model}: "
                f"HTTP {response.status_code} {response.text[:200]}"
            )
        choices = response.json().get("choices") or []
        content = (
            ((choices[0].get("message") or {}).get("content") or "")
            if choices
            else ""
        )
        if not str(content).strip():
            raise RuntimeError(
                f"gateway preflight returned empty content for {model}"
            )


def receipt_state(cell: Cell) -> dict:
    path = OUT_DIR / cell.filename
    rows: list[dict] = []
    malformed = 0
    if path.exists():
        for line in path.open(errors="replace"):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                malformed += 1
    attempts: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row.get("case_id") is not None:
            attempts[str(row["case_id"])].append(row)
    chosen: dict[str, dict] = {}
    for case_id, case_rows in attempts.items():
        chosen[case_id] = case_rows[-1]
        for row in case_rows:
            if row.get("status") in TERMINAL:
                chosen[case_id] = row
                break
    retryable = [
        case_id
        for case_id, row in chosen.items()
        if row.get("status") in RETRYABLE and len(attempts[case_id]) < 2
    ]
    return {
        "raw_rows": len(rows),
        "unique": len(attempts),
        "remaining_unique": max(0, cell.target - len(attempts)),
        "statuses": dict(
            Counter(str(row.get("status")) for row in chosen.values())
        ),
        "retryable_under_cap": len(retryable),
        "malformed": malformed,
    }


def write_state(
    pending: list[Cell],
    running: dict[str, tuple[Cell, subprocess.Popen, object]],
    completed: set[str],
    launches: Counter,
    started_at: str,
) -> None:
    payload = {
        "checked_at": utcnow(),
        "started_at": started_at,
        "max_parallel_weight": int(os.environ.get("MAX_PARALLEL_WEIGHT", "30")),
        "pending": [cell.cell_id for cell in pending],
        "running": {
            cell_id: {
                "pid": proc.pid,
                "concurrency": cell.concurrency,
                "launches": launches[cell_id],
            }
            for cell_id, (cell, proc, _) in running.items()
        },
        "completed": sorted(completed),
        "cells": {cell.cell_id: receipt_state(cell) for cell in CELLS},
    }
    temp = STATE_PATH.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    os.replace(temp, STATE_PATH)


def launch(cell: Cell, launches: Counter) -> tuple[subprocess.Popen, object]:
    log_path = CELL_LOG_DIR / f"{cell.cell_id}.log"
    log_handle = log_path.open("a", buffering=1)
    print(
        f"[{utcnow()}] LAUNCH {cell.cell_id} attempt={launches[cell.cell_id] + 1}",
        file=log_handle,
        flush=True,
    )
    cmd = [
        sys.executable,
        "scripts/phase4a_runner.py",
        "--dataset",
        cell.dataset,
        "--agent",
        cell.agent,
        "--backbone",
        cell.backbone,
        "--n",
        str(cell.target),
        "--out",
        str(OUT_DIR / cell.filename),
        "--concurrency",
        str(cell.concurrency),
        "--resume-statuses",
        "ok,skipped,parser_error",
        "--max-attempts-per-case",
        "2",
        "--timeout_s",
        "900",
    ]
    env = dict(os.environ)
    if cell.wire_model:
        env["MAIDXO_MODEL_OVERRIDE"] = cell.wire_model
    proc = subprocess.Popen(
        cmd,
        cwd=ROOT,
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    launches[cell.cell_id] += 1
    return proc, log_handle


def main() -> int:
    os.chdir(ROOT)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    CELL_LOG_DIR.mkdir(parents=True, exist_ok=True)
    load_dotenv()
    os.environ.setdefault(
        "LLM_GATEWAY_URL", "https://aihubmix.com/v1/chat/completions"
    )
    os.environ.setdefault("LLM_GATEWAY_KEY_ENV", "AIHUBMIX_API_KEY")
    if not os.environ.get(os.environ["LLM_GATEWAY_KEY_ENV"]):
        raise RuntimeError("configured gateway key is missing")
    gateway_preflight()

    max_weight = int(os.environ.get("MAX_PARALLEL_WEIGHT", "30"))
    started_at = utcnow()
    pending = list(CELLS)
    running: dict[str, tuple[Cell, subprocess.Popen, object]] = {}
    completed: set[str] = set()
    launches: Counter = Counter()
    stopping = False

    def request_stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    while pending or running:
        for cell_id, (cell, proc, log_handle) in list(running.items()):
            rc = proc.poll()
            if rc is None:
                continue
            log_handle.close()
            del running[cell_id]
            state = receipt_state(cell)
            if (
                rc == 0
                and state["unique"] >= cell.target
                and state["retryable_under_cap"] == 0
                and state["malformed"] == 0
            ):
                completed.add(cell_id)
            elif launches[cell_id] < 3:
                pending.append(cell)
            else:
                print(
                    f"[fatal] {cell_id} exhausted supervisor launches: "
                    f"rc={rc} state={state}",
                    file=sys.stderr,
                )
                write_state(
                    pending, running, completed, launches, started_at
                )
                return 2

        if stopping:
            for cell, proc, log_handle in running.values():
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                log_handle.close()
            write_state(pending, running, completed, launches, started_at)
            return 130

        used = sum(cell.concurrency for cell, _, _ in running.values())
        deeprare_running = any(
            cell.agent == "deeprare" for cell, _, _ in running.values()
        )
        launched_any = True
        while launched_any:
            launched_any = False
            for index, cell in enumerate(pending):
                state = receipt_state(cell)
                if (
                    state["unique"] >= cell.target
                    and state["retryable_under_cap"] == 0
                    and state["malformed"] == 0
                ):
                    completed.add(cell.cell_id)
                    pending.pop(index)
                    launched_any = True
                    break
                if used + cell.concurrency > max_weight:
                    continue
                if cell.agent == "deeprare" and deeprare_running:
                    continue
                proc, handle = launch(cell, launches)
                running[cell.cell_id] = (cell, proc, handle)
                used += cell.concurrency
                deeprare_running = deeprare_running or cell.agent == "deeprare"
                pending.pop(index)
                launched_any = True
                break

        write_state(pending, running, completed, launches, started_at)
        time.sleep(15)

    write_state(pending, running, completed, launches, started_at)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
