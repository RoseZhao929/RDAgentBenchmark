"""Generate the main-body paper figures from Phase 4a+4c data, in a
Nature-grade style (shared _figstyle). Figure types are deliberately varied:

  fig1  multi-panel heatmap  (agent x backbone R@1, one panel per dataset)
  fig2  cost-vs-accuracy scatter with a Pareto frontier
  fig3  lollipop / dot-plot ranking (best-backbone R@1 per agent per dataset)

Writes 300-dpi PNGs to data/round2/figures/.
"""
from __future__ import annotations
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _figstyle import (apply_nature_style, AGENT_COLOR, heatmap_cmap,
                       despine, text_color_for)

FIG = Path("data/round2/figures")
DS_TITLE = {'phenopacket_store': 'Phenopacket-Store', 'rarearena_rds': 'RareArena RDS',
            'rarebench': 'RareBench HF', 'mimic_diverse': 'MIMIC-N (de-leaked)'}

# The EHR layer is reported from the de-leaked discharge-summary probe (416
# frozen cases, fixed denominator) rather than the leaked ICD-title slice.
# Keyed (agent, backbone-suffix) -> micro R@1, loaded from the score manifest.
MIMIC_MANIFEST = Path(
    "audit_frozen/mimic_note_experiment/agent_matrix_scores.json")
_MIMIC_BB = {'deepseek-v4-pro': 'deepseek_deepseek-v4-pro',
             'deepseek-v4-flash': 'deepseek_deepseek-v4-flash',
             'gpt-5': 'openai_gpt-5',
             'gemini-3-flash': 'google_gemini-3-flash-preview-20251217'}


def _full_bb(bb: str) -> str:
    """phase4a_summary keys truncate the backbone to 30 chars; undo that so the
    de-leaked manifest (which uses full names) can be looked up."""
    for full in _MIMIC_BB.values():
        if full.startswith(bb):
            return full
    return bb


def load_deleaked_mimic() -> dict:
    """(agent, backbone) -> micro R@1 on the de-leaked 416-case probe."""
    if not MIMIC_MANIFEST.exists():
        print(f"WARNING: {MIMIC_MANIFEST} missing; MIMIC panel will be empty",
              file=sys.stderr)
        return {}
    with open(MIMIC_MANIFEST) as f:
        cells = json.load(f)['cells']
    out = {}
    for key, cell in cells.items():
        agent, bb = key.split('|')
        out[(agent, _MIMIC_BB[bb])] = cell['micro_R1']
    return out


def main():
    try:
        apply_nature_style()
        import matplotlib.pyplot as plt
        import matplotlib.colors as mcolors
        import numpy as np
    except ImportError:
        print("matplotlib not installed, skipping.", file=sys.stderr)
        return

    with open('data/round2/phase4a_summary.json') as f:
        stats = json.load(f)
    FIG.mkdir(parents=True, exist_ok=True)

    agents = ['llm_control', 'mdagents', 'medagents', 'agentclinic',
              'maidxo', 'deeprare', 'vc_rdagent', 'lirical']
    backbones = ['google_gemini-3-flash-preview-20251217', 'deepseek_deepseek-v4-pro',
                 'deepseek_deepseek-v4-flash', 'openai_gpt-5',
                 'vc_rdagent-offline-v1', 'lirical-2.4.0']
    bb_label = {'google_gemini-3-flash-preview-20251217': 'Gemini\nFlash',
                'deepseek_deepseek-v4-pro': 'DS\nV4-Pro',
                'deepseek_deepseek-v4-flash': 'DS\nV4-Flash',
                'openai_gpt-5': 'GPT-5\nmin', 'vc_rdagent-offline-v1': 'offline',
                'lirical-2.4.0': 'classical'}
    datasets = ['phenopacket_store', 'rarearena_rds', 'rarebench', 'mimic_diverse']

    deleaked = load_deleaked_mimic()

    def r1(ds, ag, bb):
        if ds == 'mimic_diverse':
            # de-leaked probe: fixed 416 denominator, failures count as misses
            return deleaked.get((ag, bb))
        s = stats.get(f"{ds}|{ag}|{bb[:30]}")
        return s['h1v'] / s['ok'] if s and s['ok'] > 0 else None

    # ============ Figure 1: multi-panel heatmap (a-d) ============
    cmap = heatmap_cmap()
    norm = mcolors.Normalize(vmin=0, vmax=0.5)
    fig, axes = plt.subplots(2, 2, figsize=(9.2, 8.2))
    for k, (ax, ds) in enumerate(zip(axes.flat, datasets)):
        M = np.full((len(agents), len(backbones)), np.nan)
        for i, ag in enumerate(agents):
            for j, bb in enumerate(backbones):
                v = r1(ds, ag, bb)
                if v is not None:
                    M[i, j] = v
        ax.imshow(M, cmap=cmap, norm=norm, aspect='auto')
        ax.set_xticks(range(len(backbones)))
        ax.set_xticklabels([bb_label[b] for b in backbones], fontsize=6)
        ax.set_yticks(range(len(agents)))
        ax.set_yticklabels(agents, fontsize=6.5)
        ax.set_title(DS_TITLE[ds], fontsize=9)
        ax.tick_params(length=0)
        for sp in ax.spines.values():
            sp.set_visible(False)
        for i in range(len(agents)):
            for j in range(len(backbones)):
                if not np.isnan(M[i, j]):
                    ax.text(j, i, f'{M[i, j]:.2f}', ha='center', va='center',
                            color=text_color_for(cmap, norm, M[i, j]), fontsize=6)
        ax.text(-0.14, 1.06, chr(97 + k), transform=ax.transAxes,
                fontsize=12, fontweight='bold', va='top')
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    cbar = fig.colorbar(sm, ax=axes, shrink=0.6, pad=0.02, aspect=30)
    cbar.set_label('R@1 (variants)', fontsize=8)
    cbar.outline.set_visible(False)
    fig.suptitle('Diagnostic accuracy across agents, backbones and datasets',
                 fontsize=10, fontweight='bold', y=0.98)
    fig.savefig(FIG / 'fig1_heatmaps.png')
    plt.close(fig)
    print("Wrote fig1_heatmaps.png")

    # ============ Figure 2: cost vs accuracy + Pareto frontier ============
    bb_marker = {'google_gemini-3-flash-preview-20251217': 'o',
                 'deepseek_deepseek-v4-pro': 's', 'deepseek_deepseek-v4-flash': '^',
                 'openai_gpt-5': 'D'}
    fig, ax = plt.subplots(figsize=(7.2, 5.2))
    pts = []
    for key, s in stats.items():
        if s['ok'] == 0 or s['sum_usd'] == 0:
            continue
        ds, ag, bb = key.split('|')
        cost = s['sum_usd'] / s['ok']
        if ds == 'mimic_diverse':
            # accuracy must come from the de-leaked probe; the leaked cells are
            # not reported anywhere in the paper. Cost per prediction is
            # unchanged (same model, same prompt scale).
            acc = deleaked.get((ag, _full_bb(bb)))
            if acc is None:
                continue
        else:
            acc = s['h1v'] / s['ok']
        pts.append((cost, acc, ag, bb))
        ax.scatter(cost, acc, c=AGENT_COLOR.get(ag, '#999999'),
                   marker=bb_marker.get(bb, 'x'), s=42, alpha=0.85,
                   edgecolors='white', linewidths=0.5, zorder=3)
    # Pareto frontier: max accuracy achievable at or below each cost
    front = []
    best = -1
    for cost, acc, ag, bb in sorted(pts, key=lambda x: x[0]):
        if acc > best:
            best = acc
            front.append((cost, acc))
    if front:
        fx = [p[0] for p in front]
        fy = [p[1] for p in front]
        ax.step(fx, fy, where='post', color='#333333', lw=1.2, ls='--',
                zorder=2, label='Pareto frontier')
    ax.set_xscale('log')
    ax.set_xlabel('Cost per prediction (USD, log scale)')
    ax.set_ylabel('R@1 (variants)')
    ax.set_title('Cost-efficiency of agent x backbone cells', fontsize=9)
    ax.grid(True, which='major', axis='both', alpha=0.5)
    # two legends: agent colour, backbone shape
    from matplotlib.lines import Line2D
    ag_h = [Line2D([0], [0], marker='o', color='w', markerfacecolor=AGENT_COLOR[a],
                   markersize=7, label=a) for a in agents if a in AGENT_COLOR
            and any(p[2] == a for p in pts)]
    bb_h = [Line2D([0], [0], marker=m, color='#555555', linestyle='',
                   markersize=7, label=bb_label.get(b, b).replace('\n', ' '))
            for b, m in bb_marker.items()]
    leg1 = ax.legend(handles=ag_h, title='agent', loc='lower right', fontsize=6.5,
                     title_fontsize=7, ncol=2)
    ax.add_artist(leg1)
    ax.legend(handles=bb_h + [Line2D([0], [0], color='#333333', ls='--', label='Pareto frontier')],
              title='backbone', loc='upper left', fontsize=6.5, title_fontsize=7)
    despine(ax)
    fig.savefig(FIG / 'fig2_cost_accuracy.png')
    plt.close(fig)
    print("Wrote fig2_cost_accuracy.png")

    # ============ Figure 3: lollipop ranking (not bars) ============
    fig, axes = plt.subplots(2, 2, figsize=(9.2, 7.4))
    for k, (ax, ds) in enumerate(zip(axes.flat, datasets)):
        best = {}
        for ag in agents:
            for bb in backbones:
                v = r1(ds, ag, bb)
                if v is not None and (ag not in best or v > best[ag][0]):
                    best[ag] = (v, bb_label.get(bb, bb).replace('\n', ' '))
        items = sorted(best.items(), key=lambda x: x[1][0])   # ascending -> top at end
        names = [k2 for k2, _ in items]
        vals = [v[0] for _, v in items]
        bbl = [v[1] for _, v in items]
        y = range(len(names))
        ax.hlines(y, 0, vals, color='#cccccc', lw=1.2, zorder=1)
        ax.scatter(vals, y, color=[AGENT_COLOR.get(a, '#999999') for a in names],
                   s=55, zorder=3, edgecolors='white', linewidths=0.6)
        ax.set_yticks(list(y))
        ax.set_yticklabels(names, fontsize=6.5)
        ax.set_xlim(0, max(0.55, max(vals) * 1.18))
        ax.set_xlabel('R@1 (best backbone)', fontsize=7.5)
        ax.set_title(DS_TITLE[ds], fontsize=9)
        for yi, (v, b) in enumerate(zip(vals, bbl)):
            ax.text(v + 0.012, yi, f'{v:.2f}', va='center', fontsize=6, color='#333333')
        ax.grid(True, axis='x', alpha=0.4)
        despine(ax)
        ax.text(-0.16, 1.07, chr(97 + k), transform=ax.transAxes,
                fontsize=12, fontweight='bold', va='top')
    fig.suptitle('Best-backbone agent ranking per dataset', fontsize=10,
                 fontweight='bold', y=0.99)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(FIG / 'fig3_ranking.png')
    plt.close(fig)
    print("Wrote fig3_ranking.png")


if __name__ == "__main__":
    main()
