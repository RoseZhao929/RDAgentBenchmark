"""Score the BEFORE (leaked) vs AFTER (de-leaked) bare-LLM comparison on the
same frozen 416 case set, across all 4 paper backbones.

Score-ONLY (no LLM calls). Reuses score_mimic_note_matrix helpers verbatim so
the denominator (416, failures = miss), matching (gold_hit_with_crossmap),
dedupe (prefer-ok), and bootstrap CI are IDENTICAL to the agent matrix.

  * AFTER  = llm_control on the de-leaked probe:
             data/round2/phase4a_mimic_note/predictions_mimic_note_llm_control_<suf>.jsonl
  * BEFORE = llm_control on the LEAKED variant (full note, no truncation/mask,
             SAME 416 case_ids):
             data/round2/phase4a_mimic_note_leaked/predictions_mimic_note_leaked_llm_control_<suf>.jsonl

Gold is the same for both (evaluation_only in note_eval_hpo_line_v1.jsonl); the
leaked file carries the identical case_ids by construction (built with
build_mimic_note_deleaked.py --leaked --restrict-to note_eval_hpo_line_v1.jsonl).

Emits a JSON manifest + markdown tables. DUA-safe (no raw MIMIC text).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.score_mimic_note_matrix import (  # noqa: E402
    BACKBONES,
    load_gold,
    score_cell,
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--after-dir", default="data/round2/phase4a_mimic_note")
    ap.add_argument("--before-dir", default="data/round2/phase4a_mimic_note_leaked")
    ap.add_argument("--gold", default="data/mimic_iv_rd_slice/note_eval_hpo_line_v1.jsonl")
    ap.add_argument("--out", default="audit_frozen/mimic_note_experiment/before_after_scores.json")
    args = ap.parse_args()

    gold = load_gold(args.gold)
    print(f"[gold] {len(gold)} cases from {args.gold}", file=sys.stderr)

    manifest: dict = {
        "n_gold": len(gold),
        "gold_path": args.gold,
        "case_set": "note_eval_hpo_line_v1 (416)",
        "before": {"desc": "leaked: full note, no truncation/mask", "dir": args.before_dir, "cells": {}},
        "after": {"desc": "de-leaked: presentation-span + gold-name mask", "dir": args.after_dir, "cells": {}},
    }

    for suf, disp in BACKBONES:
        after_path = os.path.join(args.after_dir, f"predictions_mimic_note_llm_control_{suf}.jsonl")
        before_path = os.path.join(args.before_dir, f"predictions_mimic_note_leaked_llm_control_{suf}.jsonl")
        manifest["after"]["cells"][disp] = score_cell(after_path, gold)
        manifest["before"]["cells"][disp] = score_cell(before_path, gold)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(manifest, f, indent=2)

    disps = [d for _, d in BACKBONES]

    def cell_str(c):
        if c is None:
            return "—"
        lo, hi = c["R1_ci95"]
        return f"{c['micro_R1']:.3f} [{lo:.3f},{hi:.3f}]"

    print(f"\n## MIMIC-note 416 — bare-LLM (llm_control) BEFORE vs AFTER de-leak · micro R@1 (hits/{len(gold)}), 95% CI\n")
    print("| backbone | BEFORE (leaked) | AFTER (de-leaked) | Δ absolute | Δ relative |")
    print("|---|---|---|---|---|")
    for _, disp in BACKBONES:
        b = manifest["before"]["cells"][disp]
        a = manifest["after"]["cells"][disp]
        if b is None or a is None:
            print(f"| {disp} | {cell_str(b)} | {cell_str(a)} | — | — |")
            continue
        d_abs = b["micro_R1"] - a["micro_R1"]
        d_rel = (d_abs / b["micro_R1"] * 100) if b["micro_R1"] else 0.0
        print(f"| {disp} | {cell_str(b)} | {cell_str(a)} | -{d_abs:.3f} | -{d_rel:.0f}% |")

    print(f"\n## macro R@1 + status (denominator {len(gold)})\n")
    print("| backbone | BEFORE micro/macro | AFTER micro/macro | BEFORE ok | AFTER ok |")
    print("|---|---|---|---|---|")
    for _, disp in BACKBONES:
        b = manifest["before"]["cells"][disp]
        a = manifest["after"]["cells"][disp]
        bs = f"{b['micro_R1']:.3f}/{b['macro_R1']:.3f}" if b else "—"
        as_ = f"{a['micro_R1']:.3f}/{a['macro_R1']:.3f}" if a else "—"
        bok = b["n_ok"] if b else "—"
        aok = a["n_ok"] if a else "—"
        print(f"| {disp} | {bs} | {as_} | {bok} | {aok} |")

    print(f"\n[written] {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
