"""Introduction-figure candidates for RareAgentBench.

A  : concept — fragmented benchmarks (each agent -> its own case set / ontology
     / scorer) collapsing into one shared CanonicalCase evaluation surface.
B  : data — the SAME single-LLM control's Recall@1 swings across evaluation
     settings (datasets), so a headline number reflects the setting, not the
     agent.
AB : A on top, B strip below.

Vector PDF + PNG to paper_aaai27_collab/Figures_intro/.
"""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from _figstyle import apply_nature_style, EMNLP_PALETTE as PAL, BAR_EDGE, despine

OUT = ROOT / "paper_aaai27_collab" / "Figures_intro"
OUT.mkdir(parents=True, exist_ok=True)

C_LLM, C_ACC, C_CLS = PAL[0], PAL[1], PAL[2]
GREY = "#8A8A8A"

def _save(fig, name):
    fig.savefig(OUT / f"{name}.png", dpi=300, bbox_inches="tight")
    fig.savefig(OUT / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)
    print("wrote", name)


# ------------------------------------------------------------------ A: concept
def fig_A(ax=None):
    own = ax is not None
    if not own:
        apply_nature_style(); fig, ax = plt.subplots(figsize=(7.4, 3.2))
    ax.set_xlim(0, 10); ax.set_ylim(0, 6); ax.axis("off")
    # left: fragmented — 4 agents each to its own mismatched bench
    agents = ["MedAgents", "MDAgents", "DeepRare", "MAI-DxO"]
    benches = ["case set A\nontology X", "case set B\nontology Y",
               "case set C\nscorer P", "case set D\nscorer Q"]
    ay = [5.2, 3.8, 2.4, 1.0]
    for i, (a, b, y) in enumerate(zip(agents, benches, ay)):
        ax.add_patch(FancyBboxPatch((0.2, y-0.35), 1.7, 0.7,
                     boxstyle="round,pad=0.03", fc=C_LLM, ec=BAR_EDGE, lw=0.8))
        ax.text(1.05, y, a, ha="center", va="center", color="white",
                fontsize=9, fontweight="bold")
        ax.add_patch(FancyBboxPatch((3.0, y-0.4), 1.9, 0.8,
                     boxstyle="round,pad=0.03", fc="#EDE3CF", ec=C_CLS, lw=0.8))
        ax.text(3.95, y, b, ha="center", va="center", color="#5a4a1a", fontsize=7)
        ax.add_patch(FancyArrowPatch((1.95, y), (2.95, y),
                     arrowstyle="-|>", mutation_scale=10, color=GREY, lw=1.0))
    ax.text(2.5, 5.9, "Fragmented: not comparable", ha="center",
            fontsize=9.5, fontweight="bold", color="#333")
    # big arrow to the right
    ax.add_patch(FancyArrowPatch((5.1, 3.1), (6.3, 3.1), arrowstyle="-|>",
                 mutation_scale=22, color="#333", lw=2.2))
    ax.text(5.7, 3.5, "RareAgentBench", ha="center", fontsize=8, color="#333")
    # right: unified surface
    ax.add_patch(FancyBboxPatch((6.5, 0.7), 3.2, 4.8,
                 boxstyle="round,pad=0.05", fc="#EAF0F8", ec=C_LLM, lw=1.4))
    ax.text(8.1, 5.05, "Shared \\texttt{CanonicalCase}", ha="center",
            fontsize=9, fontweight="bold", color=C_LLM)
    for j, t in enumerate(["one schema, five sources",
                           "same cases \\& ontologies",
                           "fixed matching \\& failures",
                           "backbone held constant"]):
        ax.text(6.7, 4.4-j*0.8, "• " + t, ha="left", va="center",
                fontsize=8, color="#333")
    ax.text(8.1, 0.95, "Comparable evaluation", ha="center",
            fontsize=8.5, fontweight="bold", color=C_ACC)
    if not own:
        fig.tight_layout(); _save(fig, "figINTRO_A_concept")


# ------------------------------------------------------------------ B: data
def fig_B(ax=None, colors=None, name="figINTRO_B_drift", annotate=False):
    own = ax is not None
    if not own:
        apply_nature_style(); fig, ax = plt.subplots(figsize=(8.4, 4.0))
    import numpy as np
    # the SAME no-scaffold single-LLM baseline, four backbones, four datasets.
    # headline number is set by the dataset, not the model (see caption).
    datasets = ["RareBench", "RareArena", "PP-Store", "PMC-OA"]
    r1 = {
        "Gemini 3 Flash":    [0.023, 0.281, 0.293, 0.616],
        "DeepSeek V4-Pro":   [0.021, 0.193, 0.274, 0.581],
        "DeepSeek V4-Flash": [0.049, 0.207, 0.263, 0.485],
        "GPT-5 minimal":     [0.005, 0.216, 0.254, 0.525],
    }
    cols = colors or [PAL[0], PAL[1], PAL[2], PAL[3]]
    x = np.arange(len(datasets)) * 1.25   # wider group spacing
    w = 0.16                               # thinner bars
    for i, (lab, vals) in enumerate(r1.items()):
        off = (i - 1.5) * (w + 0.05)       # gap between bars
        ax.bar(x + off, vals, w, color=cols[i], edgecolor=BAR_EDGE, lw=0.7,
               label=lab, zorder=3)
    ax.set_xticks(x); ax.set_xticklabels(datasets)
    ax.set_ylabel("Recall@1")
    ax.set_ylim(0, 0.78)
    ax.legend(loc="upper left", frameon=False, ncol=1,
              handlelength=1.1, labelspacing=0.3, handletextpad=0.4,
              bbox_to_anchor=(0.0, 1.0))
    if annotate:
        # span arrow between the lowest (RareBench) and highest (PMC-OA) bars
        # to emphasise the dataset-driven swing, parked clear of the legend.
        x_lo, x_hi = x[0], x[3]
        ax.annotate("", xy=(x_hi, 0.66), xytext=(x_lo, 0.055),
                    arrowprops=dict(arrowstyle="-|>", color="#B0392B",
                                    lw=1.6, connectionstyle="arc3,rad=-0.18"))
        ax.text(x[2]+0.1, 0.71, r"same model, up to $100\times$ across datasets",
                ha="center", va="center", color="#B0392B", fontweight="bold")
    despine(ax); ax.grid(axis="y", alpha=0.4, zorder=0)
    if not own:
        fig.tight_layout(); _save(fig, name)


# ------------------------------------------------------------------ AB combo
def fig_AB():
    apply_nature_style()
    fig, axes = plt.subplots(2, 1, figsize=(7.4, 5.4),
                             gridspec_kw={"height_ratios": [3.0, 2.4]})
    fig_A(axes[0]); fig_B(axes[1])
    fig.tight_layout(h_pad=1.2)
    _save(fig, "figINTRO_AB_combo")


if __name__ == "__main__":
    fig_A(); fig_B(); fig_AB()
    print("intro candidates written to", OUT)


# ============================ alternative forms for the drift story ==========
import numpy as np
_DATASETS = ["RareBench", "RareArena", "PP-Store", "PMC-OA"]
_R1 = {
    "Gemini 3 Flash":    [0.023, 0.281, 0.293, 0.616],
    "DeepSeek V4-Pro":   [0.021, 0.193, 0.274, 0.581],
    "DeepSeek V4-Flash": [0.049, 0.207, 0.263, 0.485],
    "GPT-5 minimal":     [0.005, 0.216, 0.254, 0.525],
}
_COLS = [PAL[0], PAL[1], PAL[2], PAL[3]]
_MK = ["o", "s", "^", "D"]

def form_slope():
    apply_nature_style(); fig, ax = plt.subplots(figsize=(7.8, 4.4))
    x = np.arange(len(_DATASETS))
    for i, (lab, v) in enumerate(_R1.items()):
        ax.plot(x, v, "-", marker=_MK[i], color=_COLS[i], lw=2.2, ms=9,
                label=lab, zorder=3)
    ax.set_xticks(x); ax.set_xticklabels(_DATASETS)
    ax.set_ylabel("Recall@1"); ax.set_ylim(0, 0.70)
    ax.set_xlim(-0.3, 3.5)
    ax.legend(loc="upper left", frameon=False, labelspacing=0.3,
              handlelength=1.6, bbox_to_anchor=(0.0, 1.0))
    despine(ax); ax.grid(axis="y", alpha=0.35, zorder=0)
    fig.tight_layout(); _save(fig, "figINTRO_form1_slope")

def form_dotband():
    apply_nature_style(); fig, ax = plt.subplots(figsize=(7.8, 4.2))
    x = np.arange(len(_DATASETS))
    mat = np.array(list(_R1.values()))          # 4 models x 4 datasets
    lo = mat.min(0); hi = mat.max(0)
    ax.fill_between(x, lo, hi, color=PAL[0], alpha=0.12, zorder=1)
    ax.plot(x, mat.mean(0), color="#888", lw=1.0, ls="--", zorder=2)
    for i, (lab, v) in enumerate(_R1.items()):
        ax.scatter(x, v, s=90, color=_COLS[i], edgecolor=BAR_EDGE, lw=0.7,
                   marker=_MK[i], label=lab, zorder=3)
    ax.set_xticks(x); ax.set_xticklabels(_DATASETS)
    ax.set_ylabel("Recall@1"); ax.set_ylim(0, 0.70); ax.set_xlim(-0.3, 3.4)
    ax.legend(loc="upper left", frameon=False, labelspacing=0.3,
              handlelength=1.1, bbox_to_anchor=(0.0, 1.0))
    despine(ax); ax.grid(axis="y", alpha=0.35, zorder=0)
    fig.tight_layout(); _save(fig, "figINTRO_form2_dotband")

def form_dumbbell():
    apply_nature_style(); fig, ax = plt.subplots(figsize=(7.8, 3.4))
    models = list(_R1.keys())
    y = np.arange(len(models))[::-1]
    for yi, (lab, v) in zip(y, _R1.items()):
        lo, hi = min(v), max(v)
        ax.plot([lo, hi], [yi, yi], color="#BBB", lw=4, solid_capstyle="round", zorder=2)
        ax.scatter(lo, yi, s=110, color=PAL[4], edgecolor=BAR_EDGE, lw=0.7, zorder=3)
        ax.scatter(hi, yi, s=110, color=PAL[1], edgecolor=BAR_EDGE, lw=0.7, zorder=3)
        ax.text(hi+0.01, yi, f"{lo:.2f}\\,$\\rightarrow$\\,{hi:.2f}", va="center", ha="left")
    ax.set_yticks(y); ax.set_yticklabels(models)
    ax.set_xlabel("Recall@1 range across the four datasets")
    ax.set_xlim(0, 0.78); ax.set_ylim(-0.6, len(models)-0.4)
    despine(ax); ax.grid(axis="x", alpha=0.35, zorder=0)
    fig.tight_layout(); _save(fig, "figINTRO_form3_dumbbell")

def form_heatmap():
    apply_nature_style(); fig, ax = plt.subplots(figsize=(6.8, 4.2))
    models = list(_R1.keys())
    mat = np.array([_R1[m] for m in models])    # rows models, cols datasets
    im = ax.imshow(mat, cmap="Blues", vmin=0, vmax=0.65, aspect="auto")
    ax.set_xticks(range(len(_DATASETS))); ax.set_xticklabels(_DATASETS)
    ax.set_yticks(range(len(models))); ax.set_yticklabels(models)
    for r in range(mat.shape[0]):
        for c in range(mat.shape[1]):
            v = mat[r, c]
            ax.text(c, r, f"{v:.2f}", ha="center", va="center",
                    color="white" if v > 0.33 else "#222")
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
    cb.set_label("Recall@1")
    fig.tight_layout(); _save(fig, "figINTRO_form4_heatmap")

if __name__ == "__main__" and "forms" in sys.argv:
    form_slope(); form_dotband(); form_dumbbell(); form_heatmap()
    print("forms written")
