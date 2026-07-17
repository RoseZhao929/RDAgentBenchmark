"""Phase 4a single (adapter, backbone) controller — loops 4 datasets sequentially.

Designed to be invoked as a background process. One process per (adapter,
backbone) combo. Internally runs:
  for dataset in [phenopacket_store, rarearena_rds, rarebench, mimic_diverse]:
    run phase4a_runner with N=100 (rarebench 25/split×4)

Output: data/round2/phase4a/predictions_<dataset>_<adapter>_<backbone>.jsonl

Usage:
  python3 scripts/phase4a_cell_runner.py --adapter mdagents \
      --backbone openrouter/google/gemini-3-flash-preview-20251217
"""

from __future__ import annotations

import argparse, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--adapter", required=True)
    p.add_argument("--backbone", required=True)
    p.add_argument("--datasets", default="phenopacket_store,rarearena_rds,rarebench,mimic_diverse")
    p.add_argument("--n", type=int, default=100)
    p.add_argument("--out_dir", default="data/round2/phase4a")
    args = p.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    bb_label = args.backbone.removeprefix("openrouter/").replace("/", "_")
    for dataset in args.datasets.split(","):
        dataset = dataset.strip()
        out_path = out_dir / f"predictions_{dataset}_{args.adapter}_{bb_label}.jsonl"
        print(f"\n[p4a-cell] === {dataset} × {args.adapter} × {bb_label} ===", flush=True)
        t0 = time.time()
        # Use subprocess so each dataset is isolated (in case one crashes)
        import subprocess
        runner = Path(__file__).parent / "phase4a_runner.py"
        cmd = [sys.executable, str(runner),
               "--dataset", dataset,
               "--agent", args.adapter,
               "--backbone", args.backbone,
               "--n", str(args.n),
               "--out", str(out_path)]
        try:
            proc = subprocess.run(cmd, check=False)
            print(f"[p4a-cell] {dataset} done in {int(time.time()-t0)}s rc={proc.returncode}", flush=True)
        except Exception as e:
            print(f"[p4a-cell] {dataset} EXC: {e}", flush=True)


if __name__ == "__main__":
    main()
