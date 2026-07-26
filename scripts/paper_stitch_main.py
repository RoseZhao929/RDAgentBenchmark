"""Stitch the six main-body figures into one 2x3 composite, in the order they
are referenced in the paper:

  row 1:  (a) figM1  F1 classical vs LLM     (b) figM2  cost-vs-accuracy
          (c) figM3  prevalence crossover
  row 2:  (d) figF2  scaffolding ladder      (e) figM5  self-preference
          (f) figM6  hypothesis tests

The six individual figure scripts (paper_main_figures.py) are UNCHANGED and
remain the source of truth — this script only reads their rendered PNGs and
lays them out on a grid, so individual panels can still be re-tuned and this
re-run. Panel letters (a)-(f) are drawn on each cell.

Output: data/round2/figures/figMAIN_2x3.png
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from _figstyle import apply_nature_style  # noqa: E402

FIG = ROOT / "data/round2/figures"

# (filename, panel letter) in paper reference order, row-major over a 2x3 grid.
PANELS = [
    ("figM1_v2a_layered.png", "a"),
    ("figM2_cost_accuracy.png", "b"),
    ("figM3_prevalence.png", "c"),
    ("figF2_scaffolding.png", "d"),
    ("figM5_selfpref.png", "e"),
    ("figM6_hypotheses.png", "f"),
]


def main():
    apply_nature_style()
    import matplotlib.pyplot as plt
    import matplotlib.image as mpimg

    ncols, nrows = 3, 2
    # each source PNG has its own aspect; give every cell the same box and let
    # imshow letterbox within it so nothing is distorted.
    fig, axes = plt.subplots(nrows, ncols, figsize=(18, 9.5))
    for ax, (fn, letter) in zip(axes.flat, PANELS):
        src = FIG / fn
        if not src.exists():
            ax.axis("off")
            ax.text(0.5, 0.5, f"missing\n{fn}", ha="center", va="center")
            continue
        img = mpimg.imread(src)
        ax.imshow(img)
        ax.axis("off")
        # panel letter, top-left, bold
        ax.text(-0.02, 1.02, f"({letter})", transform=ax.transAxes,
                fontsize=20, fontweight="bold", va="top", ha="left")
    fig.subplots_adjust(left=0.01, right=0.99, top=0.97, bottom=0.01,
                        wspace=0.04, hspace=0.06)
    out = FIG / "figMAIN_2x3.png"
    fig.savefig(out, dpi=200)
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
