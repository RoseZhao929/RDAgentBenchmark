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


# EMNLP reference palette (from EMNLP_2026_healthBench figures): muted-but-
# saturated blue / green / gold / purple, dark thin bar edges, dotted grid.
EMNLP_PALETTE = ["#3B6FB0", "#5B9C64", "#D6A02E", "#8E6BAF", "#C05A4D",
                 "#4FA0A6", "#B07AA1", "#7F7F7F"]
BAR_EDGE = "#222222"

# Shared canvas for every main-body panel. Identical width/height means every
# panel is scaled by the same factor in the 2x3 composite, so the (uniform)
# font renders at the same apparent size across all panels. Wide-content panels
# (M2 legend, M5 four sub-axes) still use this box; their content is arranged to
# fit rather than widening the canvas.
PANEL_FIGSIZE = (5.8, 5.0)


def apply_nature_style():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    # Font sizing follows the EMNLP_2026_healthBench reference figures (large,
    # print-legible: title ~15, panel title ~13, axis ~11, ticks ~10, legend ~10,
    # value labels ~9). Face is Times New Roman per author preference — named
    # first for portability (macOS/Overleaf); on the Linux TeX stack the URW
    # clone "Nimbus Roman" is metric-identical to Times and renders in the same
    # face as the typeset body text.
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Nimbus Roman", "Liberation Serif",
                       "Tinos", "DejaVu Serif"],
        "mathtext.fontset": "stix",
        # every text element the same size (user requirement: uniform fonts).
        # All main-body figures share a common canvas size (see PANEL_FIGSIZE)
        # so that at equal cell scale in the 2x3 composite the apparent font is
        # identical across panels.
        "font.size": 17,
        "axes.titlesize": 17,
        "axes.titleweight": "bold",
        "axes.labelsize": 17,
        "axes.labelweight": "regular",
        "xtick.labelsize": 17,
        "ytick.labelsize": 17,
        "legend.fontsize": 17,
        "legend.title_fontsize": 17,
        "legend.frameon": True,
        "legend.framealpha": 0.95,
        "legend.edgecolor": "#888888",
        "legend.borderpad": 0.5,
        "axes.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.titlepad": 8,
        "axes.axisbelow": True,
        "xtick.major.width": 0.8,
        "ytick.major.width": 0.8,
        "xtick.major.size": 3.5,
        "ytick.major.size": 3.5,
        "xtick.direction": "out",
        "ytick.direction": "out",
        "lines.linewidth": 1.8,
        "lines.markersize": 7,
        "grid.linewidth": 0.6,
        "grid.linestyle": ":",
        "grid.color": "#bbbbbb",
        "figure.dpi": 300,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.04,
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
