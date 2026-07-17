"""Backfill cost_usd in existing predictions.jsonl from token counts + price table.

The Mini Pilot Phase 0 left cost=0 in all subprocess-agent predictions because
the adapters didn't call fill_cost. Tokens ARE present, just unpriced.

This script reads the existing JSONL, applies pricing per backbone_id, writes
out a new JSONL with corrected costs. The original file is preserved.

Run: python3 scripts/backfill_costs.py [--input PATH] [--output PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.logging.openrouter_wrapper import get_price


def backfill(input_path: Path, output_path: Path) -> dict:
    stats = {"total": 0, "backfilled": 0, "already_priced": 0, "no_tokens": 0,
             "unknown_model": 0}

    with input_path.open() as f_in, output_path.open("w") as f_out:
        for line in f_in:
            line = line.strip()
            if not line:
                continue
            stats["total"] += 1
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            cost = rec.get("cost", {}) or {}
            pt = cost.get("prompt_tokens", 0) or 0
            ct = cost.get("completion_tokens", 0) or 0
            existing_usd = cost.get("cost_usd", 0.0) or 0.0

            if pt == 0 and ct == 0:
                stats["no_tokens"] += 1
            elif existing_usd > 0:
                stats["already_priced"] += 1
            else:
                # Backfill: strip openrouter/ prefix for get_price
                backbone = rec.get("backbone_id", "") or ""
                p_in, p_out = get_price(backbone)
                if p_in == 0 and p_out == 0:
                    stats["unknown_model"] += 1
                else:
                    cost["cost_usd"] = (pt * p_in + ct * p_out) / 1_000_000
                    cost["provider"] = cost.get("provider") or "openrouter"
                    rec["cost"] = cost
                    stats["backfilled"] += 1

            f_out.write(json.dumps(rec, ensure_ascii=False) + "\n")

    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",
                        default="data/round2/phase0/predictions.jsonl")
    parser.add_argument("--output",
                        default="data/round2/phase0/predictions_costfilled.jsonl")
    args = parser.parse_args()

    stats = backfill(Path(args.input), Path(args.output))
    print("Backfill stats:")
    for k, v in stats.items():
        print(f"  {k}: {v:,}")
    print(f"\nOutput: {args.output}")

    # Print per-agent cost summary
    import collections
    by_agent = collections.defaultdict(lambda: {"n": 0, "cost": 0.0, "tokens_in": 0, "tokens_out": 0})
    with Path(args.output).open() as f:
        for line in f:
            r = json.loads(line)
            a = r["agent_id"]
            c = r.get("cost", {}) or {}
            by_agent[a]["n"] += 1
            by_agent[a]["cost"] += c.get("cost_usd", 0) or 0
            by_agent[a]["tokens_in"] += c.get("prompt_tokens", 0) or 0
            by_agent[a]["tokens_out"] += c.get("completion_tokens", 0) or 0

    print("\nPer-agent cost summary (post-backfill):")
    print(f"  {'agent':15s}  n   cost($)   tokens_in   tokens_out")
    for a, s in sorted(by_agent.items()):
        print(f"  {a:15s}  {s['n']:3d}  {s['cost']:7.4f}   {s['tokens_in']:>9,}   {s['tokens_out']:>9,}")
