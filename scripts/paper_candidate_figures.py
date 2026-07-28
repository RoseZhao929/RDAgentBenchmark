"""Candidate new figures (A-D) for the RareAgentBench paper.

Reuses the shared nature-style canvas and palette from _figstyle so the
candidates render consistently with the six main-body panels. Each candidate is
written to data/round2/figures/cand_{A,B,C,D}_*.png for review.

Data sources (frozen):
  audit_frozen/_manifest_rows.json                     -- per-cell recompute
  audit_frozen/mimic_note_experiment/agent_matrix_scores.json (not needed here)
"""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from _figstyle import (apply_nature_style, EMNLP_PALETTE as PALETTE, BAR_EDGE,
                       PANEL_FIGSIZE, despine)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

FIG = ROOT / "data/round2/figures"
FIG.mkdir(parents=True, exist_ok=True)
MAN = json.loads((ROOT / "audit_frozen/_manifest_rows.json").read_text())
idx = {(m["dataset"], m["system"], m["backbone"]): m for m in MAN}

C_LLM = PALETTE[0]
C_ACCENT = PALETTE[1]
GEM = "google_gemini-3-flash-preview-"
AGENTS = ["llm_control", "mdagents", "medagents", "agentclinic", "deeprare", "maidxo"]
AG_LABEL = {"llm_control": "LLM control", "mdagents": "MDAgents",
            "medagents": "MedAgents", "agentclinic": "AgentClinic",
            "deeprare": "DeepRare", "maidxo": "MAI-DxO"}
DEV = ["phenopacket_store", "rarearena_rds", "rarebench"]


def agg_over_dev(system, field_list):
    """Sum given integer fields over the three dev layers, all backbones."""
    out = {f: 0 for f in field_list}
    n = 0
    for m in MAN:
        if m["system"] == system and m["dataset"] in DEV:
            for f in field_list:
                out[f] += m.get(f, 0) or 0
            n += m["n_attempted"]
    return out, n


# ---------------------------------------------------------------- Candidate A
def cand_A_failure_modes():
    """Stacked horizontal bar: outcome composition per agent (ok / empty /
    parser / timeout / agent_error), aggregated over the 3 dev layers."""
    apply_nature_style()
    fields = ["n_successful", "fail_empty_ok", "fail_parser", "fail_timeout", "fail_agent"]
    seg_labels = ["Success", "Empty / abstained", "Parser error", "Timeout", "Agent error"]
    seg_colors = [C_ACCENT, "#C05A4D", "#D6A02E", "#8E6BAF", "#7F7F7F"]
    rows = []
    for ag in AGENTS:
        agg, n = agg_over_dev(ag, fields)
        rows.append((ag, [agg[f] / n * 100 for f in fields], n))
    fig, ax = plt.subplots(figsize=PANEL_FIGSIZE)
    y = np.arange(len(rows))[::-1]
    left = np.zeros(len(rows))
    for si, (lab, col) in enumerate(zip(seg_labels, seg_colors)):
        vals = np.array([r[1][si] for r in rows])
        ax.barh(y, vals, left=left, color=col, edgecolor=BAR_EDGE,
                linewidth=0.6, label=lab, zorder=3)
        left += vals
    ax.set_yticks(y)
    ax.set_yticklabels([AG_LABEL[r[0]] for r in rows])
    ax.set_xlabel("Outcome share (%)")
    ax.set_xlim(0, 100)
    # annotate non-success total on the right
    for yi, r in zip(y, rows):
        fail = 100 - r[1][0]
        if fail > 0.5:
            ax.text(101, yi, f"{fail:.0f}% fail", va="center", ha="left",
                    fontsize=12, color="#444")
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.01), ncol=3,
              fontsize=11, frameon=False)
    ax.set_xlim(0, 108)
    despine(ax)
    fig.tight_layout()
    fig.savefig(FIG / "cand_A_failure_modes.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("wrote cand_A_failure_modes.png")


# ---------------------------------------------------------------- Candidate B
def _median_latency_ok(ag, ds="phenopacket_store", bb_id="google_gemini-3-flash-preview-20251217"):
    """Median end-to-end latency (s) over SUCCESSFUL cases only, read from
    receipts. Successful-only + median so the number reflects the agent's
    intrinsic speed and is not distorted by the harness timeout wall."""
    import statistics
    f = ROOT / f"data/round2/phase4a/predictions_{ds}_{ag}_{bb_id}.jsonl"
    lats = []
    try:
        fh = open(f)
    except OSError:
        return None
    for l in fh:
        if not l.strip():
            continue
        r = json.loads(l)
        if r.get("status") == "ok" and r.get("ranked_predictions"):
            lat = r.get("total_latency_ms")
            if lat:
                lats.append(lat / 1000)
    return statistics.median(lats) if lats else None


def cand_B_latency_accuracy():
    """Scatter: orchestration latency (log x, median over successful cases) vs
    R@1 (y), PP-Store, Gemini. Heavy scaffolds pay 5-80x latency for equal-or-
    worse accuracy. Latency is median-of-successful so the harness timeout wall
    does not enter the number."""
    apply_nature_style()
    ag_color = {a: PALETTE[i % len(PALETTE)] for i, a in enumerate(AGENTS)}
    # explicit label placement (data coords for x via log; y absolute) with a
    # thin leader line, so the three fast agents in the top-left do not collide.
    lab_pos = {
        "llm_control": (2.6, 0.335, "left"),
        "mdagents":    (5.4, 0.238, "center"),
        "medagents":   (17.0, 0.335, "left"),
        "agentclinic": (40, 0.158, "center"),
        "deeprare":    (122, 0.315, "center"),
        "maidxo":      (150, 0.055, "right"),
    }
    fig, ax = plt.subplots(figsize=PANEL_FIGSIZE)
    for ag in AGENTS:
        m = idx.get(("phenopacket_store", ag, GEM))
        lat = _median_latency_ok(ag)
        if not m or lat is None:
            continue
        acc = m["R@1_variant_aware"]
        ax.scatter(lat, acc, c=ag_color[ag], s=210, edgecolors=BAR_EDGE,
                   linewidths=0.9, zorder=4)
        lx, ly, lha = lab_pos[ag]
        # leader line from marker to label
        ax.annotate("", xy=(lat, acc), xytext=(lx, ly),
                    arrowprops=dict(arrowstyle="-", color="#BBBBBB", lw=0.8),
                    zorder=2)
        ax.text(lx, ly, AG_LABEL[ag], fontsize=17, ha=lha, va="center",
                zorder=5)
    ax.set_xscale("log")
    ax.set_xlabel("Median latency per case (s, log scale)")
    ax.set_ylabel("R@1 (variant-aware)")
    ax.set_ylim(-0.03, 0.37)
    ax.set_xlim(2, 600)
    # control-accuracy reference line (unlabeled; described in caption)
    ctrl = idx[("phenopacket_store", "llm_control", GEM)]
    ax.axhline(ctrl["R@1_variant_aware"], ls=":", color="#999", lw=1.2, zorder=1)
    despine(ax)
    fig.tight_layout()
    fig.savefig(FIG / "cand_B_latency_accuracy.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("wrote cand_B_latency_accuracy.png")


# ---------------------------------------------------------------- Candidate C
def cand_C_r1_r5_dumbbell():
    """Dumbbell: R@1 -> R@5 (variant-aware) per agent, PP-Store & RareBench,
    Gemini. Reveals 'answer in top-5 but mis-ranked' (DeepRare) vs
    'fundamentally absent' (MAI-DxO, gap 0)."""
    apply_nature_style()
    datasets = [("phenopacket_store", "Phenopacket-Store"), ("rarebench", "RareBench")]
    fig, axes = plt.subplots(1, 2, figsize=(PANEL_FIGSIZE[0] * 1.7, PANEL_FIGSIZE[1]),
                             sharey=True)
    for ax, (ds, title) in zip(axes, datasets):
        y = np.arange(len(AGENTS))[::-1]
        for yi, ag in zip(y, AGENTS):
            m = idx.get((ds, ag, GEM))
            if not m or m["R@1_variant_aware"] is None:
                continue
            r1, r5 = m["R@1_variant_aware"], m["R@5_variant_aware"]
            ax.plot([r1, r5], [yi, yi], color="#BBBBBB", lw=3, zorder=2,
                    solid_capstyle="round")
            ax.scatter(r1, yi, c=C_LLM, s=130, edgecolors=BAR_EDGE,
                       linewidths=0.8, zorder=3)
            ax.scatter(r5, yi, c=C_ACCENT, s=130, edgecolors=BAR_EDGE,
                       linewidths=0.8, zorder=3)
        ax.set_yticks(y)
        ax.set_yticklabels([AG_LABEL[a] for a in AGENTS])
        ax.set_xlabel("R@k (variant-aware)")
        ax.set_title(title, fontsize=14)
        ax.set_xlim(-0.02, 0.55)
        despine(ax)
    handles = [Line2D([0], [0], marker="o", color="w", markerfacecolor=C_LLM,
                      markeredgecolor=BAR_EDGE, markersize=12, label="R@1"),
               Line2D([0], [0], marker="o", color="w", markerfacecolor=C_ACCENT,
                      markeredgecolor=BAR_EDGE, markersize=12, label="R@5")]
    axes[0].legend(handles=handles, loc="lower right", fontsize=12, frameon=False)
    fig.tight_layout()
    fig.savefig(FIG / "cand_C_r1_r5_dumbbell.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("wrote cand_C_r1_r5_dumbbell.png")


# ---------------------------------------------------------------- Candidate D
def cand_D_layer_profile():
    """Line profile across the 4 evaluation layers, per agent, Gemini.
    Shows every scaffold collapses on RareBench and peaks on PMC."""
    apply_nature_style()
    layers = [("phenopacket_store", "PP-Store"), ("rarearena_rds", "RareArena"),
              ("rarebench", "RareBench"), ("pmc_oa_holdout", "PMC-OA")]
    fig, ax = plt.subplots(figsize=PANEL_FIGSIZE)
    x = np.arange(len(layers))
    for i, ag in enumerate(AGENTS):
        ys = []
        for ds, _ in layers:
            m = idx.get((ds, ag, GEM))
            ys.append(m["R@1_variant_aware"] if m else np.nan)
        ax.plot(x, ys, "o-", color=PALETTE[i % len(PALETTE)], lw=2.0, ms=8,
                label=AG_LABEL[ag], zorder=3)
    ax.set_xticks(x)
    ax.set_xticklabels([l[1] for l in layers])
    ax.set_ylabel("R@1 (variant-aware)")
    ax.set_xlabel("Evaluation layer")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.14), ncol=3,
              fontsize=10, frameon=False)
    despine(ax)
    fig.tight_layout()
    fig.savefig(FIG / "cand_D_layer_profile.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("wrote cand_D_layer_profile.png")


if __name__ == "__main__":
    # cand_A_failure_modes()  # deprecated: failure breakdown risks exposing infra errors
    cand_B_latency_accuracy()
    print("candidates A,B written to", FIG)
