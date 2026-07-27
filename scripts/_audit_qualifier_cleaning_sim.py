"""READ-ONLY audit: quantify the impact of 'qualifier cleaning' on the 24-cell
matrix R@1, to decide whether the parenthetical/qualifier matching gap is a
scoring artifact that inflates the LLM-vs-agent gap.

NO writes to production data/scorer. NO LLM calls. Reuses the EXACT scorer
dedupe + matcher. For each prediction that is a plain NL name (not an ID),
we ALSO try a cleaned variant:
  - strip a trailing parenthetical  "... (qualifier)"
  - cut at the first " — "/" – "/" - "/":" separator
  - strip markdown ** __ `
A case counts as a "cleaned hit" if EITHER the raw preds[0] OR its cleaned
form matches gold. This is an UPPER-BOUND on what a rank0-cleaning fix recovers.

Prints per-cell raw R@1 vs cleaned R@1, and the LLM-row vs agent-row deltas.
"""
from __future__ import annotations
import json, os, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.canonical_case import GoldLabel
from harness.metrics.cross_map import gold_hit_with_crossmap
from scripts.score_mimic_note_matrix import dedupe_prefer_ok, load_gold, AGENTS, BACKBONES

PREDS_DIR = "data/round2/phase4a_mimic_note"
GOLD = "data/mimic_iv_rd_slice/note_eval_hpo_line_v1.jsonl"


def clean_name(s: str) -> str:
    if not s:
        return s
    s = re.sub(r"(\*\*|__|`)", "", s)
    for sep in (" — ", " – ", " - ", ":"):
        if sep in s:
            s = s.split(sep, 1)[0]
            break
    # strip trailing parenthetical qualifier(s)
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s)
    return s.rstrip(":.;,").strip()


def hit_raw(pred: str, g: GoldLabel) -> bool:
    return bool(pred and gold_hit_with_crossmap(pred, g))


def hit_cleaned(pred: str, g: GoldLabel) -> bool:
    if not pred:
        return False
    if gold_hit_with_crossmap(pred, g):
        return True
    # only clean plain NL names (leave IDs untouched)
    if pred.strip().split(":")[0] in ("ORPHA", "OMIM", "CCRD", "HP"):
        return False
    c = clean_name(pred)
    if c and c.lower() != pred.strip().lower():
        return gold_hit_with_crossmap(c, g)
    return False


def main() -> None:
    gold = load_gold(GOLD)
    n = len(gold)
    rows = {}
    for agent in AGENTS:
        for suf, disp in BACKBONES:
            path = os.path.join(PREDS_DIR, f"predictions_mimic_note_{agent}_{suf}.jsonl")
            if not os.path.exists(path):
                rows[(agent, disp)] = None
                continue
            recs = dedupe_prefer_ok(path)
            raw = cln = 0
            for cid, g in gold.items():
                r = recs.get(cid)
                preds = (r or {}).get("ranked_predictions") or []
                p0 = preds[0] if preds else None
                if hit_raw(p0, g):
                    raw += 1
                if hit_cleaned(p0, g):
                    cln += 1
            rows[(agent, disp)] = (raw, cln, len(recs))
            print(f"  scored {agent:12} x {disp:16} raw={raw:3} cleaned={cln:3} present={len(recs)}",
                  file=sys.stderr)

    disps = [d for _, d in BACKBONES]
    print(f"\n## Qualifier-cleaning impact on R@1 (denom {n}) — raw -> cleaned (Δhits)\n")
    print("| agent | " + " | ".join(disps) + " |")
    print("|" + "---|" * (len(disps) + 1))
    for agent in AGENTS:
        cells = []
        for _, disp in BACKBONES:
            v = rows[(agent, disp)]
            if v is None:
                cells.append("—")
            else:
                raw, cln, _ = v
                d = cln - raw
                cells.append(f"{raw/n:.3f}->{cln/n:.3f} (+{d})" if d else f"{raw/n:.3f} (=)")
        print(f"| {agent} | " + " | ".join(cells) + " |")

    # LLM row vs agent rows: mean Δ per backbone
    print("\n## Net effect on LLM-vs-agent gap (mean R@1 across the 4 backbones)\n")
    print("| row | raw meanR@1 | cleaned meanR@1 | Δ |")
    print("|---|---|---|---|")
    for agent in AGENTS:
        vs = [rows[(agent, d)] for _, d in BACKBONES if rows[(agent, d)]]
        if not vs:
            continue
        raw_m = sum(x[0] for x in vs) / (len(vs) * n)
        cln_m = sum(x[1] for x in vs) / (len(vs) * n)
        print(f"| {agent} | {raw_m:.3f} | {cln_m:.3f} | +{cln_m-raw_m:.3f} |")


if __name__ == "__main__":
    main()
