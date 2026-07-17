"""H10 — faithfulness-rank vs accuracy-rank decoupling (Spearman ρ < 0.5).

Per (agent, case) judged trace: correlate the judge's faithfulness score (1-5)
with whether the agent's top-1 diagnosis actually hit gold (0/1). H10 predicts
ρ < 0.5 (a faithful-looking trace does not imply a correct answer).

Reads the expanded P5 judge files (v1 Gemini judge, v2 Claude judge) and reports
per-judge + pooled ρ with a bootstrap-free normal-approx one-sided p for ρ<0.5.

Usage: python3 scripts/h10_faithfulness_accuracy.py [judge_file ...]
Default reads the N=50 expanded files if present, else the N=10 pilot.
"""
from __future__ import annotations
import json, sys, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scipy import stats
from harness.metrics.cross_map import gold_hit_with_crossmap
from scripts.regen_receipts_and_figures import load_gold_map

DEFAULT = [
    "data/round2/phase1/p5_judge_scores_v1_n50.jsonl",
    "data/round2/phase1/p5_judge_scores_v2_n50.jsonl",
]
FALLBACK = [
    "data/round2/phase1/p5_judge_scores_v1.jsonl",
    "data/round2/phase1/p5_judge_scores_v2.jsonl",
]


def pairs(path, gm):
    fh, hit = [], []
    for line in open(path):
        r = json.loads(line)
        s = r.get("scores", {}) or {}
        fv = s.get("faithfulness")
        if not isinstance(fv, (int, float)):
            continue
        g = gm.get(r.get("case_id"), (None, None))[1]
        ranked = r.get("ranked", [])
        if not g or not ranked:
            continue
        fh.append(fv)
        hit.append(1 if gold_hit_with_crossmap(ranked[0], g) else 0)
    return fh, hit


def main():
    files = sys.argv[1:] or [f for f in DEFAULT if Path(f).exists()] or FALLBACK
    gm = load_gold_map()
    md = ["# H10 — faithfulness vs accuracy decoupling (Spearman ρ < 0.5)\n"]
    all_fh, all_hit = [], []
    for f in files:
        if not Path(f).exists():
            continue
        fh, hit = pairs(f, gm)
        all_fh += fh; all_hit += hit
        if len(fh) > 2:
            rho, p = stats.spearmanr(fh, hit)
            md.append(f"- `{Path(f).name}`: n={len(fh)} ρ={rho:.3f} (two-sided p={p:.3g})")
    n = len(all_fh)
    rho, p2 = stats.spearmanr(all_fh, all_hit)
    # one-sided p for H0: ρ >= 0.5 vs HA: ρ < 0.5 (t-approx)
    against = 0.5
    t = (rho - against) * math.sqrt((n - 2) / max(1 - rho ** 2, 1e-12))
    p_one = 0.5 * math.erfc(-t / math.sqrt(2)) if t < 0 else 1 - 0.5 * math.erfc(t / math.sqrt(2))
    md.append(f"\n**Pooled (both judges): n={n}, ρ={rho:.3f}**")
    md.append(f"- H10 test (ρ < 0.5, one-sided): t={t:.2f}, p={p_one:.3g}")
    verdict = "SUPPORTED (decoupled)" if (rho < 0.5 and p_one < 0.05) else \
              "directional only" if rho < 0.5 else "NOT supported (coupled)"
    md.append(f"- Verdict: **{verdict}** — faithfulness and accuracy are "
              f"{'moderately coupled' if rho >= 0.4 else 'weakly coupled'} (ρ≈{rho:.2f}).")
    out = Path("data/round2/ablations/H10_faithfulness_accuracy.md")
    out.write_text("\n".join(md))
    print("\n".join(md))
    print(f"\nWrote {out}")
    print(f"H10_RESULT rho={rho:.3f} n={n} p_one={p_one:.4f}")


if __name__ == "__main__":
    main()
