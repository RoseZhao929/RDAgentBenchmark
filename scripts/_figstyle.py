"""Shared Nature-grade matplotlib style for all paper figures.

Call apply_nature_style() once before plotting. Provides a colorblind-safe
categorical palette (Okabe-Ito), a perceptually-uniform sequential colormap
for heatmaps, and helpers for despining and luminance-aware text color.
"""
from __future__ import annotations

# Okabe-Ito colorblind-safe categorical palette (Nature-recommended)
PALETTE = ['#0072B2', '#E69F00', '#009E73', '#D55E00', '#CC79A7',
           '#56B4E9', '#F0E442', '#000000', '#999999']

AGENT_ORDER = ['llm_control', 'mdagents', 'medagents', 'agentclinic',
               'maidxo', 'deeprare', 'vc_rdagent', 'lirical']
AGENT_COLOR = {a: PALETTE[i % len(PALETTE)] for i, a in enumerate(AGENT_ORDER)}


def heatmap_cmap():
    """Perceptually-uniform sequential colormap (seaborn 'rocket', mpl fallback)."""
    try:
        import seaborn as sns
        return sns.color_palette("rocket_r", as_cmap=True)
    except Exception:
        import matplotlib.pyplot as plt
        return plt.get_cmap("magma_r")


def apply_nature_style():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "Helvetica Neue", "DejaVu Sans"],
        "font.size": 8,
        "axes.titlesize": 9,
        "axes.titleweight": "bold",
        "axes.labelsize": 8,
        "axes.labelweight": "regular",
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "legend.fontsize": 7,
        "legend.frameon": False,
        "axes.linewidth": 0.6,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.titlepad": 6,
        "axes.axisbelow": True,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "xtick.major.size": 3,
        "ytick.major.size": 3,
        "xtick.direction": "out",
        "ytick.direction": "out",
        "lines.linewidth": 1.4,
        "lines.markersize": 6,
        "grid.linewidth": 0.4,
        "grid.color": "#cccccc",
        "figure.dpi": 300,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.03,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })


def despine(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def text_color_for(cmap, norm, value):
    """Black or white label depending on cell luminance — readable on any cmap."""
    r, g, b, _ = cmap(norm(value))
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "white" if lum < 0.5 else "black"
