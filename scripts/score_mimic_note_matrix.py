"""Score the 6-agent × 4-backbone MIMIC-note (HPO-line 416) agent matrix.

Score-ONLY (no LLM calls): reads the frozen predictions written by
`scripts/phase4a_runner.py --dataset mimic_note` and computes R@1 / R@5 against
the code-derived Orphanet gold in `note_eval_hpo_line_v1.jsonl`.

Policy (matches audit_frozen/recompute_engine.py, honest denominator):
  * Denominator = the frozen 416-case line (N=416), NOT n_ok. Every case that
    is missing, failed, timed out, parser_error'd, or returned an EMPTY ok
    prediction counts as a MISS. No success-only inflation.
  * Matching = harness.metrics.cross_map.gold_hit_with_crossmap (ORPHA/OMIM/CCRD
    cross-map + case-insensitive disease-name + Orphadata fuzzy≥90), reused
    verbatim so agents whose adapter emits NL names (DeepRare) are matched the
    same way as the 2-model probe.
  * Dedupe = one record per case_id, preferring a status==ok record (matches
    recompute_engine.dedupe_cases), so resume-duplicate appends don't double-count.
  * micro R@1 = hits / 416.  macro R@1 = mean over gold diseases of per-disease
    hit-rate (long-tail-robust, same as the 2-model HPO-line report).
  * 95% CI via the exact binomial bootstrap in recompute_engine.

maidxo × openai/gpt-5 is scored honestly (NOT skipped): its low score reflects
a real structured-output protocol collapse, not a timeout. See
scripts/phase4a_runner.py header + memory maidxo-gpt5-protocol-collapse.

Output: prints a markdown table and writes a JSON manifest with per-cell
counts + status breakdown for provenance. NO raw MIMIC text is emitted (only
case_id, gold ORPHA id, counts, rates) — DUA-safe for docs/git.

Usage:
    python3 scripts/score_mimic_note_matrix.py \
        --preds-dir data/round2/phase4a_mimic_note \
        --gold data/mimic_iv_rd_slice/note_eval_hpo_line_v1.jsonl \
        --out audit_frozen/mimic_note_experiment/agent_matrix_scores.json
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.canonical_case import GoldLabel  # noqa: E402
from harness.metrics.cross_map import gold_hit_with_crossmap  # noqa: E402
from audit_frozen.recompute_engine import bootstrap_ci_cases  # noqa: E402

AGENTS = ("llm_control", "medagents", "mdagents", "agentclinic", "deeprare", "maidxo")
# (filename suffix -> display backbone). Suffixes are exactly what phase4a_runner
# emits (note the DOUBLE underscore for v4-pro).
BACKBONES = [
    ("deepseek__deepseek-v4-pro", "deepseek-v4-pro"),
    ("deepseek_deepseek-v4-flash", "deepseek-v4-flash"),
    ("openai_gpt-5", "gpt-5"),
    ("google_gemini-3-flash-preview-20251217", "gemini-3-flash"),
]


def load_gold(path: str) -> dict[str, GoldLabel]:
    gold: dict[str, GoldLabel] = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            ev = r.get("evaluation_only") or {}
            gold[r["case_id"]] = GoldLabel(
                orphanet_id=ev.get("gold_orpha"),
                disease_name=ev.get("gold_disease"),
            )
    return gold


def dedupe_prefer_ok(path: str) -> dict[str, dict]:
    best: dict[str, dict] = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            cid = r.get("case_id")
            if cid is None:
                continue
            prev = best.get(cid)
            if prev is None:
                best[cid] = r
            elif r.get("status") == "ok" and prev.get("status") != "ok":
                best[cid] = r
    return best


def score_cell(preds_path: str, gold: dict[str, GoldLabel]) -> dict | None:
    if not os.path.exists(preds_path):
        return None
    recs = dedupe_prefer_ok(preds_path)
    gold_ids = list(gold.keys())  # the frozen 416-case denominator
    n = len(gold_ids)

    h1_flags: list[int] = []
    h5_hits = 0
    status_ct: Counter = Counter()
    empty_ok = 0
    # per-disease for macro
    per_disease_hit: dict[str, list[int]] = defaultdict(list)

    for cid in gold_ids:
        g = gold[cid]
        r = recs.get(cid)
        disease_key = (g.orphanet_id or g.disease_name or cid)
        if r is None:
            status_ct["missing"] += 1
            h1_flags.append(0)
            per_disease_hit[disease_key].append(0)
            continue
        status_ct[r.get("status") or "unknown"] += 1
        preds = r.get("ranked_predictions") or []
        if r.get("status") == "ok" and not preds:
            empty_ok += 1
        hit1 = bool(preds and gold_hit_with_crossmap(preds[0], g))
        hit5 = any(gold_hit_with_crossmap(p, g) for p in preds[:5])
        h1_flags.append(1 if hit1 else 0)
        if hit5:
            h5_hits += 1
        per_disease_hit[disease_key].append(1 if hit1 else 0)

    h1 = sum(h1_flags)
    micro_r1 = h1 / n if n else 0.0
    micro_r5 = h5_hits / n if n else 0.0
    macro_r1 = (
        sum(sum(v) / len(v) for v in per_disease_hit.values()) / len(per_disease_hit)
        if per_disease_hit else 0.0
    )
    lo, hi = bootstrap_ci_cases(h1_flags)
    n_ok = status_ct.get("ok", 0)
    return {
        "n": n,
        "n_present": len(recs),
        "n_ok": n_ok,
        "empty_ok": empty_ok,
        "hits_r1": h1,
        "hits_r5": h5_hits,
        "micro_R1": round(micro_r1, 4),
        "micro_R5": round(micro_r5, 4),
        "macro_R1": round(macro_r1, 4),
        "R1_success_denom": round(h1 / n_ok, 4) if n_ok else None,
        "R1_ci95": [lo, hi],
        "n_diseases": len(per_disease_hit),
        "status": dict(status_ct),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preds-dir", default="data/round2/phase4a_mimic_note")
    ap.add_argument("--gold", default="data/mimic_iv_rd_slice/note_eval_hpo_line_v1.jsonl")
    ap.add_argument("--out", default="audit_frozen/mimic_note_experiment/agent_matrix_scores.json")
    args = ap.parse_args()

    gold = load_gold(args.gold)
    print(f"[gold] loaded {len(gold)} cases from {args.gold}", file=sys.stderr)

    manifest: dict = {"n_gold": len(gold), "gold_path": args.gold, "cells": {}}
    # rows = agents, cols = backbones
    for agent in AGENTS:
        for suf, disp in BACKBONES:
            path = os.path.join(
                args.preds_dir, f"predictions_mimic_note_{agent}_{suf}.jsonl"
            )
            cell = score_cell(path, gold)
            manifest["cells"][f"{agent}|{disp}"] = cell

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(manifest, f, indent=2)

    # ---- markdown tables to stdout ----
    disps = [d for _, d in BACKBONES]
    print(f"\n## MIMIC-note HPO-line agent matrix — micro R@1 (hits / {len(gold)}), 95% CI\n")
    print("| agent | " + " | ".join(disps) + " |")
    print("|" + "---|" * (len(disps) + 1))
    for agent in AGENTS:
        row = [agent]
        for _, disp in BACKBONES:
            c = manifest["cells"][f"{agent}|{disp}"]
            if c is None:
                row.append("—")
            else:
                lo, hi = c["R1_ci95"]
                row.append(f"{c['micro_R1']:.3f} [{lo:.3f},{hi:.3f}]")
        print("| " + " | ".join(row) + " |")

    print(f"\n## micro R@5 / macro R@1\n")
    print("| agent | " + " | ".join(f"{d} R@5 / macro" for d in disps) + " |")
    print("|" + "---|" * (len(disps) + 1))
    for agent in AGENTS:
        row = [agent]
        for _, disp in BACKBONES:
            c = manifest["cells"][f"{agent}|{disp}"]
            row.append("—" if c is None else f"{c['micro_R5']:.3f} / {c['macro_R1']:.3f}")
        print("| " + " | ".join(row) + " |")

    print(f"\n## status breakdown (dedup'd, denominator {len(gold)})\n")
    for agent in AGENTS:
        for _, disp in BACKBONES:
            c = manifest["cells"][f"{agent}|{disp}"]
            if c is None:
                continue
            print(f"- {agent} × {disp}: ok={c['n_ok']} empty_ok={c['empty_ok']} "
                  f"present={c['n_present']}/{c['n']}  status={c['status']}")

    print(f"\n[written] {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
