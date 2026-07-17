"""Second MAI-DxO smoke test exercising the panel deliberation path.

`instant` mode short-circuits to no diagnosis (degenerate by design).
This test uses `no_budget` with max_iterations=1 so that one full round of
Hypothesis -> TestChooser -> Challenger -> Stewardship -> Checklist ->
Consensus -> Gatekeeper -> Judge runs end-to-end through OpenRouter.
"""

import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path("/Users/yutianzhao/Desktop/RDAgentBenchmark")
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

assert os.environ.get("OPENROUTER_API_KEY")

from mai_dx import MaiDxOrchestrator

MODEL = "openrouter/google/gemini-3-flash-preview"

INITIAL = (
    "A 7-year-old boy with progressive muscle weakness, calf hypertrophy, "
    "Gower sign positive, and elevated creatine kinase. Maternal uncle died "
    "at 19 from similar disease."
)
FULL = INITIAL + "\nGenetic test: deletion of exons 45-50 of the DMD gene confirmed."
GT = "Duchenne muscular dystrophy"


def main():
    print(f"[smoke-full] model = {MODEL}")
    t0 = time.time()
    orch = MaiDxOrchestrator.create_variant(
        "no_budget",
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
    print(f"[smoke-full] elapsed = {dt:.1f}s")
    print(f"[smoke-full] final_diagnosis = {result.final_diagnosis!r}")
    print(f"[smoke-full] accuracy_score = {result.accuracy_score}")
    print(f"[smoke-full] iterations = {result.iterations}")
    print(f"[smoke-full] total_cost = {result.total_cost}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
