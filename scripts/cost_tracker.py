"""Cost tracker — sum cost_usd from all phase4a predictions, broken down by
backbone. Use this to monitor cost trajectory per feedback_cost_discipline.

Usage: python3 scripts/cost_tracker.py [--budget 360]
"""
from __future__ import annotations
import argparse
import glob
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path("/Users/yutianzhao/Desktop/RDAgentBenchmark")
PHASE4A = ROOT / "data/round2/phase4a"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=360.0,
                    help="cap to compare against (per memory cost discipline)")
    args = ap.parse_args()

    by_bb = defaultdict(lambda: {"n_ok": 0, "n_err": 0, "cost": 0.0, "files": 0})
    total_files = 0
    for p in sorted(glob.glob(str(PHASE4A / "predictions_*.jsonl"))):
        fn = os.path.basename(p).replace("predictions_", "").replace(".jsonl", "")
        bb = "other"
        for k in ("gemini", "v4-pro", "v4-flash", "gpt-5", "lirical", "vc_rdagent-offline"):
            if k in fn:
                bb = k
                break
        total_files += 1
        by_bb[bb]["files"] += 1
        # dedupe by case_id, prefer ok
        best = {}
        try:
            with open(p) as f:
                for line in f:
                    try:
                        r = json.loads(line)
                    except Exception:
                        continue
                    cid = r.get("case_id")
                    if cid is None:
                        continue
                    prev = best.get(cid)
                    if prev is None or (r.get("status") == "ok" and prev.get("status") != "ok"):
                        best[cid] = r
        except FileNotFoundError:
            continue
        for r in best.values():
            if r.get("status") == "ok":
                by_bb[bb]["n_ok"] += 1
            else:
                by_bb[bb]["n_err"] += 1
            by_bb[bb]["cost"] += (r.get("cost", {}) or {}).get("cost_usd", 0) or 0

    total_cost = sum(d["cost"] for d in by_bb.values())
    total_ok = sum(d["n_ok"] for d in by_bb.values())
    total_err = sum(d["n_err"] for d in by_bb.values())

    print(f"\n=== Cost Tracker — {total_files} prediction files ===\n")
    print(f"{'Backbone':<20} {'Files':>5} {'OK':>7} {'ERR':>5} {'Cost USD':>11}")
    print("-" * 53)
    for bb, d in sorted(by_bb.items(), key=lambda x: -x[1]["cost"]):
        print(f"{bb:<20} {d['files']:>5} {d['n_ok']:>7} {d['n_err']:>5} ${d['cost']:>9.2f}")
    print("-" * 53)
    print(f"{'TOTAL':<20} {total_files:>5} {total_ok:>7} {total_err:>5} ${total_cost:>9.2f}")
    pct = (total_cost / args.budget) * 100 if args.budget else 0
    bar = "█" * int(pct / 4) + "░" * (25 - int(pct / 4))
    print(f"\nBudget: ${args.budget:.0f} | Used: ${total_cost:.2f} ({pct:.1f}%)")
    print(f"[{bar}]")
    if total_cost > args.budget:
        print("⚠️  OVER BUDGET — stop and confirm with user (feedback_cost_discipline)")
    elif pct > 70:
        print("🟡 Approaching budget cap (>70%) — slow down before launching more cells")


if __name__ == "__main__":
    os.chdir(ROOT)
    main()
