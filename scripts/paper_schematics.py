"""Schematic (non-data) paper figures, Nature-grade style:

  fig_design_matrix : capability pillars x diagnostic/probe coverage grid
                      (replaces the pillar table + layer table)
  fig_schema        : the CanonicalCase record diagram (replaces the code block)

Writes 300-dpi PNGs to data/round2/figures/.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _figstyle import apply_nature_style

FIG = Path("data/round2/figures")

PILLARS = [
    ("P1", "Phenotype Extraction", "free-text → HPO list"),
    ("P2", "Phenotype-only DDx", "HPO → ranked diseases"),
    ("P3", "Genotype-aware DDx", "HPO + variants → gene"),
    ("P4", "Family-aware DDx", "HPO + pedigree → MOI"),
    ("P5", "Reasoning Faithfulness", "trace → 4-axis score"),
]
LAYERS = [
    ("L1", "Phenotype\nBackbone", "PP-Store + RareBench", "11,173"),
    ("S-EHR", "Structured EHR\nProbe", "MIMIC-IV admissions", "956"),
    ("L3", "Scale +\nFree text", "RareArena RDS", "72,661"),
    ("L4", "Post-cutoff\nHoldout", "PMC-OA ≥2024", "200"),
]
# coverage[pillar_idx] = set of covered layer indices in v1 ; None-ish = v2
COVER = {
    0: {0, 2, 3},        # P1 on L1(synthetic), L3, L4
    1: {0, 1, 2, 3},     # P2 all four
    2: {0},              # P3 PP-Store (structured variants) only
    3: set(),            # P4 deferred to v2
    4: {0, 1, 2, 3},     # P5 all layers (pilot)
}


def design_matrix():
    apply_nature_style()
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch
    nP, nL = len(PILLARS), len(LAYERS)
    fig, ax = plt.subplots(figsize=(9.0, 5.6))
    ax.set_xlim(-0.2, nL + 0.05)
    ax.set_ylim(-0.15, nP + 1.15)
    ax.invert_yaxis()
    ax.axis("off")

    covc, v2c, emptyc = "#0072B2", "#cfcfcf", "#f3f4f6"
    # column headers (layers)
    for j, (lid, name, src, n) in enumerate(LAYERS):
        ax.text(j + 0.5, -0.02, lid, ha="center", va="bottom",
                fontsize=10, fontweight="bold", color="#111")
        ax.text(j + 0.5, 0.30, name, ha="center", va="top", fontsize=7.2, color="#111")
        ax.text(j + 0.5, 0.72, src, ha="center", va="top", fontsize=6.0, color="#555")
        ax.text(j + 0.5, 0.93, f"n={n}", ha="center", va="top", fontsize=6.0,
                style="italic", color="#555")
    # cells
    for i, (pid, pname, io) in enumerate(PILLARS):
        y = i + 1
        ax.text(-0.15, y + 0.42, pid, ha="left", va="center",
                fontsize=9.5, fontweight="bold", color="#111")
        ax.text(-0.15, y + 0.72, pname, ha="left", va="center", fontsize=6.6, color="#111")
        deferred = (len(COVER[i]) == 0)
        for j in range(nL):
            covered = j in COVER[i]
            fc = covc if covered else (v2c if deferred else emptyc)
            box = FancyBboxPatch((j + 0.08, y + 0.12), 0.84, 0.76,
                                 boxstyle="round,pad=0.0,rounding_size=0.06",
                                 linewidth=0.6, edgecolor="white", facecolor=fc)
            ax.add_patch(box)
            if covered:
                cx, cy = j + 0.5, y + 0.5   # draw a check (font-independent; y-axis inverted)
                ax.plot([cx - 0.16, cx - 0.03, cx + 0.18],
                        [cy, cy + 0.14, cy - 0.15],
                        color="white", lw=2.4, solid_capstyle="round",
                        solid_joinstyle="round", zorder=5)
            elif deferred:
                ax.text(j + 0.5, y + 0.5, "v2", ha="center", va="center",
                        fontsize=8, color="#888", style="italic")
    # left header
    ax.text(-0.15, 0.5, "Capability pillar", ha="left", va="center",
            fontsize=8, fontweight="bold", color="#333")
    # legend
    import matplotlib.patches as mp
    handles = [mp.Patch(facecolor=covc, edgecolor="white", label="evaluated in v1"),
               mp.Patch(facecolor=v2c, edgecolor="white", label="deferred to v2"),
               mp.Patch(facecolor=emptyc, edgecolor="white", label="not applicable")]
    ax.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, -0.06),
              ncol=3, fontsize=7, frameon=False)
    fig.suptitle("Benchmark surface: three diagnostic layers + one structured-EHR probe",
                 fontsize=10, fontweight="bold", y=0.98)
    fig.savefig(FIG / "fig_design_matrix.png")
    plt.close(fig)
    print("Wrote fig_design_matrix.png")


SCHEMA_GROUPS = [
    ("Identity", "#0072B2", [
        "case_id : str", "source_dataset : Literal[...]",
        "source_split : Optional[str]", "language : en | zh | other"]),
    ("Inputs", "#009E73", [
        "demographics : age, sex, ancestry", "free_text_vignette : Optional[str]",
        "synthetic_vignette : Optional[str]", "gold_hpo_terms : List[HpoTerm]",
        "variants : List[Variant]", "vcf_path : Optional[str]  (local, DUA)",
        "family : Optional[FamilyHistory]"]),
    ("Gold label", "#D55E00", [
        "gold_label : OMIM | ORPHA | CCRD | name"]),
    ("Meta", "#666666", ["metadata : publication_date, dept, ..."]),
]


def schema_card():
    apply_nature_style()
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch
    fig, ax = plt.subplots(figsize=(7.2, 6.2))
    ax.set_xlim(0, 10); ax.set_ylim(0, 12.6); ax.axis("off")

    ax.add_patch(FancyBboxPatch((0.2, 0.2), 9.6, 12.0,
                 boxstyle="round,pad=0.02,rounding_size=0.18",
                 linewidth=1.2, edgecolor="#333", facecolor="#fbfbfb"))
    ax.text(5.0, 12.0, "CanonicalCase", ha="center", va="top",
            fontsize=12, fontweight="bold", color="#111")
    ax.text(5.0, 11.5, "single Pydantic-v2 schema; every dataset ingests into it,"
            " every agent adapter projects out of it",
            ha="center", va="top", fontsize=6.6, style="italic", color="#666")

    y = 11.0
    for gname, color, fields in SCHEMA_GROUPS:
        gh = 0.42 + 0.46 * len(fields)
        ax.add_patch(FancyBboxPatch((0.55, y - gh), 8.9, gh,
                     boxstyle="round,pad=0.02,rounding_size=0.08",
                     linewidth=0, facecolor=color + "18"))
        ax.add_patch(plt.Rectangle((0.55, y - gh), 0.10, gh, color=color))
        ax.text(0.85, y - 0.12, gname, ha="left", va="top",
                fontsize=8.5, fontweight="bold", color=color)
        for k, fld in enumerate(fields):
            ax.text(2.7, y - 0.14 - 0.46 * k, fld, ha="left", va="top",
                    fontsize=7.4, family="monospace", color="#222")
        y -= gh + 0.18

    fig.suptitle("Canonical case representation", fontsize=10,
                 fontweight="bold", y=0.99)
    fig.savefig(FIG / "fig_schema.png")
    plt.close(fig)
    print("Wrote fig_schema.png")


if __name__ == "__main__":
    FIG.mkdir(parents=True, exist_ok=True)
    design_matrix()
    schema_card()
