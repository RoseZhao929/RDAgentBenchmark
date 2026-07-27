"""Balance the de-leaked MIMIC-note eval subset to at most N cases per disease.

Input is the prior-known-filtered subset (note_eval_subset_v2.jsonl). For each
gold Orphanet id we keep the first ``--cap`` cases in ascending hadm_id order
(deterministic), so no single high-frequency disease (e.g. hepatocellular
carcinoma) dominates the aggregate metric. All record fields — including the
A/B markers ``history_undeterminable`` / ``prior_known_flag`` — are preserved.

No LLM calls, no fabrication, deterministic. Output stays under gitignored
data/ (credentialed). Only the printed manifest is safe to copy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def build(in_path: Path, out_path: Path | None, cap: int) -> dict[str, Any]:
    rows = [json.loads(l) for l in in_path.open() if l.strip()]
    by_disease: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_disease[r["evaluation_only"]["gold_orpha"]].append(r)

    kept: list[dict] = []
    for oid in by_disease:
        # deterministic: ascending hadm_id, take first `cap`
        for r in sorted(by_disease[oid], key=lambda x: x["hadm_id"])[:cap]:
            kept.append(r)
    kept.sort(key=lambda x: x["hadm_id"])  # stable global order

    digest = hashlib.sha256()
    writer = out_path.open("w") if out_path else None
    try:
        for r in kept:
            line = json.dumps(r, ensure_ascii=False)
            digest.update(line.encode("utf-8"))
            if writer:
                writer.write(line + "\n")
    finally:
        if writer:
            writer.close()

    n_a = sum(1 for r in kept if r.get("history_undeterminable"))
    return {
        "input_n": len(rows),
        "cap_per_disease": cap,
        "n_final": len(kept),
        "n_distinct_diseases": len(by_disease),
        "A_history_undeterminable": n_a,
        "B_verbatim_masked": len(kept) - n_a,
        "output": str(out_path) if out_path else None,
        "output_sha256": digest.hexdigest(),
        "task_version": "mimic-note-eval-cap-v2",
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path,
                   default=Path("data/mimic_iv_rd_slice/note_eval_subset_v2.jsonl"))
    p.add_argument("--output", type=Path,
                   help="Credentialed JSONL output (keep under gitignored data/).")
    p.add_argument("--cap", type=int, default=10)
    args = p.parse_args()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
    print(json.dumps(build(args.input, args.output, args.cap),
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
