"""Post-run sanity check: verify a batch of predictions has diverse top-1.

Meta-lesson from Retrospective #2 (2026-05-15): DeepRare wrote 50 cases all
returning the same top-1 "Metachondromatosis" (first-case-leak bug). A simple
"unique-top-1-count" check would have caught this immediately.

This script reads a predictions JSONL and for each agent reports:
- N cases
- N unique top-1 values (after lowercase/strip normalization)
- Diversity ratio = unique / N
- Flags any agent with diversity < 0.30 as SUSPICIOUS

Usage:
    python3 scripts/sanity_check_diversity.py data/round2/phase0/predictions_v2.jsonl
    python3 scripts/sanity_check_diversity.py data/round2/phase0/predictions_v3.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


def normalize(s: str) -> str:
    return (s or "").strip().lower()[:120]


def audit(path: Path, threshold: float = 0.30) -> dict:
    by_agent_top1: dict[str, list[str]] = defaultdict(list)
    by_agent_total: Counter = Counter()

    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            agent = r.get("agent_id", "?")
            preds = r.get("ranked_predictions", []) or []
            top1 = preds[0] if preds else "(empty)"
            by_agent_top1[agent].append(normalize(top1))
            by_agent_total[agent] += 1

    rows = []
    flags = []
    for agent in sorted(by_agent_top1):
        tops = by_agent_top1[agent]
        n = len(tops)
        unique = len(set(tops))
        diversity = unique / n if n > 0 else 0.0
        most_common = Counter(tops).most_common(1)[0]
        suspicious = diversity < threshold
        rows.append({
            "agent": agent,
            "n": n,
            "unique_top1": unique,
            "diversity": diversity,
            "most_common_top1": most_common[0][:60],
            "most_common_count": most_common[1],
            "suspicious": suspicious,
        })
        if suspicious:
            flags.append(agent)

    return {"rows": rows, "flags": flags, "threshold": threshold,
            "input": str(path)}


def print_report(result: dict) -> None:
    print(f"\n=== sanity_check_diversity ({result['input']}) ===")
    print(f"Threshold for flagging: diversity < {result['threshold']:.0%}")
    print(f"\n{'agent':15s} {'n':>4} {'uniq':>5} {'div':>6} {'most_common_top1':<62} {'×':>5}")
    print("-" * 105)
    for row in result["rows"]:
        flag = "🚨" if row["suspicious"] else "  "
        print(f"{flag} {row['agent']:13s} {row['n']:>4} {row['unique_top1']:>5} "
              f"{row['diversity']:>6.0%} {row['most_common_top1']:<62} "
              f"×{row['most_common_count']:>4}")
    if result["flags"]:
        print(f"\n🚨 FLAGGED AGENTS (likely bug): {result['flags']}")
        print("→ Inspect raw_response_excerpt of first-flagged agent's logs.")
        sys.exit(1)
    else:
        print("\n✅ all agents pass diversity check")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("path", type=Path,
                   help="Path to predictions JSONL")
    p.add_argument("--threshold", type=float, default=0.30,
                   help="Diversity threshold (default 0.30)")
    args = p.parse_args()

    result = audit(args.path, threshold=args.threshold)
    print_report(result)
