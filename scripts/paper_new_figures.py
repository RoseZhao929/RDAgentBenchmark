"""New paper figures (2026-07 round), Nature-grade style (shared _figstyle):

  fig1_overview  : THE benchmark-method overview — the core pipeline chain
                   (3 diagnostic layers + structured probe -> CanonicalCase
                   A/B -> 5 capability pillars -> metrics). Hand-drawn schematic.
  fig_radar      : legacy agent capability radar over diagnostic layers
                   R@1), overlaying representative LLM agents + classical
                   baselines. Real data from leaderboard/phase4a_summary.json.
  fig_selfpref   : self-preference slopegraph — v1 (Gemini/family judge) ->
                   v2 (Claude/non-family judge) 4-axis faithfulness scores.
  fig_costbar    : cost-per-prediction by backbone (log axis), the cost story
                   as a bar chart. From Sec 6.3 / Appendix J.

Writes 300-dpi PNGs to paper_build/acl/figures/ (committed, git-tracked).
Run:  .figvenv/bin/python scripts/paper_new_figures.py
"""
from __future__ import annotations
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from _figstyle import apply_nature_style, PALETTE  # noqa: E402

FIG = ROOT / "data" / "round2" / "figures"
SUMMARY = ROOT / "leaderboard" / "phase4a_summary.json"

# ---------------------------------------------------------------- shared data
DS_ORDER = ["phenopacket_store", "rarebench", "rarearena_rds"]
DS_LABEL = {
    "phenopacket_store": "PP-Store\n(HPO, curated)",
    "rarebench": "RareBench\n(HPO, sparse)",
    "rarearena_rds": "RareArena\n(free-text)",
}


def best_backbone_r1():
    """best-backbone R@1 per (agent, dataset) from committed per-cell receipts."""
    d = json.load(open(SUMMARY))
    best = defaultdict(float)
    for k, v in d.items():
        dsn, agn, _ = k.split("|")
        if v.get("ok", 0) > 0:
            best[(agn, dsn)] = max(best[(agn, dsn)], v["h1v"] / v["ok"])
    return best


# =========================================================== Figure 1: overview
def fig1_overview():
    apply_nature_style()
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

    fig, ax = plt.subplots(figsize=(13.0, 5.4))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 46)
    ax.axis("off")

    C_DATA = "#0072B2"
    C_CANON = "#333333"
    C_ADAPT = "#E69F00"
    C_PASS = "#009E73"
    C_PILLAR = "#CC79A7"
    C_METRIC = "#56B4E9"

    def box(x, y, w, h, fc, ec="white", lw=0.8, r=0.4, alpha=1.0, z=2):
        ax.add_patch(FancyBboxPatch(
            (x, y), w, h, boxstyle=f"round,pad=0.02,rounding_size={r}",
            linewidth=lw, edgecolor=ec, facecolor=fc, alpha=alpha, zorder=z))

    def arrow(x0, y0, x1, y1, color="#888", lw=1.4, z=1):
        ax.add_patch(FancyArrowPatch(
            (x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=11,
            linewidth=lw, color=color, zorder=z,
            shrinkA=1, shrinkB=1))

    def col_header(x, w, txt, color):
        ax.text(x + w / 2, 44.2, txt, ha="center", va="center",
                fontsize=9.5, fontweight="bold", color=color)

    # ---- column 1: diagnostic layers + separate structured probe -------
    layers = [
        ("L1", "Phenopacket-Store + RareBench", "11,173 · HPO, gold, variants"),
        ("S-EHR", "MIMIC-IV structured probe", "956 · separate code-supervised task"),
        ("L3", "RareArena RDS", "72,661 · free-text vignette"),
        ("L4", "PMC-OA holdout ≥ 2024", "200 · post-cutoff, verified"),
    ]
    x1, w1 = 1.0, 20.0
    col_header(x1, w1, "Data layers", C_DATA)
    ys = [33.5, 24.5, 15.5, 6.5]
    for (lid, name, sub), y in zip(layers, ys):
        box(x1, y, w1, 7.4, C_DATA, alpha=0.13, ec=C_DATA, lw=0.9)
        ax.text(x1 + 0.9, y + 5.6, lid, ha="left", va="center",
                fontsize=9, fontweight="bold", color=C_DATA)
        ax.text(x1 + 0.9, y + 3.5, name, ha="left", va="center",
                fontsize=7.3, color="#111")
        ax.text(x1 + 0.9, y + 1.5, sub, ha="left", va="center",
                fontsize=6.4, style="italic", color="#555")

    # ---- column 2: canonical case (the funnel) -------------------------
    x2, w2 = 25.0, 13.5
    col_header(x2, w2, "Unified contract", C_CANON)
    box(x2, 12.0, w2, 22.0, "#fbfbfb", ec=C_CANON, lw=1.3)
    ax.text(x2 + w2 / 2, 31.6, "CanonicalCase", ha="center", va="center",
            fontsize=10, fontweight="bold", color="#111")
    ax.text(x2 + w2 / 2, 29.4, "Pydantic-v2", ha="center", va="center",
            fontsize=6.8, style="italic", color="#666")
    for k, fld in enumerate(["identity", "demographics", "free_text /",
                             "  synthetic vignette", "gold_hpo_terms",
                             "variants · vcf_path", "family", "gold_label (parallel ID)"]):
        ax.text(x2 + 1.0, 27.4 - k * 1.9, fld, ha="left", va="center",
                fontsize=6.6, family="monospace", color="#222")
    for y in ys:
        arrow(x1 + w1, y + 3.7, x2, 23.0, color=C_DATA, lw=1.1)

    # ---- column 3: 11 adapter shims ------------------------------------
    x3, w3 = 41.0, 13.0
    col_header(x3, w3, "Agent adapters", C_ADAPT)
    box(x3, 12.0, w3, 22.0, C_ADAPT, alpha=0.13, ec=C_ADAPT, lw=0.9)
    ax.text(x3 + w3 / 2, 31.8, "11 systems", ha="center", va="center",
            fontsize=9, fontweight="bold", color="#8a5a00")
    agents = ["DeepRare", "MDAgents", "MedAgents", "AgentClinic", "MAI-DxO",
              "RDMA", "VC-RDAgent", "LIRICAL", "+3 LLM controls"]
    for k, a in enumerate(agents):
        ax.text(x3 + w3 / 2, 29.4 - k * 2.0, a, ha="center", va="center",
                fontsize=6.7, color="#222",
                fontweight="bold" if a.startswith("+") else "normal")
    ax.text(x3 + w3 / 2, 12.9, "subprocess isolation", ha="center", va="center",
            fontsize=6.0, style="italic", color="#8a5a00")
    arrow(x2 + w2, 23.0, x3, 23.0, color=C_CANON, lw=1.6)

    # ---- column 4: dual-pass -------------------------------------------
    x4, w4 = 56.5, 15.0
    col_header(x4, w4, "Dual-pass eval", C_PASS)
    # Pass A
    box(x4, 24.5, w4, 9.0, C_PASS, alpha=0.16, ec=C_PASS, lw=0.9)
    ax.text(x4 + w4 / 2, 31.6, "Pass A · gold HPO", ha="center", va="center",
            fontsize=8, fontweight="bold", color="#00694d")
    ax.text(x4 + w4 / 2, 29.2, "curated HPO → downstream", ha="center",
            va="center", fontsize=6.5, color="#222")
    ax.text(x4 + w4 / 2, 27.2, "isolates capability", ha="center", va="center",
            fontsize=6.2, style="italic", color="#00694d")
    # Pass B
    box(x4, 13.0, w4, 9.0, C_PASS, alpha=0.16, ec=C_PASS, lw=0.9)
    ax.text(x4 + w4 / 2, 20.1, "Pass B · end-to-end", ha="center", va="center",
            fontsize=8, fontweight="bold", color="#00694d")
    ax.text(x4 + w4 / 2, 17.7, "free text → agent extracts", ha="center",
            va="center", fontsize=6.5, color="#222")
    ax.text(x4 + w4 / 2, 15.7, "deployment performance", ha="center", va="center",
            fontsize=6.2, style="italic", color="#00694d")
    arrow(x3 + w3, 26.0, x4, 29.0, color=C_ADAPT, lw=1.4)
    arrow(x3 + w3, 20.0, x4, 17.5, color=C_ADAPT, lw=1.4)
    # delta annotation
    ax.annotate("", xy=(x4 + w4 / 2, 24.4), xytext=(x4 + w4 / 2, 22.1),
                arrowprops=dict(arrowstyle="<->", color="#d1495b", lw=1.3))
    ax.text(x4 + w4 + 0.4, 23.25, "A−B\n= P1\nsensitivity", ha="left",
            va="center", fontsize=6.3, color="#d1495b", fontweight="bold")

    # ---- column 5: five pillars ----------------------------------------
    x5, w5 = 76.5, 13.0
    col_header(x5, w5, "Five pillars", C_PILLAR)
    pillars = [
        ("P1", "Phenotype extraction"),
        ("P2", "Phenotype-only DDx"),
        ("P3", "Genotype-aware DDx"),
        ("P4", "Family-aware DDx (v2)"),
        ("P5", "Reasoning faithfulness"),
    ]
    ph = 3.9
    for k, (pid, pname) in enumerate(pillars):
        y = 33.0 - k * (ph + 0.9)
        deferred = pid == "P4"
        box(x5, y, w5, ph, C_PILLAR, alpha=0.10 if deferred else 0.20,
            ec=C_PILLAR, lw=0.8)
        ax.text(x5 + 0.8, y + ph / 2 + 0.55, pid, ha="left", va="center",
                fontsize=8, fontweight="bold",
                color="#9c4f78" if not deferred else "#bb97ac")
        ax.text(x5 + 0.8, y + ph / 2 - 0.9, pname, ha="left", va="center",
                fontsize=6.3, color="#333" if not deferred else "#999",
                style="italic" if deferred else "normal")
    arrow(x4 + w4, 29.0, x5, 26.0, color=C_PASS, lw=1.4)
    arrow(x4 + w4, 17.5, x5, 20.0, color=C_PASS, lw=1.4)

    # ---- column 6: metrics ---------------------------------------------
    x6, w6 = 91.5, 7.6
    col_header(x6, w6, "Metrics", C_METRIC)
    box(x6, 12.0, w6, 22.0, C_METRIC, alpha=0.14, ec=C_METRIC, lw=0.9)
    for k, m in enumerate(["R@1/3/5/10", "MRR", "median rank",
                            "P/R/F1", "cost / case", "passʸ",
                            "faithfulness", "bias strata"]):
        ax.text(x6 + w6 / 2, 30.5 - k * 2.4, m, ha="center", va="center",
                fontsize=6.6, family="monospace", color="#1f5d78")
    arrow(x5 + w5, 23.0, x6, 23.0, color=C_PILLAR, lw=1.6)

    # ---- pre-registration footer band ----------------------------------
    box(x1, 1.0, (x6 + w6) - x1, 3.2, "#f3f4f6", ec="#cccccc", lw=0.7, r=0.3)
    ax.text((x1 + x6 + w6) / 2, 2.6,
            "Pre-registered protocol: H1–H11 hypotheses + A1–A12 ablations "
            "frozen at OSF · per-cell reproducibility receipts (run-id, request-id, $cost) released",
            ha="center", va="center", fontsize=7.0, color="#444")

    fig.savefig(FIG / "fig1_overview.png")
    plt.close(fig)
    print("wrote fig1_overview.png")


# =============================================================== radar
def fig_radar():
    apply_nature_style()
    import numpy as np
    import matplotlib.pyplot as plt

    best = best_backbone_r1()
    # representative lineup: 2 scaffolds, 1 control, 2 classical, 1 specialist
    show = [
        ("medagents", "MedAgents (LLM)", PALETTE[2], "-", "o"),
        ("llm_control", "LLM control", PALETTE[0], "-", "s"),
        ("deeprare", "DeepRare (specialist)", PALETTE[4], "-", "^"),
        ("lirical", "LIRICAL (classical)", PALETTE[3], "--", "D"),
        ("vc_rdagent", "VC-RDAgent (offline)", PALETTE[1], "--", "v"),
    ]
    axes_ds = DS_ORDER
    N = len(axes_ds)
    angles = [n / float(N) * 2 * np.pi for n in range(N)] + [0]

    fig, ax = plt.subplots(figsize=(6.6, 6.2), subplot_kw=dict(polar=True))
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_rlabel_position(0)
    ax.set_ylim(0, 0.5)
    ax.set_yticks([0.1, 0.2, 0.3, 0.4])
    ax.set_yticklabels(["0.1", "0.2", "0.3", "0.4"], fontsize=6.5, color="#888")
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels([DS_LABEL[d] for d in axes_ds], fontsize=7.6)
    ax.tick_params(axis="x", pad=8)
    ax.grid(color="#dddddd", linewidth=0.5)
    ax.spines["polar"].set_color("#cccccc")

    for agn, label, color, ls, mk in show:
        vals = [best.get((agn, d), 0.0) for d in axes_ds]
        vals += vals[:1]
        ax.plot(angles, vals, color=color, linewidth=1.6, linestyle=ls,
                marker=mk, markersize=4.5, label=label, zorder=3)
        if ls == "-":
            ax.fill(angles, vals, color=color, alpha=0.06, zorder=1)

    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.06), ncol=2,
              fontsize=7, frameon=False, handlelength=1.8)
    ax.set_title("Agent capability profile · best-backbone R@1 per data layer",
                 fontsize=9.5, fontweight="bold", pad=18)
    fig.savefig(FIG / "fig_radar.png")
    plt.close(fig)
    print("wrote fig_radar.png")


# =============================================================== self-preference
def fig_selfpref():
    apply_nature_style()
    import matplotlib.pyplot as plt

    # from Sec 7.5 Table (v1 Gemini/family judge -> v2 Claude/non-family judge)
    AXES = ["factual", "relevance", "depth", "faithful"]
    data = {
        "llm_control": ([4.70, 4.50, 3.60, 4.90], [4.30, 4.50, 3.10, 4.50], PALETTE[0]),
        "mdagents":    ([5.00, 5.00, 4.00, 5.00], [4.10, 4.17, 3.49, 4.26], PALETTE[2]),
        "deeprare":    ([1.70, 1.40, 1.90, 1.70], [2.31, 1.33, 2.58, 2.72], PALETTE[4]),
    }
    fig, axs = plt.subplots(1, 4, figsize=(11.0, 3.7), sharey=True)
    for j, (axname, ax) in enumerate(zip(AXES, axs)):
        for agn, (v1, v2, color) in data.items():
            ax.plot([0, 1], [v1[j], v2[j]], color=color, marker="o",
                    markersize=5, linewidth=1.6,
                    label=agn if j == 0 else None, zorder=3)
        ax.set_xlim(-0.35, 1.35)
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["v1\nGemini\n(family)", "v2\nClaude\n(non-family)"],
                           fontsize=6.8)
        ax.set_title(axname, fontsize=9, fontweight="bold")
        ax.set_ylim(1, 5.3)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.grid(axis="y", linewidth=0.4, color="#dddddd")
    axs[0].set_ylabel("LLM-judge score (1–5)")
    axs[0].legend(loc="lower left", fontsize=6.8, frameon=False)
    fig.suptitle("Self-preference bias: swapping to a non-family judge shrinks the "
                 "single-LLM lead (mdagents overtakes on depth)",
                 fontsize=9.5, fontweight="bold", y=1.02)
    fig.savefig(FIG / "fig_selfpref.png")
    plt.close(fig)
    print("wrote fig_selfpref.png")


# =============================================================== cost bar
def fig_costbar():
    apply_nature_style()
    import numpy as np
    import matplotlib.pyplot as plt

    # from Sec 6.3 per-backbone cost-per-prediction (2026-07-06 final)
    rows = [
        ("DS V4-Flash", 0.00040, PALETTE[2]),
        ("DS V4-Pro\n(reasoning-off)", 0.00088, PALETTE[5]),
        ("Gemini Flash", 0.00321, PALETTE[0]),
        ("GPT-5\n(minimal)", 0.00793, PALETTE[3]),
    ]
    labels = [r[0] for r in rows]
    vals = [r[1] for r in rows]
    colors = [r[2] for r in rows]

    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    x = np.arange(len(rows))
    bars = ax.bar(x, vals, color=colors, width=0.62, zorder=3)
    ax.set_yscale("log")
    ax.set_ylabel("USD per prediction (log scale)")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=7.4)
    ax.set_ylim(1e-4, 2e-2)
    ax.grid(axis="y", linewidth=0.4, color="#dddddd", zorder=0)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v * 1.12, f"${v:.5f}",
                ha="center", va="bottom", fontsize=7.0, fontweight="bold")
    # annotate the multiplier
    ax.text(3, 0.0102, "≈20× V4-Flash,\nno consistent R@1 edge",
            ha="center", va="bottom", fontsize=6.8, color=PALETTE[3])
    ax.text(0.02, 0.0135,
            "LIRICAL / VC-RDAgent classical baselines: $0 (not shown on log axis)",
            transform=ax.transData, fontsize=6.4, style="italic", color="#666")
    ax.set_title("Cost per prediction by backbone · >20× spread, "
                 "GPT-5 the outlier", fontsize=9.5, fontweight="bold")
    fig.savefig(FIG / "fig_costbar.png")
    plt.close(fig)
    print("wrote fig_costbar.png")


if __name__ == "__main__":
    FIG.mkdir(parents=True, exist_ok=True)
    fig1_overview()
    fig_radar()
    fig_selfpref()
    fig_costbar()
    print("all new figures written to", FIG)
