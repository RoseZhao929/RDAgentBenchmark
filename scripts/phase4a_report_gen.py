"""Phase 4a paper-grade aggregate report generator.

Reads all data/round2/phase4a/predictions_*.jsonl, builds the per-dataset
backbone × agent R@1 matrix (strict + variants), and writes:
  - data/round2/phase4a_REPORT.md (paper-grade)
  - data/round2/phase4a_summary.json (machine-readable)

Designed to be re-runnable as new cells finish.
"""
from __future__ import annotations
import sys, json, os, glob
from pathlib import Path
from collections import defaultdict
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def main():
    from harness.canonical_case import CanonicalCase
    from harness.metrics.cross_map import gold_hit_with_crossmap, gold_hit_with_variants
    from harness.ingest import ingest_phenopacket_store, ingest_rarearena, ingest_rarebench
    print("Loading gold maps...", file=sys.stderr)
    case_gold_all = {}
    for c in ingest_phenopacket_store('data/phenopacket_store/notebooks'): case_gold_all[c.case_id] = ('phenopacket_store', c.gold_label)
    for c in ingest_rarearena('data/rarearena/benchmark_data/RDS_benchmark.jsonl', 'RDS'): case_gold_all[c.case_id] = ('rarearena_rds', c.gold_label)
    for split in ('RAMEDIS','LIRICAL','MME','HMS'):
        for c in ingest_rarebench(f'data/rarebench_hf/data_unzipped/data/{split}.jsonl', split): case_gold_all[c.case_id] = ('rarebench', c.gold_label)
    with open('data/mimic_iv_rd_slice/cases_filtered_diverse.jsonl') as f:
        for line in f:
            c = CanonicalCase.model_validate_json(line); case_gold_all[c.case_id] = ('mimic_diverse', c.gold_label)
    print(f"Total gold cases: {len(case_gold_all)}", file=sys.stderr)

    stats = defaultdict(lambda: {"ok":0,"err":0,"h1s":0,"h1v":0,"h5s":0,"h5v":0,"sum_usd":0.0,"sum_lat_ms":0})
    # 2026-07-08: canonical N=2000 cap for pp/rarearena (same as receipts regen)
    _canon = {}
    _cp = 'data/round2/phase4a_canonical_2000.json'
    if os.path.exists(_cp):
        _canon = {k: set(v) for k, v in json.load(open(_cp)).items()}
    for p in sorted(glob.glob('data/round2/phase4a/predictions_*.jsonl')):
        fn = os.path.basename(p).replace('predictions_','').replace('.jsonl','')
        ds = ag = None
        for d in ('phenopacket_store','rarearena_rds','rarebench','mimic_diverse'):
            if fn.startswith(d+'_'): ds = d; rest = fn[len(d)+1:]; break
        if not ds: continue
        for a in ('mdagents','medagents','agentclinic','maidxo','deeprare','llm_control','vc_rdagent','lirical'):
            if rest.startswith(a+'_'): ag = a; bb = rest[len(a)+1:]; break
        if not ag: continue
        key = (ds, ag, bb[:30])
        # Dedupe by case_id (2026-05-28): RESUME mode re-attempts non-ok cases
        # and appends, so a recovered case has stale parser_error/timeout lines
        # plus a final ok line. Counting every line double-counts. Keep one
        # record per case_id, preferring `ok` (then the last-seen status).
        best: dict[str, dict] = {}
        with open(p) as f:
            for line in f:
                r = json.loads(line)
                cid = r.get('case_id')
                if cid is None:
                    continue
                prev = best.get(cid)
                if prev is None or (r.get('status') == 'ok' and prev.get('status') != 'ok'):
                    best[cid] = r
                elif prev.get('status') != 'ok':
                    best[cid] = r  # last non-ok wins until an ok shows up
        if ds in _canon:
            best = {cid: r for cid, r in best.items() if cid in _canon[ds]}
        for r in best.values():
            s = r.get('status', '?')
            if s != 'ok':
                stats[key]['err'] += 1
                continue
            stats[key]['ok'] += 1
            stats[key]['sum_usd'] += (r.get('cost', {}) or {}).get('cost_usd', 0) or 0
            stats[key]['sum_lat_ms'] += r.get('total_latency_ms', 0) or 0
            _, g = case_gold_all.get(r['case_id'], (None, None))
            if not g:
                continue
            preds = r.get('ranked_predictions', [])
            variants = r.get('extra', {}).get('ranked_predictions_variants') or []
            if preds and gold_hit_with_crossmap(preds[0], g): stats[key]['h1s'] += 1
            if any(gold_hit_with_crossmap(p, g) for p in preds[:5]): stats[key]['h5s'] += 1
            if variants:
                if gold_hit_with_variants(variants[0], g): stats[key]['h1v'] += 1
                if any(gold_hit_with_variants(v, g) for v in variants[:5]): stats[key]['h5v'] += 1
            else:
                if preds and gold_hit_with_crossmap(preds[0], g): stats[key]['h1v'] += 1
                if any(gold_hit_with_crossmap(p, g) for p in preds[:5]): stats[key]['h5v'] += 1

    # Write report
    bbs_o = ['google_gemini-3-flash-preview-20251217','deepseek_deepseek-v4-pro','deepseek_deepseek-v4-flash','openai_gpt-5','vc_rdagent-offline-v1','lirical-2.4.0']
    bb_label = {'google_gemini-3-flash-preview-20251217':'Gemini Flash','deepseek_deepseek-v4-pro':'DS V4-Pro','deepseek_deepseek-v4-flash':'DS V4-Flash','openai_gpt-5':'GPT-5 min','vc_rdagent-offline-v1':'offline','lirical-2.4.0':'classical'}
    agents_o = ['llm_control','mdagents','medagents','agentclinic','maidxo','deeprare','vc_rdagent','lirical']

    md_lines = [
        "# Phase 4a Mini-Sample Report (N=100 × 4 datasets)",
        "",
        "**Generated**:", f"`{__import__('datetime').datetime.now().isoformat(timespec='seconds')}`",
        "",
        "## Per-dataset matrix (R@1 variants — strict in parentheses)",
        "",
    ]
    for ds in ('phenopacket_store','rarearena_rds','rarebench','mimic_diverse'):
        md_lines.append(f"\n### {ds}\n")
        header = "| Agent | " + " | ".join(bb_label[b] for b in bbs_o) + " |"
        md_lines.append(header)
        md_lines.append("|" + "|".join(["---"]*(len(bbs_o)+1)) + "|")
        for ag in agents_o:
            row = [f"| `{ag}`"]
            for bb in bbs_o:
                s = stats.get((ds, ag, bb[:30]))
                if not s or s['ok']==0:
                    row.append("—")
                else:
                    r1v = s['h1v']/s['ok']; r1s = s['h1s']/s['ok']
                    row.append(f"**{r1v:.2f}** ({r1s:.2f}) [{s['ok']}/{s['ok']+s['err']}]")
            md_lines.append(" | ".join(row) + " |")

    # Cost summary
    md_lines += ["\n## Cost summary (recomputed from tokens × price table)\n", "| Backbone | Total predictions | Sum cost USD |", "|---|---|---|"]
    by_bb = defaultdict(lambda: {"n":0,"usd":0.0})
    for (ds, ag, bb), s in stats.items():
        by_bb[bb]['n'] += s['ok']
        by_bb[bb]['usd'] += s['sum_usd']
    for bb, d in sorted(by_bb.items()):
        md_lines.append(f"| `{bb[:30]}` | {d['n']} | ${d['usd']:.3f} |")
    total_usd = sum(d['usd'] for d in by_bb.values())
    total_n = sum(d['n'] for d in by_bb.values())
    md_lines.append(f"| **TOTAL** | **{total_n}** | **${total_usd:.3f}** |")

    Path('data/round2/phase4a_REPORT.md').write_text("\n".join(md_lines))
    summary = {f"{ds}|{ag}|{bb}": s for (ds, ag, bb), s in stats.items()}
    Path('data/round2/phase4a_summary.json').write_text(json.dumps(summary, indent=2))
    print(f"Wrote phase4a_REPORT.md ({len(md_lines)} lines) + phase4a_summary.json")

if __name__ == "__main__":
    main()
