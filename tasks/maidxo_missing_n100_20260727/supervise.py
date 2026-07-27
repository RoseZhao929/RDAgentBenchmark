#!/usr/bin/env python3
"""Keep the resumable MAI-DxO pilot alive and audit it once per minute."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent
ROOT = TASK_DIR.parents[1]
LOG_DIR = ROOT / "logs" / "maidxo_missing_n100_20260727"
SUP_LOG = LOG_DIR / "supervisor.log"
CHECK_INTERVAL = 60
STALL_SECONDS = 25 * 60


def log(message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat()
    with SUP_LOG.open("a") as handle:
        handle.write(f"[{stamp}] {message}\n")


def free_percent() -> int:
    try:
        result = subprocess.run(
            ["memory_pressure"], capture_output=True, text=True, timeout=10
        )
        match = re.search(r"System-wide memory free percentage:\s*(\d+)%", result.stdout)
        return int(match.group(1)) if match else 30
    except Exception:
        return 30


def choose_concurrency() -> int:
    free = free_percent()
    concurrency = 4 if free >= 35 else 3 if free >= 20 else 2
    log(f"memory_free={free}% cell_concurrency={concurrency} total_max={concurrency * 2}")
    return concurrency


def monitor() -> tuple[int, dict]:
    result = subprocess.run(
        [sys.executable, str(TASK_DIR / "monitor.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    try:
        payload = json.loads(result.stdout.strip().splitlines()[-1])
    except Exception:
        payload = {"critical": ["monitor output could not be parsed"], "cells": {}}
        result = subprocess.CompletedProcess(result.args, 2)
    log(
        f"progress={payload.get('settled_total', 0)}/500 "
        f"critical={payload.get('critical', [])}"
    )
    return result.returncode, payload


def stop_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=15)
    except Exception:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def main() -> int:
    while True:
        rc, payload = monitor()
        if rc == 2:
            log("critical audit failure before launch; supervisor stopping")
            return 2
        if payload.get("settled_total") == 500:
            log("all 500 case-cells settled")
            subprocess.run([sys.executable, str(TASK_DIR / "summarize.py")], cwd=ROOT)
            return 0

        env = os.environ.copy()
        env["CELL_CONCURRENCY"] = str(choose_concurrency())
        proc = subprocess.Popen(
            ["bash", str(TASK_DIR / "run.sh")],
            cwd=ROOT,
            env=env,
            start_new_session=True,
        )
        log(f"launched orchestrator pid={proc.pid}")
        last_progress = int(payload.get("settled_total", 0))
        last_progress_at = time.monotonic()

        while proc.poll() is None:
            time.sleep(CHECK_INTERVAL)
            rc, payload = monitor()
            progress = int(payload.get("settled_total", 0))
            if progress > last_progress:
                last_progress = progress
                last_progress_at = time.monotonic()
            is_stalled = time.monotonic() - last_progress_at > STALL_SECONDS
            if rc == 2 or is_stalled:
                reason = "critical audit failure" if rc == 2 else "no receipt progress for 25m"
                log(f"{reason}; terminating orchestrator group")
                stop_group(proc)
                if rc == 2:
                    return 2
                break

        return_code = proc.poll()
        log(f"orchestrator exit={return_code}; rechecking in 30s")
        time.sleep(30)


if __name__ == "__main__":
    raise SystemExit(main())
