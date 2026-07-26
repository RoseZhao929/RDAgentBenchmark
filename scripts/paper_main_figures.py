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
  figM5_selfpref           P5 judge-swap / family-relation sensitivity
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
from _figstyle import (apply_nature_style, EMNLP_PALETTE as PALETTE, BAR_EDGE,  # noqa: E402
                       PANEL_FIGSIZE, despine)

FIG = ROOT / "data/round2/figures"
MANIFEST = ROOT / "audit_frozen/frozen_main_manifest.csv"
COST = ROOT / "audit_frozen/cost_summary.csv"
P5 = ROOT / "audit_frozen/_p5_same_trace_report.json"

CLASSICAL = {"lirical", "vc_rdagent"}

# Consistent colours for the two agent families across every figure (EMNLP palette).
C_LLM = PALETTE[0]        # blue  = LLM-scaffolded agents
C_CLASSICAL = PALETTE[2]  # gold  = classical / offline baselines
C_ACCENT = PALETTE[1]     # green accent (peaks / highlights)


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

    # This is a LLM-vs-classical comparison, so it shows ONLY the two HPO-input
    # layers where a classical/offline baseline can actually run (both bars
    # present). The three layers with no classical run — RareArena (free-text),
    # MIMIC (structured EHR) and the PMC temporal holdout — are explained in the
    # caption rather than shown as half-empty groups.
    layers = [("phenopacket_store", "Phenopacket-Store"),
              ("rarebench", "RareBench HF")]
    best = best_per_family(rows, {l[0] for l in layers})

    llm = [best.get((l[0], "llm"), (0,))[0] for l in layers]
    cls = [best.get((l[0], "classical"), (None,))[0] for l in layers]

    # squeezed: narrower canvas + tighter bar spacing so the two groups don't
    # float in whitespace.
    fig, ax = plt.subplots(figsize=(5.6, 4.6))
    x = np.arange(len(layers)) * 0.78
    w = 0.32
    b1 = ax.bar(x - w / 2, llm, w, label="Best LLM", color=C_LLM,
                edgecolor=BAR_EDGE, linewidth=0.7, zorder=3)
    cls_x, cls_v = [], []
    for i, c in enumerate(cls):
        if c is not None:
            cls_x.append(x[i] + w / 2)
            cls_v.append(c)
    b2 = ax.bar(np.array(cls_x), cls_v, w, label="Best classical",
                color=C_CLASSICAL, edgecolor=BAR_EDGE, linewidth=0.7, zorder=3)

    def label(bars):
        for b in bars:
            h = b.get_height()
            ax.text(b.get_x() + b.get_width() / 2, h + 0.008, f"{h:.2f}",
                    ha="center", va="bottom", fontsize=15)
    label(b1)
    label(b2)

    # gap annotation on PP-Store: sits in the gap to the RIGHT of the 0.30 label,
    # between the blue and gold bars.
    if cls[0] is not None:
        gap = (cls[0] - llm[0]) * 100
        gx = x[0] + w / 2 - 0.015        # right edge of blue bar / left of gold
        ax.annotate("", xy=(gx, cls[0]), xytext=(gx, llm[0]),
                    arrowprops=dict(arrowstyle="<->", color="#333", lw=1.4))
        ax.text(gx + 0.03, (cls[0] + llm[0]) / 2 + 0.03, f"+{gap:.0f} pp",
                fontsize=15, color="#333", va="center", ha="left")

    ax.set_xticks(x)
    ax.set_xticklabels([l[1] for l in layers])
    ax.set_ylabel("R@1")
    ax.set_xlim(x[0] - 0.42, x[-1] + 0.42)
    ax.set_ylim(0, 0.56)
    ax.legend(loc="upper right", frameon=False, handlelength=1.1,
              handletextpad=0.5, labelspacing=0.3, borderaxespad=0.2)
    ax.grid(axis="y", zorder=0)
    despine(ax)
    fig.tight_layout()
    fig.savefig(FIG / "figM1_llm_vs_classical.png")
    plt.close(fig)
    print("wrote figM1_llm_vs_classical.png (V1)",
          f"[PP {llm[0]:.3f}v{cls[0]:.3f}, RB {llm[1]:.3f}v{cls[1]:.3f}]")


def _best_r1_with_r5(rows, ds, fam, min_n=100):
    """The R@1-best system for (dataset, family), plus that same system's R@5.
    Returns (r1, r5, system). Stacking R@5 above R@1 for the SAME system keeps
    the two layers honest (not a max over different systems)."""
    b1 = None
    for r in rows:
        if r["dataset"] != ds or r["n_attempted"] < min_n:
            continue
        f = "classical" if r["system"] in CLASSICAL else "llm"
        if f != fam:
            continue
        if b1 is None or r["R@1_variant_aware"] > b1["R@1_variant_aware"]:
            b1 = r
    if b1 is None:
        return None
    r5 = float(b1["R@5_variant_aware"])
    return (b1["R@1_variant_aware"], r5, b1["system"])


# =============================== M1 Version 2a: R@1 + R@5 layered (stacked) =====
def figM1_v2a_layered(rows):
    apply_nature_style()
    import matplotlib.pyplot as plt
    import numpy as np
    BIG = 15   # in-bar value labels; matches the shared base font

    layers = [("phenopacket_store", "Phenopacket-Store"),
              ("rarebench", "RareBench HF")]
    fams = [("llm", "LLM", C_LLM), ("classical", "classical", C_CLASSICAL)]

    # slightly smaller canvas than the other panels: this figure has little
    # content, so a smaller box keeps the (shared-size) fonts looking large
    # rather than lost in whitespace when scaled into the 2x3 composite.
    fig, ax = plt.subplots(figsize=(5.8, 5.0))
    x = np.arange(len(layers)) * 1.1          # datasets a bit closer together
    w = 0.19                                  # narrow bars (near M6 width)
    gap = 0.06                                # small gap between blue/gold pair
    offs = {"llm": -(w / 2 + gap / 2), "classical": (w / 2 + gap / 2)}
    # lighter shade for the R@1->R@5 increment
    def lighten(hexc, f=0.5):
        c = hexc.lstrip("#"); r, g, b = (int(c[i:i+2], 16) for i in (0, 2, 4))
        return "#%02x%02x%02x" % tuple(int(v + (255 - v) * f) for v in (r, g, b))

    for fam, flabel, fcolor in fams:
        r1s, lifts = [], []
        for ds, _ in layers:
            got = _best_r1_with_r5(rows, ds, fam)
            r1s.append(got[0]); lifts.append(got[1] - got[0])
        xb = x + offs[fam]
        ax.bar(xb, r1s, w, color=fcolor, edgecolor=BAR_EDGE, linewidth=0.7,
               zorder=3, label=f"{flabel} R@1")
        # the light upper segment is the R@1->R@5 increment (its top = R@5); the
        # caption explains the stacking. Legend reads "R@5 gain".
        ax.bar(xb, lifts, w, bottom=r1s, color=lighten(fcolor), edgecolor=BAR_EDGE,
               linewidth=0.7, zorder=3, label=f"{flabel} R@5 gain")
        for xi, r1, lift in zip(xb, r1s, lifts):
            ax.text(xi, r1 / 2, f"{r1:.2f}", ha="center", va="center",
                    fontsize=BIG, color="white")
            ax.text(xi, r1 + lift + 0.01, f"{r1+lift:.2f}", ha="center",
                    va="bottom", fontsize=BIG)

    ax.set_xticks(x)
    ax.set_xticklabels([l[1] for l in layers])
    ax.set_xlabel("Dataset")
    ax.set_ylabel("Recall@$k$")
    # headroom just above the tallest bar (0.62) for a 2-row legend strip that
    # sits close to the bars, not floating far above them.
    # extra headroom inside the axes so the 2-row legend sits just above the
    # tallest bar's 0.62 label, not floating far above it.
    # headroom for the legend above the bars, but the y-axis SPINE is truncated
    # at 0.65 so it doesn't stick up empty above the data.
    # more top headroom so the legend sits fully ABOVE the 0.62 bar label
    ax.set_ylim(0, 0.88)
    ax.set_yticks([0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    ax.set_xlim(x[0] - 0.4, x[-1] + 0.4)
    ax.legend(loc="upper center", frameon=False, ncol=2,
              bbox_to_anchor=(0.5, 1.0), handlelength=1.1, handletextpad=0.5,
              columnspacing=1.4, labelspacing=0.25)
    ax.grid(axis="y", zorder=0)
    despine(ax)
    ax.spines["left"].set_bounds(0, 0.65)   # cut the empty upper spine stub
    fig.tight_layout()
    fig.savefig(FIG / "figM1_v2a_layered.png")
    plt.close(fig)
    print("wrote figM1_v2a_layered.png")


# =============================== M1 Version 2b: R@1 | R@5 four-group dual bar ===
def figM1_v2b_dual(rows):
    apply_nature_style()
    import matplotlib.pyplot as plt
    import numpy as np

    layers = [("phenopacket_store", "Phenopacket-Store"),
              ("rarebench", "RareBench HF")]
    # two metric blocks side by side per dataset: R@1 block, R@5 block
    metrics = [("R@1_variant_aware", "R@1"), ("R@5_variant_aware", "R@5")]

    def bestval(ds, fam, metric):
        b = None
        for r in rows:
            if r["dataset"] != ds or r["n_attempted"] < 100:
                continue
            f = "classical" if r["system"] in CLASSICAL else "llm"
            if f != fam:
                continue
            v = float(r[metric])
            if b is None or v > b:
                b = v
        return b

    fig, ax = plt.subplots(figsize=(7.6, 4.8))
    group_w = 1.0
    x = np.arange(len(layers)) * 2.2
    w = 0.42
    # within a dataset: [LLM R@1, cls R@1]  gap  [LLM R@5, cls R@5]
    positions = {"llm": {"R@1_variant_aware": -1.5 * w, "R@5_variant_aware": 0.6 * w},
                 "classical": {"R@1_variant_aware": -0.5 * w, "R@5_variant_aware": 1.6 * w}}
    fam_color = {"llm": C_LLM, "classical": C_CLASSICAL}
    seen = set()
    for fam in ("llm", "classical"):
        for metric, mlab in metrics:
            xs, vs = [], []
            for i, (ds, _) in enumerate(layers):
                v = bestval(ds, fam, metric)
                xs.append(x[i] + positions[fam][metric]); vs.append(v)
            lab = {"llm": "Best LLM", "classical": "Best classical"}[fam]
            ax.bar(xs, vs, w, color=fam_color[fam], edgecolor=BAR_EDGE,
                   linewidth=0.7, zorder=3,
                   label=lab if lab not in seen else None)
            seen.add(lab)
            for xi, v in zip(xs, vs):
                ax.text(xi, v + 0.008, f"{v:.2f}", ha="center", va="bottom",
                        fontsize=15)
    # metric-block labels under each block
    for i, (ds, dslab) in enumerate(layers):
        ax.text(x[i] - w, -0.055, "R@1", ha="center", va="top", fontsize=15,
                color="#555", transform=ax.transData)
        ax.text(x[i] + 1.1 * w, -0.055, "R@5", ha="center", va="top", fontsize=15,
                color="#555", transform=ax.transData)
    ax.set_xticks(x + 0.05 * w)
    ax.set_xticklabels([l[1] for l in layers])
    ax.tick_params(axis="x", pad=22)
    ax.set_ylabel("Recall@$k$")
    ax.set_ylim(0, 0.68)
    ax.set_xlim(x[0] - 2.2 * w, x[-1] + 2.4 * w)
    ax.legend(loc="upper right", frameon=False, handlelength=1.1,
              handletextpad=0.5, labelspacing=0.3)
    ax.grid(axis="y", zorder=0)
    despine(ax)
    fig.tight_layout()
    fig.savefig(FIG / "figM1_v2b_dual.png")
    plt.close(fig)
    print("wrote figM1_v2b_dual.png")


# =========================================================== M2: cost-accuracy
def figM2_cost_accuracy(rows, variant="A", outfile="figM2_cost_accuracy.png"):
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

    # slightly wider canvas so the single-column Agent legend fits in the empty
    # lower-right corner without touching any point.
    fig, ax = plt.subplots(figsize=(6.8, 5.0))
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
                   marker=bb_short[k][1], s=170, alpha=0.92,
                   edgecolors=BAR_EDGE, linewidths=0.8, zorder=3)

    # Pareto frontier (max acc at or below each cost)
    front, best = [], -1
    for cost, acc in sorted(pts):
        if acc > best:
            best = acc
            front.append((cost, acc))
    if front:
        ax.step([p[0] for p in front], [p[1] for p in front], where="post",
                color="#333", lw=1.6, ls="--", zorder=2)

    ax.set_xscale("log")
    ax.set_xlabel("Cost per attempt")
    ax.set_ylabel("R@1, Phenopacket-Store")
    ax.grid(True, which="major", zorder=0)
    ag_h = [Line2D([0], [0], marker="o", color="w", markerfacecolor=ag_color[a],
                   markersize=12, label=a, linestyle="") for a in agents]
    bb_h = [Line2D([0], [0], marker=m, color="#555", ls="", markersize=12,
                   label=lab) for lab, m in bb_short.values()]
    bb_h.append(Line2D([0], [0], color="#333", ls="--", label="Pareto frontier"))

    ax.set_ylim(0, 0.31)
    # Only the Agent (colour) legend is drawn, compactly in the bottom-left
    # corner. The Backbone (marker-shape) key -- circle=Gemini Flash,
    # square=DS V4-Pro, triangle=DS V4-Flash, diamond=GPT-5 minimal -- is given
    # in the caption instead, since two legends do not fit this narrow panel.
    # Agent legend as a narrow 2-col x 3-row block in the bottom-left corner;
    # only two columns wide, so it does not reach the mid-plot maidxo point.
    ax.legend(handles=ag_h, title="Agent", loc="lower left", ncol=2,
              frameon=False, handletextpad=0.0, columnspacing=0.1,
              labelspacing=0.12, borderaxespad=0.1, bbox_to_anchor=(-0.05, -0.02))
    despine(ax)
    fig.tight_layout()
    fig.savefig(FIG / outfile)
    plt.close(fig)
    print(f"wrote {outfile} (variant {variant})")


# =========================================================== M3: prevalence H1
def figM3_prevalence():
    # frozen H1 tier values (paper_sections/7_2_7_3_7_4_analysis.md §7.7)
    apply_nature_style()
    import matplotlib.pyplot as plt
    # scale fonts up to match panel (a) in the composite
    plt.rcParams.update({
        "font.size": 20, "axes.titlesize": 20, "axes.labelsize": 20,
        "xtick.labelsize": 20, "ytick.labelsize": 20, "legend.fontsize": 20,
    })

    tiers = ["common-rare", "moderate", "ultra-rare", "super-rare"]
    llm = [0.37, 0.26, 0.39, 0.22]
    cls = [0.30, 0.23, 0.33, 0.50]

    fig, ax = plt.subplots(figsize=PANEL_FIGSIZE)
    ax.plot(tiers, llm, "o-", color=C_LLM, lw=2.4, ms=11, label="LLM agents")
    ax.plot(tiers, cls, "s--", color=C_CLASSICAL, lw=2.4, ms=11,
            label="Classical / offline")
    # value labels: generically LLM-above / classical-below (they separate at
    # every tier except the super-rare crossover, where the order flips, so the
    # rightmost tier is special-cased: classical 0.50 above, LLM 0.22 below —
    # keeping the gap arrow between them clear of both numbers).
    n = len(tiers)
    # nudge the leftmost tier's labels rightward so they clear the y-axis
    dx0 = 0.12
    for i, (xi, yi) in enumerate(zip(tiers, llm)):
        below = (i == n - 1)
        off = dx0 if i == 0 else 0.0
        ax.text(i + off, yi + (-0.022 if below else 0.022), f"{yi:.2f}",
                ha="center", va="top" if below else "bottom",
                fontsize=18, color=C_LLM)
    for i, (xi, yi) in enumerate(zip(tiers, cls)):
        above = (i == n - 1)
        off = dx0 if i == 0 else 0.0
        ax.text(i + off, yi + (0.022 if above else -0.024), f"{yi:.2f}",
                ha="center", va="bottom" if above else "top",
                fontsize=18, color="#9a7016")
    # crossover gap on the rarest tier, label hugging the (right-edge) line
    gap = (cls[-1] - llm[-1]) * 100
    ax.annotate("", xy=(n - 1, cls[-1]), xytext=(n - 1, llm[-1]),
                arrowprops=dict(arrowstyle="<->", color="#333", lw=1.4))
    ax.text(n - 1 - 0.06, (cls[-1] + llm[-1]) / 2, f"+{gap:.0f} pp",
            fontsize=18, color="#333", ha="right", va="center")
    ax.set_xlabel("Prevalence tier")
    ax.set_ylabel("Pooled R@1")
    # gently rotate the long tier names (kept centered on each tick) so they
    # don't overlap in the narrow panel
    ax.set_xticks(range(len(tiers)))
    ax.set_xticklabels(tiers, rotation=10, ha="center")
    ax.set_ylim(0.15, 0.56)
    # legend inside the upper-left empty band (below 0.50), clear of both curves
    # which sit at <=0.39 on the left half.
    ax.legend(loc="upper left", frameon=False, ncol=1, handlelength=1.8,
              handletextpad=0.5, labelspacing=0.35, bbox_to_anchor=(0.02, 0.99))
    ax.grid(True, zorder=0)
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

    # Four bars, peak highlighted. Axis parentheticals and per-bin n live in the
    # caption, not on the figure.
    fig, ax = plt.subplots(figsize=(7.0, 4.7))
    x = np.arange(len(bins))
    peak = int(np.argmax(r1))
    colors = [C_ACCENT if i == peak else C_LLM for i in range(len(bins))]
    bars = ax.bar(x, r1, 0.62, color=colors, edgecolor=BAR_EDGE, linewidth=0.8,
                  zorder=3)
    for b, v, i in zip(bars, r1, range(len(bins))):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.008, f"{v:.2f}",
                ha="center", va="bottom", fontsize=15,
                fontweight="bold" if i == peak else "normal",
                color=C_ACCENT if i == peak else "#333")
    ax.set_xticks(x)
    ax.set_xticklabels(bins)
    ax.set_xlabel("HPO terms per case")
    ax.set_ylabel("Pooled R@1")
    ax.set_ylim(0, 0.38)
    ax.grid(axis="y", zorder=0)
    despine(ax)
    fig.tight_layout()
    fig.savefig(FIG / "figM4_hpo_density.png")
    plt.close(fig)
    print("wrote figM4_hpo_density.png")


# =============================== candidate: F2 scaffolding ladder ==============
def figF2_scaffolding(rows):
    """Scaffolding ladder on PP-Store, Gemini Flash: single-LLM control vs the
    multi-agent scaffolds. Shows F2 — deepening the scaffold does not reliably
    beat the no-scaffold control (mdagents sits BELOW it; agentclinic/maidxo
    collapse). Bars coloured by whether they clear the control line."""
    apply_nature_style()
    import matplotlib.pyplot as plt
    import numpy as np
    # scale fonts up to match panel (a) in the composite
    plt.rcParams.update({
        "font.size": 20, "axes.titlesize": 20, "axes.labelsize": 20,
        "xtick.labelsize": 20, "ytick.labelsize": 20,
    })
    BIG = 20

    ladder = ["llm_control", "mdagents", "medagents", "agentclinic", "maidxo"]
    disp = {"llm_control": "LLM control\n(no scaffold)", "mdagents": "MDAgents",
            "medagents": "MedAgents", "agentclinic": "AgentClinic",
            "maidxo": "MAI-DxO"}
    val = {}
    for ag in ladder:
        for r in rows:
            if (r["dataset"] == "phenopacket_store" and r["system"] == ag
                    and r["backbone"].startswith("google_gemini")):
                val[ag] = r["R@1_variant_aware"]
    ctrl = val["llm_control"]
    # dumbbell / lollipop of the scaffold's DELTA vs the no-scaffold control:
    # zero line = control; positive (green, right) beats it, negative (gold,
    # left) trails it. Far more legible than five near-equal bars.
    scaffolds = ladder[1:]                      # exclude the control itself
    deltas = [(val[a] - ctrl) * 100 for a in scaffolds]   # in pp
    # order worst-to-best so the collapse is visually anchored at the bottom
    order = sorted(range(len(scaffolds)), key=lambda i: deltas[i])
    scaffolds = [scaffolds[i] for i in order]
    deltas = [deltas[i] for i in order]

    fig, ax = plt.subplots(figsize=PANEL_FIGSIZE)
    y = np.arange(len(scaffolds))
    for yi, d in zip(y, deltas):
        col = C_ACCENT if d >= 0 else C_CLASSICAL
        ax.plot([0, d], [yi, yi], color=col, lw=3.0, zorder=2,
                solid_capstyle="round")
        ax.scatter([d], [yi], s=280, color=col, edgecolors=BAR_EDGE,
                   linewidths=1.0, zorder=3)
        # Small near-zero deltas (top two rows) label to the LEFT of the marker
        # (above would collide with the control-line text); the two large
        # negative deltas keep their label above the marker.
        if abs(d) < 4:
            ax.text(d - 1.2, yi, f"{d:+.1f} pp", va="center", ha="right",
                    fontsize=BIG, color="#333")
        else:
            ax.text(d, yi + 0.18, f"{d:+.1f} pp", va="bottom", ha="center",
                    fontsize=BIG, color="#333")
    ax.axvline(0, color=C_LLM, lw=2.2, zorder=1)
    # label the control line as a single horizontal row above the top marker,
    # right-aligned to the zero line so it stays inside the frame.
    ax.text(-0.5, len(scaffolds) - 0.35, "no-scaffold control", ha="right",
            va="bottom", fontsize=BIG, color=C_LLM)
    ax.set_yticks(y)
    ax.set_yticklabels([disp[a].replace("\n", " ") for a in scaffolds],
                       fontsize=BIG)
    ax.set_xlabel("R@1 change vs. single-LLM control")
    ax.set_xlim(min(deltas) - 9, 8)
    ax.set_ylim(-0.6, len(scaffolds) - 0.1)
    ax.grid(axis="x", zorder=0)
    despine(ax)
    fig.tight_layout()
    fig.savefig(FIG / "figF2_scaffolding.png")
    plt.close(fig)
    print("wrote figF2_scaffolding.png",
          f"[ctrl {ctrl:.3f}; deltas {[round(d,1) for d in deltas]}]")


# =============================== candidate: H2 genotype channel lift ===========
def figH2_genotype(rows=None):
    """H2 — adding a structured-variant (genotype) block lifts R@1 by ~20 pp for
    ANY agent that ingests it, not just DeepRare. Slopegraph P2 (HPO-only) -> P3
    (HPO + variants), frozen §7.3 (llm_control n=500 paired; deeprare n=50)."""
    apply_nature_style()
    import matplotlib.pyplot as plt

    data = [  # (agent, P2, P3, color)
        ("LLM control", 0.296, 0.494, C_LLM),
        ("DeepRare", 0.22, 0.38, C_ACCENT),
    ]
    fig, ax = plt.subplots(figsize=(6.4, 4.8))
    for name, p2, p3, col in data:
        ax.plot([0, 1], [p2, p3], "-", color=col, lw=3.0, marker="o", ms=13,
                zorder=3)
        ax.text(-0.05, p2, f"{p2:.2f}", ha="right", va="center", fontsize=15,
                color=col)
        ax.text(1.05, p3, f"{p3:.2f}", ha="left", va="center", fontsize=15,
                color=col)
        # agent name + lift near the right end
        ax.text(1.05, p3 - 0.028, f"{name}  (+{(p3-p2)*100:.0f} pp)", ha="left",
                va="top", fontsize=15, color=col)
    ax.set_xlim(-0.35, 1.75)
    ax.set_ylim(0.15, 0.56)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["HPO only\n(P2)", "HPO + variants\n(P3)"], fontsize=15)
    ax.set_ylabel("R@1")
    ax.grid(axis="y", zorder=0)
    despine(ax)
    fig.tight_layout()
    fig.savefig(FIG / "figH2_genotype.png")
    plt.close(fig)
    print("wrote figH2_genotype.png")


# =========================================================== M5: judge-swap sensitivity
def figM5_selfpref():
    # Frozen §7.5 table: v1 Gemini (same-family) -> v2 Claude
    # (cross-family), same axes. Judge identity and family relation change
    # together in every line. Only llm_control + deeprare preserve the traces;
    # mdagents additionally changes trace completeness and is drawn dashed.
    apply_nature_style()
    import matplotlib.pyplot as plt
    # four narrow sub-panels shrink text in the composite; scale fonts up ~1.5x
    # so this panel matches panel (a).
    plt.rcParams.update({
        "font.size": 22, "axes.titlesize": 22, "axes.labelsize": 22,
        "xtick.labelsize": 22, "ytick.labelsize": 22, "legend.fontsize": 22,
    })

    axes_names = ["factual", "relevance", "depth", "faithful"]
    data = {
        "llm_control": ([4.70, 4.50, 3.60, 4.90], [4.30, 4.50, 3.10, 4.50], C_LLM),
        "mdagents":    ([5.00, 5.00, 4.00, 5.00], [4.10, 4.17, 3.49, 4.26], PALETTE[3]),
        "deeprare":    ([1.70, 1.40, 1.90, 1.70], [2.31, 1.33, 2.58, 2.72], PALETTE[1]),
    }
    # 2x2 layout -> near-square canvas that fills the composite cell (no
    # letterbox), so this panel is as tall as the D/F panels.
    fig, axs = plt.subplots(2, 2, figsize=(7.4, 5.6), sharey=True, sharex=True)
    axs = axs.flatten()
    for j, (axname, ax) in enumerate(zip(axes_names, axs)):
        for agn, (v1, v2, color) in data.items():
            trace_repaired = agn == "mdagents"
            label = f"{agn}*" if trace_repaired else agn
            ax.plot([0, 1], [v1[j], v2[j]], color=color,
                    marker="s" if trace_repaired else "o", ms=10,
                    lw=2.6, ls="--" if trace_repaired else "-",
                    label=label if j == 0 else None, zorder=3)
        ax.set_xlim(-0.45, 1.45)
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["SF", "CF"])
        ax.set_title(axname)
        ax.set_ylim(1, 5.4)
        despine(ax)
        ax.grid(axis="y", zorder=0)
    # one shared, vertically-centered y-axis label for the whole 2x2 block
    fig.supylabel("LLM-judge score", fontsize=22)
    # legend as one narrow horizontal strip across the top (tight handle/column
    # gaps so it stays within the panel width).
    handles, labels = axs[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=3, frameon=False,
               bbox_to_anchor=(0.5, 1.03), handlelength=0.8, handletextpad=0.2,
               columnspacing=0.5)
    fig.tight_layout(rect=(0.02, 0, 1, 0.94))
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
    # scale fonts up to match panel (a) in the composite
    plt.rcParams.update({
        "font.size": 20, "axes.titlesize": 20, "axes.labelsize": 20,
        "xtick.labelsize": 20, "ytick.labelsize": 20,
    })

    # Vertical bars, hypotheses on the x-axis (rotated labels). The raw
    # -log10(p) spans 1.4 to 68, which leaves a huge empty mid-band; we CAP the
    # y-axis (broken-axis style) so bar heights stay comparable, and print the
    # true statistic on top of each bar. Full wording of each Hn is in caption.
    # (code, statistic value as bare number, Holm-adj p, survives). Whether each
    # number is a z or a Spearman rho is stated in the caption (H1/H8/H2/H4 are
    # z; H7/H10 are rho).
    H = [
        ("H1", "17.5", 2.2e-68, True),
        ("H8", "12.6", 7.8e-36, True),
        ("H2", "6.4", 3.0e-10, True),
        ("H7", "0.92", 1.6e-03, True),
        ("H4", "2.6", 9.0e-03, True),
        ("H10", "0.35", 3.7e-02, False),
    ]
    H = sorted(H, key=lambda h: h[2])                 # most to least significant
    codes = [h[0] for h in H]
    neglogp = [-np.log10(h[2]) for h in H]
    CAP = 14.0                                        # broken-axis cap
    shown = [min(v, CAP) for v in neglogp]
    x = np.arange(len(H))

    fig, ax = plt.subplots(figsize=PANEL_FIGSIZE)
    colors = [C_ACCENT if h[3] else C_CLASSICAL for h in H]
    bars = ax.bar(x, shown, 0.5, color=colors, edgecolor=BAR_EDGE,
                  linewidth=0.8, zorder=3)
    # True statistic printed on top of each bar. Bars taller than CAP are
    # truncated (their true value is printed, so no info is lost); the
    # significance threshold and the meaning of z/rho live in the caption.
    for xi, (v, sv, h) in enumerate(zip(neglogp, shown, H)):
        ax.text(xi, sv + 0.3, h[1], ha="center", va="bottom", fontsize=20,
                color="#333")
    ax.set_xticks(x)
    ax.set_xticklabels(codes, rotation=0, fontsize=20)
    ax.set_xlabel("Pre-registered hypothesis")
    ax.set_ylabel(r"$-\log_{10}$(Holm-adj. $p$)")
    ax.set_ylim(0, CAP + 1.5)
    ax.set_xlim(-0.6, len(H) - 0.4)
    ax.grid(axis="y", zorder=0)
    despine(ax)
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
                ha="left" if r[1] >= 0 else "right", fontsize=15, color="#333")
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=15)
    ax.set_xlabel("Spearman ρ (log pre-cutoff PubMed mentions vs. per-disease R@1)")
    ax.set_xlim(-0.32, 0.55)
    ax.set_title("Literature-frequency audit: LLM ρ≈0.3; classical controls "
                 "near zero", fontsize=15)
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
    ax.errorbar(mids, y, xerr=errs, fmt="o", ms=6, color=C_LLM,
                ecolor="#33506e", elinewidth=1.4, capsize=3, zorder=3,
                label="LLM midpoint (whisker = scaffold range)")
    for yi, s in enumerate(specs):
        if s[3] is not None:
            ax.scatter([s[3]], [yi], marker="D", s=46, color=C_CLASSICAL,
                       zorder=4, edgecolors="white", linewidths=0.5)
    ax.scatter([], [], marker="D", s=46, color=C_CLASSICAL,
               label="classical baseline (where it inverts)")
    ax.set_yticks(y)
    ax.set_yticklabels([s[0] for s in specs], fontsize=15)
    ax.set_xlabel("R@1 by modal HPO organ system")
    ax.set_xlim(0, 0.62)
    ax.set_title("Shared cross-agent specialty blind spots (H7); classical "
                 "inverts on nervous/head-neck", fontsize=15)
    ax.legend(loc="lower right", fontsize=15)
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
