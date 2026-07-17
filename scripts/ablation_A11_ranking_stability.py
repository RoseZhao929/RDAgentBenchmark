"""Ablation A11 — Cross-dataset agent ranking stability (Spearman ρ).

For each pair of datasets (PP-Store, RareArena, RareBench, MIMIC) compute
Spearman ρ of agent R@1 ranks. Low ρ means an agent's ranking shifts
across datasets — dataset-specific behavior, not a universal best.

Output:
  - data/round2/ablations/A11_ranking_stability.md
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from collections import defaultdict
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def main():
    with open('data/round2/phase4a_summary.json') as f:
        stats = json.load(f)

    # Pick best backbone per agent per dataset (R@1 variants)
    per_ds = defaultdict(dict)  # dataset -> agent -> best R@1
    for key, s in stats.items():
        if s['ok'] == 0: continue
        ds, ag, bb = key.split('|')
        r1v = s['h1v'] / s['ok']
        if ag not in per_ds[ds] or r1v > per_ds[ds][ag][0]:
            per_ds[ds][ag] = (r1v, bb, s['ok'])

    # Build agent-rank vectors per dataset
    datasets = ['phenopacket_store','rarearena_rds','rarebench','mimic_diverse']
    rank_vectors = {}
    for ds in datasets:
        if not per_ds[ds]: continue
        ag_r1 = [(ag, v[0]) for ag, v in per_ds[ds].items()]
        ag_r1.sort(key=lambda x: -x[1])  # descending R@1
        # Rank: best=1, worst=N
        rank_vectors[ds] = {ag: i+1 for i, (ag, _) in enumerate(ag_r1)}

    # Pairwise Spearman
    try:
        from scipy.stats import spearmanr
    except ImportError:
        # Hand-roll Spearman
        def spearmanr(a, b):
            assert len(a) == len(b)
            n = len(a)
            if n < 3: return (None, None)
            mean_a, mean_b = sum(a)/n, sum(b)/n
            num = sum((a[i]-mean_a)*(b[i]-mean_b) for i in range(n))
            den_a = sum((a[i]-mean_a)**2 for i in range(n))**0.5
            den_b = sum((b[i]-mean_b)**2 for i in range(n))**0.5
            if den_a*den_b == 0: return (0, None)
            return (num/(den_a*den_b), None)

    md = ["# Ablation A11 — Cross-dataset Agent Ranking Stability (Spearman ρ)",
          "",
          "For each agent we pick its best-performing backbone per dataset (R@1 variants)",
          "and rank agents within each dataset (1=best). Spearman ρ measures how",
          "stable agent rankings are across datasets.",
          "",
          "## Per-dataset agent rankings (best→worst)",
          ""]
    for ds in datasets:
        if not rank_vectors.get(ds): continue
        ranked = sorted(per_ds[ds].items(), key=lambda x: -x[1][0])
        md.append(f"### {ds}")
        md.append("| Rank | Agent | R@1 (best backbone) | n_ok |")
        md.append("|---|---|---|---|")
        for i, (ag, (r1, bb, n)) in enumerate(ranked, 1):
            md.append(f"| {i} | `{ag}` | {r1:.3f} ({bb[:25]}) | {n} |")
        md.append("")

    md.append("## Pairwise Spearman ρ\n")
    md.append("| dataset A | dataset B | n_agents in common | Spearman ρ |")
    md.append("|---|---|---|---|")
    for i, ds1 in enumerate(datasets):
        for ds2 in datasets[i+1:]:
            if not rank_vectors.get(ds1) or not rank_vectors.get(ds2): continue
            common = sorted(set(rank_vectors[ds1]) & set(rank_vectors[ds2]))
            if len(common) < 3: continue
            ranks1 = [rank_vectors[ds1][a] for a in common]
            ranks2 = [rank_vectors[ds2][a] for a in common]
            rho, _ = spearmanr(ranks1, ranks2)
            md.append(f"| {ds1} | {ds2} | {len(common)} | **{rho:.3f}** |" if rho is not None else f"| {ds1} | {ds2} | {len(common)} | n/a |")

    md.append("\n## Interpretation\n")
    md.append("- ρ ≥ 0.7: rankings stable across datasets — agent has universal ordering")
    md.append("- 0.4 ≤ ρ < 0.7: moderate stability — some dataset-specific effects")
    md.append("- ρ < 0.4: rankings shift substantially — strong dataset×agent interaction")
    md.append("")

    Path('data/round2/ablations').mkdir(parents=True, exist_ok=True)
    Path('data/round2/ablations/A11_ranking_stability.md').write_text("\n".join(md))
    print(f"Wrote A11_ranking_stability.md ({len(md)} lines)")

if __name__ == "__main__":
    main()
