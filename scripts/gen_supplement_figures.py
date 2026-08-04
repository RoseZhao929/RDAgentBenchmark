"""Regenerate the five Supplementary figures in the paper house style
(scientific-figure-style skill): no on-canvas title, minimal axis labels (no
parentheses / no dumped info -- detail lives in the LaTeX caption), fixed
colorblind-safe palette, uniform serif font, despined axes, vector PDF + PNG.

Numbers are the frozen/main-text-authoritative values:
  H2  : LLM control .296->.494 (+20pp), DeepRare .22->.38 (+16pp)
  M4  : H8 bins .218/.276/.323/.253 (peak 16-30)
  H7  : per-organ LLM range + classical inversion on nervous / head-neck
  cost: per-prediction .00032/.00098/.00341/.00825 (main paper Table)
  A6  : literature-frequency Spearman rho per system
Output -> paper_final/Figure_supplementary/{png,pdf}.
"""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from _figstyle import apply_nature_style, EMNLP_PALETTE as PAL, BAR_EDGE, despine

OUT = ROOT / "paper_final" / "Figure_supplementary"
OUT.mkdir(parents=True, exist_ok=True)

C_LLM, C_ACC, C_CLS = PAL[0], PAL[1], PAL[2]   # blue / green / gold


def _save(fig, name):
    fig.savefig(OUT / f"{name}.pdf", bbox_inches="tight")
    fig.savefig(OUT / f"{name}.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("wrote", name)


# ---------------------------------------------------------- H2 genotype slopegraph
def fig_h2():
    apply_nature_style()
    fig, ax = plt.subplots(figsize=(6.4, 4.4))
    data = [("LLM control", 0.296, 0.494, C_LLM),
            ("DeepRare", 0.22, 0.38, C_ACC)]
    for name, p2, p3, col in data:
        ax.plot([0, 1], [p2, p3], "-", color=col, lw=3.0, marker="o", ms=12, zorder=3)
        ax.text(-0.05, p2, f"{p2:.2f}", ha="right", va="center", color=col)
        ax.text(1.05, p3, f"{p3:.2f}", ha="left", va="center", color=col)
        ax.text(1.05, p3 - 0.03, f"{name} (+{(p3 - p2) * 100:.0f} pp)",
                ha="left", va="top", color=col)
    ax.set_xlim(-0.35, 1.85)
    ax.set_ylim(0.15, 0.56)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["HPO only", "HPO + variants"])
    ax.set_ylabel("Recall@1")
    ax.grid(axis="y", alpha=0.4, zorder=0)
    despine(ax)
    fig.tight_layout()
    _save(fig, "figH2_genotype")


# ---------------------------------------------------------- M4 HPO-density inverted-U
def fig_m4():
    apply_nature_style()
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    bins = ["≤5", "6–15", "16–30", ">30"]
    r1 = [0.218, 0.276, 0.323, 0.253]
    peak = int(np.argmax(r1))
    x = np.arange(len(bins))
    cols = [C_ACC if i == peak else C_LLM for i in range(len(bins))]
    bars = ax.bar(x, r1, 0.62, color=cols, edgecolor=BAR_EDGE, linewidth=0.8, zorder=3)
    for b, v in zip(bars, r1):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.008, f"{v:.2f}",
                ha="center", va="bottom")
    ax.set_xticks(x)
    ax.set_xticklabels(bins)
    ax.set_xlabel("HPO terms per case")
    ax.set_ylabel("Recall@1")
    ax.set_ylim(0, 0.37)
    ax.grid(axis="y", alpha=0.4, zorder=0)
    despine(ax)
    fig.tight_layout()
    _save(fig, "figM4_hpo_density")


# ---------------------------------------------------------- H7 specialty blind spots
def fig_h7():
    apply_nature_style()
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    rows = [  # (specialty, llm_low, llm_high, classical or None)
        ("digestive", 0.09, 0.09, None),
        ("metabolism/homeostasis", 0.10, 0.16, None),
        ("nervous system", 0.11, 0.14, 0.39),
        ("cardiovascular", 0.41, 0.44, None),
        ("head/neck", 0.44, 0.44, 0.53),
        ("integument", 0.44, 0.56, None),
    ]
    y = np.arange(len(rows))
    mids = [(lo + hi) / 2 for _, lo, hi, _ in rows]
    errs = [[m - lo for m, (_, lo, hi, _) in zip(mids, rows)],
            [hi - m for m, (_, lo, hi, _) in zip(mids, rows)]]
    ax.errorbar(mids, y, xerr=errs, fmt="o", ms=9, color=C_LLM,
                ecolor=C_LLM, elinewidth=2, capsize=3, zorder=3, label="LLM systems")
    cx = [(c, yi) for (_, _, _, c), yi in zip(rows, y) if c is not None]
    ax.scatter([c for c, _ in cx], [yi for _, yi in cx], marker="D", s=90,
               color=C_CLS, edgecolor=BAR_EDGE, lw=0.7, zorder=4, label="Classical")
    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in rows])
    ax.set_xlabel("Recall@1")
    ax.set_xlim(0, 0.62)
    ax.legend(loc="lower right", frameon=False)
    ax.grid(axis="x", alpha=0.4, zorder=0)
    despine(ax)
    fig.tight_layout()
    _save(fig, "fig7_specialty_h7")


# ---------------------------------------------------------- cost per prediction (log)
def fig_cost():
    apply_nature_style()
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    labels = ["V4-Flash", "V4-Pro", "Gemini 3 Flash", "GPT-5 minimal"]
    cost = [0.00032, 0.00098, 0.00341, 0.00825]   # main-paper authoritative
    cols = [C_ACC, PAL[3], C_LLM, C_CLS]
    x = np.arange(len(labels))
    bars = ax.bar(x, cost, 0.6, color=cols, edgecolor=BAR_EDGE, lw=0.8, zorder=3)
    ax.set_yscale("log")
    for b, v in zip(bars, cost):
        ax.text(b.get_x() + b.get_width() / 2, v * 1.08, f"${v:.5f}",
                ha="center", va="bottom", fontsize=13)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("USD per prediction")
    ax.set_ylim(1e-4, 2e-2)
    ax.grid(axis="y", alpha=0.4, zorder=0)
    despine(ax)
    fig.tight_layout()
    _save(fig, "fig_costbar")


# ---------------------------------------------------------- A6 contamination audit
def fig_a6():
    apply_nature_style()
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    rows = [  # (label, rho, is_llm)
        ("Gemini 3 Flash", 0.365, True),
        ("GPT-5 minimal", 0.354, True),
        ("DeepSeek V4-Flash", 0.348, True),
        ("DeepSeek V4-Pro", 0.294, True),
        ("VC-RDAgent", -0.059, False),
        ("LIRICAL", -0.155, False),
    ]
    y = np.arange(len(rows))[::-1]
    for (lab, rho, is_llm), yi in zip(rows, y):
        col = C_LLM if is_llm else C_CLS
        ax.plot([0, rho], [yi, yi], color="#BBB", lw=2, zorder=1)
        ax.scatter(rho, yi, s=95, color=col, edgecolor=BAR_EDGE, lw=0.7, zorder=3)
        off = 0.02 if rho >= 0 else -0.02
        ax.text(rho + off, yi, f"{rho:.2f}", va="center",
                ha="left" if rho >= 0 else "right")
    ax.axvline(0, color=BAR_EDGE, lw=0.8, zorder=2)
    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in rows])
    ax.set_xlabel("Spearman ρ")
    ax.set_xlim(-0.32, 0.5)
    ax.grid(axis="x", alpha=0.4, zorder=0)
    despine(ax)
    fig.tight_layout()
    _save(fig, "fig4_a6_contamination_scatter")


if __name__ == "__main__":
    fig_h2()
    fig_m4()
    fig_h7()
    fig_cost()
    fig_a6()
    print("all supplement figures regenerated in", OUT)
