"""Filter MIMIC-IV slice cases.jsonl to genuinely-rare diseases.

The raw ingest at v1 includes many false positives because ICD codes like G20
(Parkinson's disease) cross-reference to Orphanet entries flagged
"NON RARE IN EUROPE: Parkinson disease". These should be dropped.

Filters:
1. Drop cases whose gold_label.disease_name starts with "NON RARE IN EUROPE"
   (Orphadata's explicit non-rare flag)
2. Optionally keep only Exact match relations (precision over recall)
3. Optionally cap cases per Orphanet ID (diversity)
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Optional


def filter_cases(
    in_path: Path,
    out_path: Path,
    *,
    drop_non_rare_prefix: bool = True,
    only_exact: bool = False,
    cap_per_disease: Optional[int] = None,
) -> dict:
    """Stream-filter cases.jsonl. Returns stats."""
    stats = {
        "input_total": 0,
        "kept": 0,
        "dropped_non_rare": 0,
        "dropped_not_exact": 0,
        "dropped_disease_cap": 0,
    }
    per_disease_count: Counter[str] = Counter()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with in_path.open() as f_in, out_path.open("w") as f_out:
        for line in f_in:
            line = line.strip()
            if not line:
                continue
            stats["input_total"] += 1
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            name = (rec.get("gold_label", {}).get("disease_name") or "").upper()
            if drop_non_rare_prefix and name.startswith("NON RARE IN EUROPE"):
                stats["dropped_non_rare"] += 1
                continue

            rel = rec.get("metadata", {}).get("primary_relation", "")
            if only_exact and rel != "E":
                stats["dropped_not_exact"] += 1
                continue

            orpha = rec.get("gold_label", {}).get("orphanet_id")
            if cap_per_disease and orpha:
                if per_disease_count[orpha] >= cap_per_disease:
                    stats["dropped_disease_cap"] += 1
                    continue
                per_disease_count[orpha] += 1

            f_out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            stats["kept"] += 1

    stats["unique_diseases_in_output"] = len(per_disease_count) if cap_per_disease else None
    return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--in_path", default="data/mimic_iv_rd_slice/cases.jsonl")
    parser.add_argument("--out_path", default="data/mimic_iv_rd_slice/cases_filtered.jsonl")
    parser.add_argument("--only-exact", action="store_true",
                        help="Keep only ICD↔Orphanet Exact-match relation")
    parser.add_argument("--cap-per-disease", type=int, default=None,
                        help="Max cases per Orphanet ID (default: no cap)")
    parser.add_argument("--no-drop-non-rare", action="store_true",
                        help="Keep 'NON RARE IN EUROPE' entries (not recommended)")
    args = parser.parse_args()

    stats = filter_cases(
        Path(args.in_path),
        Path(args.out_path),
        drop_non_rare_prefix=not args.no_drop_non_rare,
        only_exact=args.only_exact,
        cap_per_disease=args.cap_per_disease,
    )
    print("=== Filter stats ===")
    for k, v in stats.items():
        print(f"  {k}: {v:,}" if isinstance(v, int) else f"  {k}: {v}")
    print(f"\nOutput: {args.out_path}")
