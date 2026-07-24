"""Static diagnostic-task leaderboard site (P6.4).

Reads audit_frozen/frozen_main_manifest.csv, emits a
single self-contained index.html under leaderboard/ with:
  - per-dataset matrix (attempted-denominator R@1 variants + strict + 95% CI)
  - cost summary
  - downloadable diagnostic-only manifest

No JS framework; minimal CSS for legibility. Suitable for GitHub Pages.
"""
from __future__ import annotations
import ast
import csv
import html
import json
from pathlib import Path

BBL = {
    'google_gemini-3-flash-preview-': 'Gemini Flash',
    'deepseek_deepseek-v4-pro': 'DS V4-Pro',
    'deepseek_deepseek-v4-flash': 'DS V4-Flash',
    'openai_gpt-5': 'GPT-5 min',
    'vc_rdagent-offline-v1': 'offline',
    'lirical-2.4.0': 'classical',
}
BB_ORDER = ['google_gemini-3-flash-preview-','deepseek_deepseek-v4-pro',
            'deepseek_deepseek-v4-flash','openai_gpt-5',
            'vc_rdagent-offline-v1','lirical-2.4.0']
AGENT_ORDER = ['llm_control','mdagents','medagents','agentclinic','maidxo',
               'deeprare','vc_rdagent','lirical']
DS = ['phenopacket_store','rarearena_rds','rarebench']
DS_LABEL = {'phenopacket_store':'Phenopacket-Store','rarearena_rds':'RareArena RDS',
            'rarebench':'RareBench HF'}

def load():
    pairs = {}
    with open('audit_frozen/frozen_main_manifest.csv', newline='') as handle:
        for row in csv.DictReader(handle):
            if row['dataset'] not in DS or row['capability'] != 'P2_phenotype_ddx':
                continue
            row['n_attempted'] = int(row['n_attempted'])
            row['n_successful'] = int(row['n_successful'])
            row['R@1_variant_aware'] = float(row['R@1_variant_aware'])
            row['R@1_strict'] = float(row['R@1_strict'])
            row['total_cost_usd'] = float(row['total_cost_usd'] or 0)
            row['bootstrap_95CI'] = ast.literal_eval(row['bootstrap_95CI'])
            pairs[(row['dataset'], row['system'], row['backbone'])] = row
    return pairs

def colorbar(r1):
    """Return a hex shade for R@1 in [0, 0.6]."""
    if r1 is None: return '#f3f4f6'
    x = max(0.0, min(1.0, r1 / 0.55))
    # green-yellow scale: low=light, high=deep amber
    r = int(255); g = int(255 - 100*x); b = int(220 - 200*x)
    return f'#{r:02x}{g:02x}{b:02x}'

def render_matrix(ds, pairs):
    rows = ['<table class="grid">']
    head = ['<th></th>'] + [f'<th>{BBL.get(b,b)}</th>' for b in BB_ORDER]
    rows.append('<tr>' + ''.join(head) + '</tr>')
    for ag in AGENT_ORDER:
        cells = [f'<th class="ag">{ag}</th>']
        for bb in BB_ORDER:
            s = pairs.get((ds, ag, bb))
            if not s or s['n_attempted'] == 0:
                cells.append('<td class="na">—</td>'); continue
            r1v = s['R@1_variant_aware']
            r1s = s['R@1_strict']
            n = s['n_attempted']
            lo, hi = s['bootstrap_95CI']
            ci_str = f' <span class="ci">[{lo:.2f}–{hi:.2f}]</span>'
            tip = f'strict {r1s:.2f}, attempted N={n}, successful={s["n_successful"]}'
            cells.append(f'<td title="{html.escape(tip)}" style="background:{colorbar(r1v)}">'
                         f'<b>{r1v:.2f}</b>{ci_str}<br><span class="n">N={n}</span></td>')
        rows.append('<tr>' + ''.join(cells) + '</tr>')
    rows.append('</table>')
    return '\n'.join(rows)

def main():
    pairs = load()
    # cost summary
    by_bb = {}
    for (_, _, bb), s in pairs.items():
        by_bb.setdefault(bb, {'n':0,'usd':0.0})
        by_bb[bb]['n'] += s['n_successful']
        by_bb[bb]['usd'] += s['total_cost_usd']
    cost_rows = ''.join(
        f'<tr><td>{BBL.get(b,b)}</td><td>{d["n"]:,}</td><td>${d["usd"]:.2f}</td>'
        f'<td>${(d["usd"]/d["n"]) if d["n"] else 0:.5f}</td></tr>'
        for b, d in sorted(by_bb.items(), key=lambda kv: -kv[1]['usd']))
    total_n = sum(d['n'] for d in by_bb.values())
    total_usd = sum(d['usd'] for d in by_bb.values())

    matrices = '\n'.join(
        f'<h2 id="{ds}">{DS_LABEL[ds]}</h2>\n{render_matrix(ds, pairs)}'
        for ds in DS)

    css = """
    body{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:1100px;
        margin:30px auto;padding:0 18px;color:#1f2937;line-height:1.5}
    h1{font-size:1.6em;border-bottom:2px solid #1f2937;padding-bottom:.3em}
    h2{margin-top:1.6em;font-size:1.15em;color:#374151}
    table.grid{border-collapse:separate;border-spacing:0;width:100%;font-size:.85em;
        box-shadow:0 1px 3px rgba(0,0,0,.07);margin-bottom:.8em}
    table.grid th,table.grid td{padding:6px 8px;text-align:center;border-bottom:1px solid #e5e7eb}
    table.grid th{background:#f9fafb;font-weight:600;color:#374151}
    table.grid th.ag{text-align:left;background:#fff;color:#111}
    table.grid td b{font-size:1em}
    table.grid td .ci{color:#6b7280;font-size:.82em}
    table.grid td .n{color:#9ca3af;font-size:.75em}
    table.grid td.na{color:#9ca3af}
    table.cost{border-collapse:collapse;margin:.6em 0}
    table.cost td,table.cost th{padding:5px 12px;border:1px solid #d1d5db}
    table.cost th{background:#f3f4f6}
    .meta{color:#6b7280;font-size:.9em;margin-bottom:1em}
    .nav a{margin-right:14px;color:#1d4ed8;text-decoration:none}
    code{background:#f3f4f6;padding:1px 5px;border-radius:3px;font-size:.9em}
    """
    html_doc = f"""<!doctype html><meta charset="utf-8">
<title>Rare-Disease Agent Benchmark — Leaderboard</title>
<style>{css}</style>
<h1>Rare-Disease Agent Benchmark — Leaderboard</h1>
<div class="meta">
  Generated from <code>audit_frozen/frozen_main_manifest.csv</code>.
  Per cell: attempted-denominator <b>R@1 (variant-aware)</b> with 95% bootstrap
  CI; strict R@1 and successful N are shown in the tooltip. MIMIC is excluded
  because its replacement structured-EHR task has not yet been scored. See
  <code>paper_sections/A1_reproducibility_audit.md</code> and
  <code>docs/baseline_repro/</code>.
</div>
<div class="nav">
  {' '.join(f'<a href="#{d}">{DS_LABEL[d]}</a>' for d in DS)}
  <a href="#cost">Cost</a>
  <a href="frozen_diagnostic_manifest.json">diagnostic manifest</a>
</div>
{matrices}
<h2 id="cost">Cost summary</h2>
<table class="cost">
  <tr><th>Backbone</th><th>Predictions</th><th>Total $</th><th>$ / pred</th></tr>
  {cost_rows}
  <tr><th>TOTAL</th><th>{total_n:,}</th><th>${total_usd:.2f}</th><th>${total_usd/total_n:.5f}</th></tr>
</table>
<p class="meta">
  Findings (FWE-corrected Holm-Bonferroni, §8.8): H1 (classical &gt; LLM on
  super-rare) and H8 (phenotype-density inverted-U) survive α=0.05; full
  hypothesis table in <code>data/round2/ablations/holm_H_family.md</code>.
</p>
"""
    out = Path('leaderboard/index.html')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_doc)
    manifest = [
        value for (_, _, _), value in sorted(pairs.items())
    ]
    (out.parent / 'frozen_diagnostic_manifest.json').write_text(
        json.dumps(manifest, indent=2, sort_keys=True)
    )
    print(f"Wrote {out} ({out.stat().st_size:,} bytes)")
    print(f"  + {len(list(out.parent.iterdir()))} files in {out.parent}/")

if __name__=='__main__':
    main()
