"""Merge Phase 0 v1 + v2 + (v3 after bug fix) predictions into a single
final leaderboard, then aggregate.

Inputs(per Retrospective Checkpoint #2):
- `data/round2/phase0/predictions.jsonl`        — v1, 4 agents (mdagents,
                                                    medagents, agentclinic,
                                                    + lirical/vc_rdagent/maidxo
                                                    pre-fix)
- `data/round2/phase0/predictions_v2.jsonl`     — D1/D2/D3 fixed re-run
                                                    (lirical/vc_rdagent/maidxo,
                                                    + DeepRare with bug)
- `data/round2/phase0/predictions_v3.jsonl`     — DeepRare/maidxo bug-fix
                                                    re-run (optional, written
                                                    by subagent if v3 ready)
- `data/sanity_check/results.jsonl`             — llm_control baseline (Gemini
                                                    Flash, 50 case)

Merge policy (newest-wins by file priority v3 > v2 > v1):
- Same (agent_id, case_id) key → keep highest priority
- llm_control comes from sanity_check, joined per case_id where matchable

Output:
- `data/round2/phase0/predictions_final.jsonl`  — deduped merged
- `data/round2/phase0/REPORT_FINAL.md`          — final P0 leaderboard

Usage:
    python3 scripts/merge_phase0_final.py
"""

from __future__ import annotations

import json
import sys
from collections import OrderedDict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.mini_round2_pilot import aggregate_and_report  # noqa: E402

PHASE0_DIR = Path("data/round2/phase0")
SANITY_PATH = Path("data/sanity_check/results.jsonl")


def merge_files(paths_priority_low_to_high: list[Path]) -> list[str]:
    """Keep the last-occurrence (highest priority) for each (agent, case)."""
    seen: OrderedDict[tuple[str, str], str] = OrderedDict()

    for path in paths_priority_low_to_high:
        if not path.exists():
            print(f"  (skip missing) {path.name}")
            continue
        n_added = 0
        n_overwritten = 0
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                key = (r["agent_id"], r["case_id"])
                if key in seen:
                    n_overwritten += 1
                else:
                    n_added += 1
                seen[key] = line
        print(f"  {path.name}: +{n_added} new, {n_overwritten} overwritten")

    return list(seen.values())


def main():
    print("[merge_phase0_final] Loading source files (priority v1 < v2 < v3):")

    # Order: lowest priority first, so later overwrites earlier
    sources = [
        PHASE0_DIR / "predictions.jsonl",       # v1
        PHASE0_DIR / "predictions_v2.jsonl",    # v2 (D1/D2/D3 fixes)
        PHASE0_DIR / "predictions_v3.jsonl",    # v3 (DeepRare/maidxo fix, may be absent)
    ]

    merged = merge_files(sources)

    # Add llm_control baseline from sanity check (Gemini Flash only, P2)
    if SANITY_PATH.exists():
        n_baseline = 0
        with SANITY_PATH.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("agent_id") == "llm_control" and \
                   r.get("backbone_id", "").endswith("gemini-3-flash-preview"):
                    merged.append(line)
                    n_baseline += 1
        print(f"  sanity_check (llm_control Gemini Flash): +{n_baseline}")

    out_path = PHASE0_DIR / "predictions_final.jsonl"
    with out_path.open("w") as f:
        for line in merged:
            f.write(line + "\n")
    print(f"\nMerged → {out_path} ({len(merged)} total rows)")

    # Aggregate
    report_path = PHASE0_DIR / "REPORT_FINAL.md"
    print(f"\nAggregating → {report_path}")
    aggregate_and_report(out_path, report_path)


if __name__ == "__main__":
    main()
