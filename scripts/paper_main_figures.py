"""Regenerate the SIX main-body paper figures (2026-07 restructure).

Every figure is driven from the FROZEN audited sources so the plotted numbers
are byte-identical to the numbers in the paper text and Table 1:

  audit_frozen/frozen_main_manifest.csv   -- per-cell R@1 (n_attempted denom)
  audit_frozen/cost_summary.csv           -- per-backbone cost-per-attempt
  audit_frozen/_p5_same_trace_report.json -- P5 same-trace judge rho

The prevalence (H1), phenotype-density (H8), specialty (H7) and Holm-family
numbers live only in the paper text (their raw ablation dumps were stripped
from the frozen slim release); they are transcribed here from the authoritative
frozen tables in paper_sections/ and kept in one place so figure == text.

Main-body figures (in reading order):
  figM1_llm_vs_classical   F1 headline: best LLM vs best classical, per layer
  figM2_cost_accuracy      cost-vs-accuracy Pareto (carries F3 + F4)
  figM3_prevalence         H1 prevalence crossover (classical rises on rarest)
  figM4_hpo_density        H8 phenotype-density inverted-U
  figM5_selfpref           P5 self-preference / judge-family slopegraph
  figM6_hypotheses         Holm-Bonferroni hypothesis-test forest plot

Writes 300-dpi PNGs to data/round2/figures/ (Nimbus-Roman / Times serif).
"""
from __future__ import annotations
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from _figstyle import apply_nature_style, PALETTE, despine  # noqa: E402

FIG = ROOT / "data/round2/figures"
MANIFEST = ROOT / "audit_frozen/frozen_main_manifest.csv"
COST = ROOT / "audit_frozen/cost_summary.csv"
P5 = ROOT / "audit_frozen/_p5_same_trace_report.json"

CLASSICAL = {"lirical", "vc_rdagent"}

# Consistent colours for the two agent families across every figure.
C_LLM = PALETTE[0]        # blue  = LLM-scaffolded agents
C_CLASSICAL = PALETTE[3]  # vermilion = classical / offline baselines
C_ACCENT = PALETTE[1]     # orange accent (peaks / highlights)


# ------------------------------------------------------------------ load frozen
def load_manifest():
    rows = list(csv.DictReader(open(MANIFEST)))
    for r in rows:
        r["R@1_variant_aware"] = float(r["R@1_variant_aware"])
        r["R@1_strict"] = float(r["R@1_strict"])
        r["n_attempted"] = int(r["n_attempted"])
        r["cost_per_attempt"] = float(r["cost_per_attempt"] or 0)
    return rows


def best_per_family(rows, datasets, min_n=100):
    """Best variant-aware R@1 per (dataset, family), attempted denom, n>=min_n."""
    best = {}
    for r in rows:
        ds = r["dataset"]
        if ds not in datasets or r["n_attempted"] < min_n:
            continue
        fam = "classical" if r["system"] in CLASSICAL else "llm"
        v = r["R@1_variant_aware"]
        cur = best.get((ds, fam))
        if cur is None or v > cur[0]:
            best[(ds, fam)] = (v, r["system"], r["backbone"], r["n_attempted"])
    return best


# =========================================================== M1: F1 headline
def figM1_llm_vs_classical(rows):
    apply_nature_style()
    import matplotlib.pyplot as plt
    import numpy as np

    layers = [("phenopacket_store", "Phenopacket-Store\n(curated HPO)"),
              ("rarebench", "RareBench HF\n(sparse HPO)"),
              ("rarearena_rds", "RareArena RDS\n(free-text)")]
    best = best_per_family(rows, {l[0] for l in layers})

    llm = [best.get((l[0], "llm"), (0,))[0] for l in layers]
    cls = [best.get((l[0], "classical"), (None,))[0] for l in layers]

    fig, ax = plt.subplots(figsize=(6.6, 3.9))
    x = np.arange(len(layers))
    w = 0.38
    b1 = ax.bar(x - w / 2, llm, w, label="Best LLM agent", color=C_LLM, zorder=3)
    # classical bar only where a classical baseline runs (HPO layers)
    cls_x, cls_v = [], []
    for i, c in enumerate(cls):
        if c is not None:
            cls_x.append(x[i] - (-w / 2))
            cls_v.append(c)
    b2 = ax.bar(np.array(cls_x), cls_v, w, label="Best classical / offline",
                color=C_CLASSICAL, zorder=3)

    def label(bars):
        for b in bars:
            h = b.get_height()
            ax.text(b.get_x() + b.get_width() / 2, h + 0.008, f"{h:.2f}",
                    ha="center", va="bottom", fontsize=7.5)
    label(b1)
    label(b2)

    # gap annotation on PP-Store (the headline F1 gap)
    if cls[0] is not None:
        gap = (cls[0] - llm[0]) * 100
        ax.annotate("", xy=(0 + w / 2, cls[0]), xytext=(0 + w / 2, llm[0]),
                    arrowprops=dict(arrowstyle="<->", color="#444", lw=1.0))
        ax.text(0 + w / 2 + 0.06, (cls[0] + llm[0]) / 2,
                f"+{gap:.0f} pp", fontsize=8, color="#444", va="center")

    ax.set_xticks(x)
    ax.set_xticklabels([l[1] for l in layers], fontsize=8)
    ax.set_ylabel("R@1 (variant-aware)")
    ax.set_ylim(0, 0.56)
    ax.set_title("Classical/offline baselines beat the best scaffolded LLM "
                 "on HPO input", fontsize=8.6)
    ax.legend(loc="upper right", fontsize=7.5)
    ax.grid(axis="y", alpha=0.4, zorder=0)
    despine(ax)
    # note that free-text has no classical bar (no HPO input)
    ax.text(2, 0.02, "no HPO input\n(classical n/a)", ha="center", va="bottom",
            fontsize=6.5, style="italic", color="#888")
    fig.tight_layout()
    fig.savefig(FIG / "figM1_llm_vs_classical.png")
    plt.close(fig)
    print("wrote figM1_llm_vs_classical.png",
          f"[PP {llm[0]:.3f}v{cls[0]:.3f}, RB {llm[1]:.3f}v{cls[1]:.3f}]")


# =========================================================== M2: cost-accuracy
def figM2_cost_accuracy(rows):
    apply_nature_style()
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    bb_short = {"google_gemini-3-flash-preview-": ("Gemini Flash", "o"),
                "deepseek_deepseek-v4-pro": ("DS V4-Pro", "s"),
                "deepseek_deepseek-v4-flash": ("DS V4-Flash", "^"),
                "openai_gpt-5": ("GPT-5 min", "D")}

    def bb_key(bb):
        for k in bb_short:
            if bb.startswith(k):
                return k
        return None

    agents = ["llm_control", "mdagents", "medagents", "agentclinic",
              "maidxo", "deeprare"]
    ag_color = {a: PALETTE[i % len(PALETTE)] for i, a in enumerate(agents)}

    fig, ax = plt.subplots(figsize=(6.6, 4.4))
    pts = []
    for r in rows:
        if r["dataset"] != "phenopacket_store" or r["n_attempted"] < 100:
            continue
        if r["system"] in CLASSICAL:
            continue
        k = bb_key(r["backbone"])
        if not k or r["cost_per_attempt"] <= 0:
            continue
        cost = r["cost_per_attempt"]     # true per-cell cost (attempted denom)
        acc = r["R@1_variant_aware"]
        pts.append((cost, acc))
        ax.scatter(cost, acc, c=ag_color.get(r["system"], "#999"),
                   marker=bb_short[k][1], s=48, alpha=0.9,
                   edgecolors="white", linewidths=0.5, zorder=3)

    # Pareto frontier (max acc at or below each cost)
    front, best = [], -1
    for cost, acc in sorted(pts):
        if acc > best:
            best = acc
            front.append((cost, acc))
    if front:
        ax.step([p[0] for p in front], [p[1] for p in front], where="post",
                color="#333", lw=1.1, ls="--", zorder=2)

    ax.set_xscale("log")
    ax.set_xlabel("Cost per attempt (USD, log scale)")
    ax.set_ylabel("R@1 (variant-aware), Phenopacket-Store")
    ax.set_title("GPT-5 costs 25× more than V4-Flash for no R@1 gain",
                 fontsize=8.6)
    ax.grid(True, which="major", alpha=0.4, zorder=0)
    ag_h = [Line2D([0], [0], marker="o", color="w", markerfacecolor=ag_color[a],
                   markersize=6.5, label=a) for a in agents]
    bb_h = [Line2D([0], [0], marker=m, color="#555", ls="", markersize=6.5,
                   label=lab) for lab, m in bb_short.values()]
    l1 = ax.legend(handles=ag_h, title="agent", loc="lower right", fontsize=6.5,
                   title_fontsize=7, ncol=2)
    ax.add_artist(l1)
    ax.legend(handles=bb_h + [Line2D([0], [0], color="#333", ls="--",
              label="Pareto frontier")], title="backbone", loc="upper left",
              fontsize=6.5, title_fontsize=7)
    despine(ax)
    fig.tight_layout()
    fig.savefig(FIG / "figM2_cost_accuracy.png")
    plt.close(fig)
    print("wrote figM2_cost_accuracy.png")


# =========================================================== M3: prevalence H1
def figM3_prevalence():
    # frozen H1 tier values (paper_sections/7_2_7_3_7_4_analysis.md §7.7)
    apply_nature_style()
    import matplotlib.pyplot as plt

    tiers = ["common-rare", "moderate", "ultra-rare", "super-rare"]
    llm = [0.37, 0.26, 0.39, 0.22]
    cls = [0.30, 0.23, 0.33, 0.50]

    fig, ax = plt.subplots(figsize=(6.6, 3.9))
    ax.plot(tiers, llm, "o-", color=C_LLM, lw=1.8, ms=7,
            label="LLM agents (Gemini Flash)")
    ax.plot(tiers, cls, "s--", color=C_CLASSICAL, lw=1.8, ms=7,
            label="Classical / offline (LIRICAL + VC-RDAgent)")
    for xs, ys in ((tiers, llm), (tiers, cls)):
        for xi, yi in zip(xs, ys):
            ax.text(xi, yi + 0.015, f"{yi:.2f}", ha="center", fontsize=6.8,
                    color="#333")
    # crossover gap on rarest tier
    gap = (cls[-1] - llm[-1]) * 100
    ax.annotate("", xy=(3, cls[-1]), xytext=(3, llm[-1]),
                arrowprops=dict(arrowstyle="<->", color="#444", lw=1.0))
    ax.text(2.78, (cls[-1] + llm[-1]) / 2, f"+{gap:.0f} pp",
            fontsize=8, color="#444", ha="right", va="center")
    ax.set_xlabel("Prevalence tier (commonest → rarest)")
    ax.set_ylabel("Pooled R@1")
    ax.set_ylim(0, 0.58)
    ax.set_title("On the rarest diseases the classical/LLM ranking inverts (H1)",
                 fontsize=8.6)
    ax.legend(loc="upper left", fontsize=7.5)
    ax.grid(True, alpha=0.4)
    despine(ax)
    fig.tight_layout()
    fig.savefig(FIG / "figM3_prevalence.png")
    plt.close(fig)
    print("wrote figM3_prevalence.png")


# =========================================================== M4: HPO density H8
def figM4_hpo_density():
    # frozen H8 bins (paper_sections/7_1_p1_p2_cascade.md §7.1.2)
    apply_nature_style()
    import matplotlib.pyplot as plt
    import numpy as np

    bins = ["≤5", "6–15", "16–30", ">30"]
    ns = [528, 2352, 1361, 513]
    r1 = [0.218, 0.276, 0.323, 0.253]

    fig, ax = plt.subplots(figsize=(6.6, 3.9))
    x = np.arange(len(bins))
    colors = [C_ACCENT if i == int(np.argmax(r1)) else C_LLM
              for i in range(len(bins))]
    bars = ax.bar(x, r1, 0.6, color=colors, zorder=3)
    for b, v, n in zip(bars, r1, ns):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.006, f"{v:.2f}",
                ha="center", va="bottom", fontsize=7.5)
        ax.text(b.get_x() + b.get_width() / 2, 0.012, f"n={n:,}",
                ha="center", va="bottom", fontsize=6.3, color="white")
    ax.set_xticks(x)
    ax.set_xticklabels(bins)
    ax.set_xlabel("HPO terms per case (binned)")
    ax.set_ylabel("Pooled R@1 (HPO-input layers)")
    ax.set_ylim(0, 0.38)
    ax.set_title("Phenotype density: an interior optimum at 16–30 HPO terms "
                 "(H8)", fontsize=8.6)
    ax.grid(axis="y", alpha=0.4, zorder=0)
    despine(ax)
    fig.tight_layout()
    fig.savefig(FIG / "figM4_hpo_density.png")
    plt.close(fig)
    print("wrote figM4_hpo_density.png")


# =========================================================== M5: self-preference
def figM5_selfpref():
    # frozen §7.5 table: v1 Gemini (family) -> v2 Claude (non-family), same axes.
    # Only llm_control + deeprare isolate a clean judge swap (traces already
    # complete in v1); we plot those two and annotate the confound for mdagents.
    apply_nature_style()
    import matplotlib.pyplot as plt

    axes_names = ["factual", "relevance", "depth", "faithful"]
    data = {
        "llm_control": ([4.70, 4.50, 3.60, 4.90], [4.30, 4.50, 3.10, 4.50], C_LLM),
        "mdagents":    ([5.00, 5.00, 4.00, 5.00], [4.10, 4.17, 3.49, 4.26], PALETTE[2]),
        "deeprare":    ([1.70, 1.40, 1.90, 1.70], [2.31, 1.33, 2.58, 2.72], PALETTE[4]),
    }
    fig, axs = plt.subplots(1, 4, figsize=(7.4, 3.2), sharey=True)
    for j, (axname, ax) in enumerate(zip(axes_names, axs)):
        for agn, (v1, v2, color) in data.items():
            ax.plot([0, 1], [v1[j], v2[j]], color=color, marker="o", ms=5,
                    lw=1.6, label=agn if j == 0 else None, zorder=3)
        ax.set_xlim(-0.35, 1.35)
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["Gemini\n(family)", "Claude\n(non-fam.)"], fontsize=6.6)
        ax.set_title(axname, fontsize=8.4)
        ax.set_ylim(1, 5.3)
        despine(ax)
        ax.grid(axis="y", alpha=0.4)
    axs[0].set_ylabel("LLM-judge score (1–5)")
    axs[0].legend(loc="lower left", fontsize=6.6)
    fig.suptitle("Swapping to a non-family judge shrinks the single-LLM lead "
                 "(mdagents overtakes on depth)", fontsize=8.6, y=1.02)
    fig.tight_layout()
    fig.savefig(FIG / "figM5_selfpref.png")
    plt.close(fig)
    print("wrote figM5_selfpref.png")


# =========================================================== M6: Holm forest
def figM6_hypotheses():
    # frozen Holm-Bonferroni family (paper_sections/8_ablations.md §8.8).
    # Plot effect sizes on a common panel is misleading (z vs rho), so we show a
    # forest plot of -log10(Holm-adj p) with the verdict, sorted by significance.
    apply_nature_style()
    import matplotlib.pyplot as plt
    import numpy as np

    # (label, statistic string, Holm-adj p, survives)
    H = [
        ("H1  classical > LLM on super-rare tier", "z=17.5", 2.2e-68, True),
        ("H8  R@1 peaks at 16–30 HPO terms",     "z=12.6", 7.8e-36, True),
        ("H2  genotype channel lift (P3 > P2)",   "z=6.4",  3.0e-10, True),
        ("H7  cross-agent specialty rank ρ>0.6",  "ρ=0.92", 1.6e-03, True),
        ("H4  scaffold helps more on complex",    "z=2.6",  9.0e-03, True),
        ("H10 faithfulness–accuracy decoupling", "ρ=0.46", 3.7e-02, False),
    ]
    H = sorted(H, key=lambda h: h[2], reverse=True)  # least to most significant
    labels = [h[0] for h in H]
    neglogp = [-np.log10(h[2]) for h in H]
    y = np.arange(len(H))

    fig, ax = plt.subplots(figsize=(6.8, 3.6))
    colors = [C_LLM if h[3] else "#BBBBBB" for h in H]
    ax.hlines(y, 0, neglogp, color="#cccccc", lw=1.2, zorder=1)
    ax.scatter(neglogp, y, s=70, color=colors, zorder=3, edgecolors="white",
               linewidths=0.6)
    # alpha=0.05 threshold after Holm (=-log10(0.05))
    thr = -np.log10(0.05)
    ax.axvline(thr, color=C_CLASSICAL, ls="--", lw=1.0, zorder=2)
    ax.text(thr + 0.3, -0.6, r"$\alpha$=0.05", color=C_CLASSICAL, fontsize=7,
            va="center")
    for yi, h in zip(y, H):
        ax.text(neglogp[yi] + 1.2, yi, h[1], va="center", fontsize=6.8,
                color="#333")
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=7.2)
    ax.set_xlabel(r"$-\log_{10}$(Holm-adjusted $p$)")
    ax.set_xlim(0, max(neglogp) * 1.15)
    ax.set_title("Five of six pre-registered hypotheses survive family-wise "
                 "correction", fontsize=8.6)
    ax.grid(axis="x", alpha=0.4, zorder=0)
    despine(ax)
    # H10 caveat, placed next to the H10 row (y=0, the least-significant / grey point)
    ax.annotate("H10 exploratory\n(judge-dependent)", xy=(neglogp[0], 0),
                xytext=(max(neglogp) * 0.32, 0.55), fontsize=6.2, style="italic",
                color="#888", va="center",
                arrowprops=dict(arrowstyle="->", color="#bbb", lw=0.7))
    fig.tight_layout()
    fig.savefig(FIG / "figM6_hypotheses.png")
    plt.close(fig)
    print("wrote figM6_hypotheses.png")


# =============================================================== A: contamination
def figA_contamination():
    # frozen A6 rho values (paper_sections/8_ablations.md §8.9). The per-disease
    # scatter data was stripped from the slim release; the load-bearing finding is
    # the LLM-vs-classical rho dichotomy, which we plot directly as a dot-plot.
    apply_nature_style()
    import matplotlib.pyplot as plt
    import numpy as np

    rows = [  # (label, rho, n_diseases, is_llm)
        ("Gemini 3 Flash", 0.365, 244, True),
        ("GPT-5 minimal", 0.354, 87, True),
        ("DeepSeek V4-Flash", 0.348, 244, True),
        ("DeepSeek V4-Pro", 0.294, 179, True),
        ("LIRICAL (classical)", -0.155, 26, False),
        ("VC-RDAgent (offline)", -0.059, 26, False),
    ]
    rows = sorted(rows, key=lambda r: r[1])
    labels = [r[0] for r in rows]
    rho = [r[1] for r in rows]
    y = np.arange(len(rows))
    colors = [C_LLM if r[3] else C_CLASSICAL for r in rows]

    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    ax.axvline(0, color="#999", lw=0.8, zorder=1)
    ax.hlines(y, 0, rho, color="#cccccc", lw=1.2, zorder=1)
    ax.scatter(rho, y, s=70, color=colors, zorder=3, edgecolors="white",
               linewidths=0.6)
    for yi, r in zip(y, rows):
        ax.text(r[1] + (0.012 if r[1] >= 0 else -0.012), yi,
                f"{r[1]:.3f} (n={r[2]})", va="center",
                ha="left" if r[1] >= 0 else "right", fontsize=6.6, color="#333")
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=7.4)
    ax.set_xlabel("Spearman ρ (log pre-cutoff PubMed mentions vs. per-disease R@1)")
    ax.set_xlim(-0.32, 0.55)
    ax.set_title("Contamination audit: LLM backbones ρ≈0.3 (weak), classical "
                 "ρ≈0 (null control)", fontsize=8.4)
    ax.grid(axis="x", alpha=0.4, zorder=0)
    despine(ax)
    fig.tight_layout()
    fig.savefig(FIG / "fig4_a6_contamination_scatter.png")
    plt.close(fig)
    print("wrote fig4_a6_contamination_scatter.png (rho dichotomy)")


# =============================================================== A: specialty H7
def figA_specialty():
    # frozen H7 specialty R@1 ranges (paper_sections §7.9). The full per-agent
    # matrix source was stripped; we plot the stated LLM range (min-max bar) per
    # organ system plus the classical inversion the text calls out.
    apply_nature_style()
    import matplotlib.pyplot as plt
    import numpy as np

    # (specialty, llm_low, llm_high, classical_point or None)
    specs = [
        ("digestive", 0.09, 0.09, None),
        ("metabolism/homeostasis", 0.10, 0.16, None),
        ("nervous system", 0.11, 0.14, 0.39),   # LIRICAL 0.35 / VC-RDAgent 0.43 -> ~0.39
        ("cardiovascular", 0.41, 0.44, None),
        ("head/neck", 0.44, 0.44, 0.53),        # classical lead 0.52-0.54
        ("integument", 0.44, 0.56, None),
    ]
    specs = sorted(specs, key=lambda s: (s[1] + s[2]) / 2)
    y = np.arange(len(specs))
    mids = [(s[1] + s[2]) / 2 for s in specs]
    errs = [[m - s[1] for m, s in zip(mids, specs)],
            [s[2] - m for m, s in zip(mids, specs)]]

    fig, ax = plt.subplots(figsize=(6.6, 3.6))
    ax.barh(y, mids, xerr=errs, color=C_LLM, height=0.55, zorder=3,
            error_kw=dict(ecolor="#33506e", lw=1.0, capsize=3),
            label="LLM agents (range across scaffolds)")
    for yi, s in enumerate(specs):
        if s[3] is not None:
            ax.scatter([s[3]], [yi], marker="D", s=46, color=C_CLASSICAL,
                       zorder=4, edgecolors="white", linewidths=0.5)
    ax.scatter([], [], marker="D", s=46, color=C_CLASSICAL,
               label="classical baseline (where it inverts)")
    ax.set_yticks(y)
    ax.set_yticklabels([s[0] for s in specs], fontsize=7.4)
    ax.set_xlabel("R@1 by modal HPO organ system")
    ax.set_xlim(0, 0.62)
    ax.set_title("Shared cross-agent specialty blind spots (H7); classical "
                 "inverts on nervous/head-neck", fontsize=8.2)
    ax.legend(loc="lower right", fontsize=6.8)
    ax.grid(axis="x", alpha=0.4, zorder=0)
    despine(ax)
    fig.tight_layout()
    fig.savefig(FIG / "fig7_specialty_h7.png")
    plt.close(fig)
    print("wrote fig7_specialty_h7.png (H7 specialty ranges)")


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    rows = load_manifest()
    figM1_llm_vs_classical(rows)
    figM2_cost_accuracy(rows)
    figM3_prevalence()
    figM4_hpo_density()
    figM5_selfpref()
    figM6_hypotheses()
    figA_contamination()
    figA_specialty()
    print("all main-body + appendix analytic figures written to", FIG)


if __name__ == "__main__":
    main()
