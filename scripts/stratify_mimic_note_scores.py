"""Compute A/B/all stratified R@1 & R@5 for a MIMIC-note prediction file.

Joins a predictions_*.jsonl (recompute-engine receipts, with _hit1/_hit5
already computed at scoring time) against the cap10 subset to recover the
A/B class of each case:

  * A class -> history_undeterminable == True  (gold name never appeared
    verbatim; cleanest, requires real reasoning)
  * B class -> history_undeterminable == False (gold name appeared & masked;
    the disease was mentioned in text -> softer leak, more suspect)

Denominator = attempted (failures/parser errors kept as misses), matching
audit_frozen/recompute_engine.py. No LLM calls, no fabrication.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_class(subset: Path) -> dict[str, str]:
    cls: dict[str, str] = {}
    for line in subset.open():
        if not line.strip():
            continue
        r = json.loads(line)
        cls[r["case_id"]] = "A" if r.get("history_undeterminable") else "B"
    return cls


def strat(preds_path: Path, cls: dict[str, str]) -> dict:
    buckets = {"all": [], "A": [], "B": []}
    for line in preds_path.open():
        if not line.strip():
            continue
        p = json.loads(line)
        cid = p["case_id"]
        # attempted denominator: every receipt counts; a failed/parser-error
        # receipt has no _hit1 -> treated as a miss (0).
        hit1 = 1 if p.get("_hit1") else 0
        hit5 = 1 if p.get("_hit5") else 0
        rec = (hit1, hit5, p.get("status"))
        buckets["all"].append(rec)
        c = cls.get(cid)
        if c:
            buckets[c].append(rec)

    out = {}
    for k, rows in buckets.items():
        n = len(rows)
        n_ok = sum(1 for _, _, s in rows if s == "ok")
        h1 = sum(a for a, _, _ in rows)
        h5 = sum(b for _, b, _ in rows)
        out[k] = {
            "n": n,
            "n_ok": n_ok,
            "R@1": round(h1 / n, 4) if n else None,
            "R@5": round(h5 / n, 4) if n else None,
            "hits1": h1,
            "hits5": h5,
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preds", type=Path, required=True)
    ap.add_argument("--subset", type=Path,
                    default=Path("data/mimic_iv_rd_slice/note_eval_cap10_v2.jsonl"))
    ap.add_argument("--label", default="")
    args = ap.parse_args()
    cls = load_class(args.subset)
    res = strat(args.preds, cls)
    print(json.dumps({"label": args.label, "preds": str(args.preds),
                      "strata": res}, indent=2))


if __name__ == "__main__":
    main()
