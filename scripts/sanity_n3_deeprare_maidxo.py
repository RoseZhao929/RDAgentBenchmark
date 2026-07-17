"""N=3 sanity check for the 2026-05-16 DeepRare + maidxo adapter fixes.

Runs deeprare and maidxo on 3 distinct cases from the same stratified sample
that the Phase 0 pilot uses (seed=42, n_per_layer=25 → 50 cases). We pick the
first 3 cases and print top-1 for each agent.

Pass criteria:
  - deeprare top-1 differs across all 3 cases (first-case-leak gone)
  - maidxo top-1 is a disease name (no vitals / no "Unable to establish ...")

Usage:
    python3 scripts/sanity_n3_deeprare_maidxo.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def load_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def main() -> int:
    load_env()
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("OPENROUTER_API_KEY not set", file=sys.stderr)
        return 2

    # Reuse the exact case-selection logic of mini_round2_pilot.
    from scripts.mini_round2_pilot import build_sample
    from harness.agents import DeepRareAdapter, MaiDxOAdapter

    cases = build_sample(seed=42, n_per_layer=25)
    sample = cases[:3]
    print(f"Sanity check on {len(sample)} cases:")
    for c in sample:
        print(f"  - {c.case_id}  gold={c.gold_label.disease_name}")

    backbone = os.environ.get(
        "PHASE0_BACKBONE",
        "openrouter/google/gemini-3-flash-preview-20251217",
    )

    results: dict[str, list[tuple[str, str, str]]] = {"deeprare": [], "maidxo": []}

    print("\n=== DeepRare ===", flush=True)
    dr = DeepRareAdapter(backbone_id=backbone)
    for i, case in enumerate(sample, 1):
        t0 = time.time()
        log = dr.predict(case, pillar="P2_phenotype_ddx", eval_mode="gold_hpo",
                         run_id=f"sanity_n3_dr_{int(time.time())}")
        top1 = log.ranked_predictions[0] if log.ranked_predictions else "NIL"
        elapsed = int(time.time() - t0)
        print(f"  [{i}/3] {case.case_id[:35]:35s}  "
              f"status={log.status:6s}  {elapsed:3d}s  top1={top1!r}",
              flush=True)
        results["deeprare"].append((case.case_id, log.status, top1))

    print("\n=== MaiDxO ===", flush=True)
    mx = MaiDxOAdapter(
        backbone_id=backbone,
        agent_extra={"mode": "no_budget", "max_iterations": 3},
    )
    for i, case in enumerate(sample, 1):
        t0 = time.time()
        log = mx.predict(case, pillar="P2_phenotype_ddx", eval_mode="gold_hpo",
                        run_id=f"sanity_n3_mx_{int(time.time())}")
        top1 = log.ranked_predictions[0] if log.ranked_predictions else "NIL"
        elapsed = int(time.time() - t0)
        print(f"  [{i}/3] {case.case_id[:35]:35s}  "
              f"status={log.status:6s}  {elapsed:3d}s  top1={top1!r}",
              flush=True)
        if log.extra.get("maidxo_noise_filtered"):
            print(f"      noise_filtered: {log.extra['maidxo_noise_filtered']!r}",
                  flush=True)
        results["maidxo"].append((case.case_id, log.status, top1))

    # Verdict
    print("\n=== Verdict ===", flush=True)
    dr_tops = [t for _, _, t in results["deeprare"]]
    dr_unique = len({t.lower() for t in dr_tops if t != "NIL"})
    print(f"DeepRare top-1s: {dr_tops}")
    print(f"  unique: {dr_unique}/{len(dr_tops)}  → "
          f"{'PASS' if dr_unique >= 2 else 'FAIL (likely still leaking)'}")

    NOISE_HINTS = ("mmHg", "bpm", "mg/dL", "SpO2", "unable to establish",
                   "further evaluation", "cannot ")
    mx_tops = [t for _, _, t in results["maidxo"]]
    mx_noise = [t for t in mx_tops
                if any(h.lower() in t.lower() for h in NOISE_HINTS)]
    print(f"MaiDxO top-1s: {mx_tops}")
    print(f"  noise tops: {len(mx_noise)}/{len(mx_tops)}  → "
          f"{'PASS' if not mx_noise else 'FAIL'}")

    ok = dr_unique >= 2 and not mx_noise
    print(f"\nOverall: {'PASS — safe to run 50 case' if ok else 'FAIL — investigate'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
