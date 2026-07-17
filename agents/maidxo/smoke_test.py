"""Smoke test for MAI-DxO community port using OpenRouter.

Loads OPENROUTER_API_KEY from project .env, builds an `instant`-mode
orchestrator (1 LLM call), and runs against a tiny test case.
"""

import os
import sys
import time
from pathlib import Path

# Load .env from project root
PROJECT_ROOT = Path("/Users/yutianzhao/Desktop/RDAgentBenchmark")
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

assert os.environ.get("OPENROUTER_API_KEY"), "OPENROUTER_API_KEY missing in .env"

# LiteLLM picks up OPENROUTER_API_KEY automatically when model is openrouter/*
# We can also set OPENAI_API_BASE manually but LiteLLM has built-in support.

from mai_dx import MaiDxOrchestrator

MODEL = "openrouter/google/gemini-3-flash-preview"

INITIAL = (
    "A 7-year-old boy with progressive muscle weakness, calf hypertrophy, "
    "and elevated creatine kinase. Has a maternal uncle who died at age 19 "
    "from a similar muscle disease."
)
FULL = (
    INITIAL
    + "\nGower sign positive. Genetic testing: deletion of exons 45-50 of the DMD gene."
)
GT = "Duchenne muscular dystrophy"


def main():
    print(f"[smoke] model = {MODEL}")
    t0 = time.time()
    orch = MaiDxOrchestrator.create_variant(
        "instant",
        model_name=MODEL,
        max_iterations=1,
        request_delay=0.0,
    )
    result = orch.run(
        initial_case_info=INITIAL,
        full_case_details=FULL,
        ground_truth_diagnosis=GT,
    )
    dt = time.time() - t0
    print(f"[smoke] elapsed = {dt:.1f}s")
    print(f"[smoke] final_diagnosis = {result.final_diagnosis!r}")
    print(f"[smoke] accuracy_score = {result.accuracy_score}")
    print(f"[smoke] iterations = {result.iterations}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
