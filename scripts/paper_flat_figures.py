"""Regenerate the six main-body panels with a uniform FLAT aspect ratio for a
2x3 composite. Originals under data/round2/figures are left untouched; flat
versions go to paper_aaai27_collab/Figures_flat/.

Approach: import paper_main_figures, monkey-patch plt.subplots so every panel
is drawn at the same wide figsize (ratio ~1.6), and redirect the module's FIG
output dir. Single-axes panels get FLAT; the 2x2 self-pref panel gets FLAT too
so all six share the same outer box for stitching.
"""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import paper_main_figures as P

# uniform flat canvas (w, h) -> ratio 1.6
FLAT = (6.4, 4.0)

OUT = ROOT / "paper_aaai27_collab" / "Figures_flat"
OUT.mkdir(parents=True, exist_ok=True)
P.FIG = OUT  # redirect all savefig(FIG / ...) into the flat folder

# force every plt.subplots(...) in the panel functions to the flat size,
# preserving nrows/ncols (needed for the 2x2 self-pref panel).
_orig_subplots = plt.subplots
def _flat_subplots(*args, **kwargs):
    kwargs["figsize"] = FLAT
    return _orig_subplots(*args, **kwargs)
plt.subplots = _flat_subplots

# the panel functions call fig.savefig(FIG / "xxx.png"); emit a vector PDF
# alongside the PNG so Overleaf renders crisp at any panel size.
from matplotlib.figure import Figure
_orig_savefig = Figure.savefig
def _dual_savefig(self, fname, *args, **kwargs):
    _orig_savefig(self, fname, *args, **kwargs)          # keep the PNG (for stitch check)
    p = Path(fname)
    if p.suffix.lower() == ".png":
        kwargs.pop("dpi", None)
        _orig_savefig(self, str(p.with_suffix(".pdf")), *args, **kwargs)
Figure.savefig = _dual_savefig

def main():
    rows = P.load_manifest()
    P.figM1_v2a_layered(rows)     # (a)
    P.figM2_cost_accuracy(rows)   # (b)
    P.figM6_hypotheses()          # (c)
    P.figF2_scaffolding(rows)     # (d)
    P.figM3_prevalence()          # (e)
    P.figM5_selfpref()            # (f)
    print("flat panels written to", OUT)

if __name__ == "__main__":
    main()
