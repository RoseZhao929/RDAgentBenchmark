"""Regenerate phase4a_receipts.csv + 4 new analytic figures (F4-F7).

F4: A6 contamination ρ scatter (log mention vs R@1, per backbone)
F5: Prevalence stratification curve (H1: LLM vs classical across tiers)
F6: HPO phenotype density inverted-U (H8)
F7: Specialty rank heatmap (H7)

Receipt CSV: phase4a_receipts.csv with per-cell {ok, err, R@1s, R@1v, R@5s,
R@5v, cost_usd, mean_lat_ms, n_done}.
"""
from __future__ import annotations
import csv
import glob
import json
import math
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path("/Users/yutianzhao/Desktop/RDAgentBenchmark")
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _figstyle import apply_nature_style, AGENT_COLOR, despine  # noqa: E402
from harness.canonical_case import CanonicalCase
from harness.metrics.cross_map import gold_hit_with_crossmap, gold_hit_with_variants
from harness.ingest import (
    ingest_phenopacket_store, ingest_rarearena, ingest_rarebench,
)

PHASE4A = ROOT / "data/round2/phase4a"
FIG = ROOT / "data/round2/figures"
RECEIPT_CSV = ROOT / "data/round2/phase4a_receipts.csv"
A6_JSON = ROOT / "data/round2/ablations/A6_contamination.json"
H1_MD = ROOT / "data/round2/ablations/H1_prevalence_real.md"
H8_MD = ROOT / "data/round2/ablations/H8_phenotype_density.md"
H7_MD = ROOT / "data/round2/ablations/H4_H7_specialty.md"


# ------------------------------------------------------------------
# load gold
# ------------------------------------------------------------------
def load_gold_map():
    out = {}
    for c in ingest_phenopacket_store("data/phenopacket_store/notebooks"):
        out[c.case_id] = ("phenopacket_store", c.gold_label)
    for c in ingest_rarearena("data/rarearena/benchmark_data/RDS_benchmark.jsonl", "RDS"):
        out[c.case_id] = ("rarearena_rds", c.gold_label)
    for split in ("RAMEDIS", "LIRICAL", "MME", "HMS"):
        for c in ingest_rarebench(f"data/rarebench_hf/data_unzipped/data/{split}.jsonl", split):
            out[c.case_id] = ("rarebench", c.gold_label)
    with open("data/mimic_iv_rd_slice/cases_filtered_diverse.jsonl") as f:
        for line in f:
            c = CanonicalCase.model_validate_json(line)
            out[c.case_id] = ("mimic_diverse", c.gold_label)
    return out


# ------------------------------------------------------------------
# Per-cell receipts
# ------------------------------------------------------------------
def receipt_per_cell(gold_map):
    stats = defaultdict(lambda: {
        "n_ok": 0, "n_err": 0,
        "h1s": 0, "h1v": 0, "h5s": 0, "h5v": 0,
        "cost_usd": 0.0, "sum_lat_ms": 0, "lat_n": 0,
    })
    # 2026-07-08: pp/rarearena are stratified samples harmonized to a common
    # N=2000 (seed=42 prefix). Aggregate only on that canonical case-id set so
    # every backbone reports on identical cases (Gemini historical over-runs
    # capped to 2000; V4-Flash shortfalls report on the subset they cover).
    _canon = {}
    _canon_path = ROOT / "data/round2/phase4a_canonical_2000.json"
    if _canon_path.exists():
        _canon = {k: set(v) for k, v in json.loads(_canon_path.read_text()).items()}
    for p in sorted(glob.glob(str(PHASE4A / "predictions_*.jsonl"))):
        fn = os.path.basename(p).replace("predictions_", "").replace(".jsonl", "")
        ds = ag = bb = None
        for d in ("phenopacket_store", "rarearena_rds", "rarebench", "mimic_diverse"):
            if fn.startswith(d + "_"):
                ds = d
                rest = fn[len(d) + 1:]
                break
        if not ds:
            continue
        for a in ("mdagents", "medagents", "agentclinic", "maidxo", "deeprare",
                  "llm_control", "vc_rdagent", "lirical"):
            if rest.startswith(a + "_"):
                ag = a
                bb = rest[len(a) + 1:]
                break
        if not ag:
            continue
        key = (ds, ag, bb[:40])
        best = {}
        with open(p) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                cid = r.get("case_id")
                if cid is None:
                    continue
                prev = best.get(cid)
                if prev is None or (r.get("status") == "ok" and prev.get("status") != "ok"):
                    best[cid] = r
        # cap pp/rarearena to the canonical N=2000 case-id set (comparability)
        if ds in _canon:
            best = {cid: r for cid, r in best.items() if cid in _canon[ds]}
        for r in best.values():
            s = r.get("status", "?")
            if s != "ok":
                stats[key]["n_err"] += 1
                continue
            stats[key]["n_ok"] += 1
            stats[key]["cost_usd"] += (r.get("cost", {}) or {}).get("cost_usd", 0) or 0
            lat = r.get("total_latency_ms")
            if lat:
                stats[key]["sum_lat_ms"] += lat
                stats[key]["lat_n"] += 1
            _, g = gold_map.get(r["case_id"], (None, None))
            if not g:
                continue
            preds = r.get("ranked_predictions", [])
            variants = r.get("extra", {}).get("ranked_predictions_variants") or []
            if preds and gold_hit_with_crossmap(preds[0], g):
                stats[key]["h1s"] += 1
            if any(gold_hit_with_crossmap(p, g) for p in preds[:5]):
                stats[key]["h5s"] += 1
            if variants:
                if gold_hit_with_variants(variants[0], g):
                    stats[key]["h1v"] += 1
                if any(gold_hit_with_variants(v, g) for v in variants[:5]):
                    stats[key]["h5v"] += 1
            else:
                if preds and gold_hit_with_crossmap(preds[0], g):
                    stats[key]["h1v"] += 1
                if any(gold_hit_with_crossmap(p, g) for p in preds[:5]):
                    stats[key]["h5v"] += 1

    # write CSV
    with open(RECEIPT_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "dataset", "agent", "backbone", "n_ok", "n_err",
            "R@1_strict", "R@1_variants", "R@5_strict", "R@5_variants",
            "cost_usd", "mean_lat_ms",
        ])
        for (ds, ag, bb), s in sorted(stats.items()):
            ok = s["n_ok"]
            r1s = s["h1s"] / ok if ok else 0
            r1v = s["h1v"] / ok if ok else 0
            r5s = s["h5s"] / ok if ok else 0
            r5v = s["h5v"] / ok if ok else 0
            mlat = s["sum_lat_ms"] / s["lat_n"] if s["lat_n"] else 0
            w.writerow([
                ds, ag, bb, ok, s["n_err"],
                f"{r1s:.3f}", f"{r1v:.3f}", f"{r5s:.3f}", f"{r5v:.3f}",
                f"{s['cost_usd']:.4f}", f"{mlat:.0f}",
            ])
    print(f"Wrote {RECEIPT_CSV}: {len(stats)} cells")
    return stats


# ------------------------------------------------------------------
# Figures
# ------------------------------------------------------------------
def fig4_a6_scatter():
    """A6 contamination ρ scatter — one panel per backbone."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    apply_nature_style()

    if not A6_JSON.exists():
        print(f"  F4 skip — {A6_JSON} missing")
        return
    data = json.loads(A6_JSON.read_text())
    by_bb = data["by_backbone"]
    rhos = data["rhos"]

    panels = [bb for bb in ("gemini", "v4-flash", "v4-pro", "gpt-5",
                            "lirical", "vc_rdagent") if bb in by_bb]
    n = len(panels)
    cols = 3
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(13, 4 * rows))
    axes = axes.flatten() if hasattr(axes, "flatten") else [axes]
    for i, bb in enumerate(panels):
        ax = axes[i]
        rows_data = by_bb[bb]
        xs = [math.log10(r["mention"] + 1) for r in rows_data]
        ys = [r["r1"] for r in rows_data]
        rho_info = rhos.get(bb, {})
        ax.scatter(xs, ys, alpha=0.5, s=22, edgecolor="none")
        ax.set_xlabel("log10(PubMed mentions pre-2024-07 + 1)")
        ax.set_ylabel("Per-disease R@1")
        ax.set_title(f"{bb} — Spearman ρ = {rho_info.get('spearman_rho', 0):.3f} "
                     f"(n={rho_info.get('n_diseases', 0)})", fontsize=10)
        ax.set_ylim(-0.05, 1.05)
        ax.grid(True, alpha=0.3)
    for j in range(n, len(axes)):
        axes[j].axis("off")
    fig.suptitle("F4 — A6 contamination audit: LLM backbones ρ≈0.3 (weak), "
                 "classical baselines ρ≈0 (null control)", y=1.00, fontsize=11)
    plt.tight_layout()
    out = FIG / "fig4_a6_contamination_scatter.png"
    plt.savefig(out, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  F4 wrote {out}")


def _parse_md_table(md_text, header_keyword):
    """Parse first markdown table after a line matching header_keyword."""
    lines = md_text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if header_keyword in ln:
            for j in range(i, min(i + 8, len(lines))):
                if lines[j].lstrip().startswith("|"):
                    start = j
                    break
            if start:
                break
    if start is None:
        return None, None
    # collect contiguous table rows
    rows = []
    headers = None
    for j in range(start, len(lines)):
        ln = lines[j].strip()
        if not ln.startswith("|"):
            break
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells):
            continue
        if headers is None:
            headers = cells
        else:
            rows.append(cells)
    return headers, rows


def fig5_prevalence_curve():
    """H1: R@1 across prevalence tiers — LLM vs classical.
    H1_prevalence_real.md has TWO separate tables (LLM section, classical section),
    each with columns [Tier, n, R@1]. We extract both and overlay them."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    apply_nature_style()

    if not H1_MD.exists():
        print("  F5 skip — H1_prevalence_real.md missing")
        return
    txt = H1_MD.read_text()

    def _grab_after(marker):
        idx = txt.find(marker)
        if idx < 0:
            return {}
        # stop at next section header `## `
        next_hdr = txt.find("\n## ", idx + len(marker))
        end = next_hdr if next_hdr > 0 else idx + 1500
        sub = txt[idx + len(marker): end]
        out = {}
        for ln in sub.splitlines():
            ln = ln.strip()
            if not ln.startswith("|"):
                continue
            cells = [c.strip() for c in ln.strip("|").split("|")]
            if len(cells) < 3:
                continue
            tier = cells[0].lower().replace("_", "-")
            m = re.search(r"^[\d.]+$", cells[2])
            if not m:
                continue
            out[tier] = float(cells[2])
        return out

    llm_vals = _grab_after("## LLM agents")
    cls_vals = _grab_after("## Classical/offline")

    tier_order = ["common-rare", "moderate", "ultra-rare", "super-rare"]
    xs = [t for t in tier_order if t in llm_vals or t in cls_vals]
    if not xs:
        print(f"  F5 skip — llm_vals={llm_vals}, cls_vals={cls_vals}")
        return
    llm_y = [llm_vals.get(t) for t in xs]
    cls_y = [cls_vals.get(t) for t in xs]

    fig, ax = plt.subplots(figsize=(8.5, 5))
    ax.plot(xs, llm_y, "o-", label="LLM agents (Gemini Flash)", linewidth=2.5,
            markersize=11, color="#2C7FB8")
    ax.plot(xs, cls_y, "s-", label="Classical / Offline (LIRICAL + VC-RDAgent)",
            linewidth=2.5, markersize=11, color="#E37222")
    # annotate gap on rarest
    if xs[-1] == "super-rare":
        gap = (cls_y[-1] or 0) - (llm_y[-1] or 0)
        ax.annotate(f"Δ = +{gap:.2f}", xy=(len(xs) - 1, (cls_y[-1] + llm_y[-1]) / 2),
                    xytext=(len(xs) - 1.5, 0.4), fontsize=11,
                    arrowprops=dict(arrowstyle="->", color="black", lw=1))
    ax.set_xlabel("Prevalence tier (commonest → rarest →)")
    ax.set_ylabel("Pooled R@1")
    ax.set_title("F5 — H1: Prevalence stratification\n"
                 "LLM declines on rarest tier; classical *rises*; gap +28 pp",
                 fontsize=11)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right")
    ax.set_ylim(0, 0.6)
    plt.tight_layout()
    out = FIG / "fig5_prevalence_h1.png"
    plt.savefig(out, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  F5 wrote {out}")


def fig6_hpo_density():
    """H8: phenotype density inverted-U."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    apply_nature_style()

    if not H8_MD.exists():
        print("  F6 skip — H8_phenotype_density.md missing")
        return
    txt = H8_MD.read_text()
    hdr, rows = _parse_md_table(txt, "HPO")
    if not rows:
        print("  F6 skip — no table parsed")
        return
    xs, ys = [], []
    for r in rows:
        bin_label = r[0]
        m = re.search(r"([\d.]+)", r[-1])
        if m:
            xs.append(bin_label)
            ys.append(float(m.group(1)))
    if not xs:
        print("  F6 skip")
        return
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(range(len(xs)), ys, color="#2C7FB8", alpha=0.85)
    peak = ys.index(max(ys))
    ax.bar([peak], [ys[peak]], color="#E37222", alpha=0.95, label="peak")
    ax.set_xticks(range(len(xs)))
    ax.set_xticklabels(xs, rotation=20)
    ax.set_xlabel("HPO terms per case (binned)")
    ax.set_ylabel("R@1 (pooled across LLM agents)")
    ax.set_title("F6 — H8: Phenotype density inverted-U (peak ≈ 16–30 HPO terms)\n"
                 "Both too-sparse and too-dense input degrade LLM diagnosis", fontsize=11)
    ax.grid(True, alpha=0.3, axis="y")
    ax.legend()
    plt.tight_layout()
    out = FIG / "fig6_hpo_density_h8.png"
    plt.savefig(out, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  F6 wrote {out}")


def fig7_specialty_heatmap():
    """H7: per-specialty R@1 cross-agent.
    The H7 table has rows like:
      | nervous system | 0.11(258) | 0.14(258) | ... |
    where the parens hold n. We parse R@1 only."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    apply_nature_style()
    import numpy as np

    if not H7_MD.exists():
        print("  F7 skip — H4_H7_specialty.md missing")
        return
    txt = H7_MD.read_text()
    marker = "## H7 — Specialty R@1 per agent"
    idx = txt.find(marker)
    if idx < 0:
        print("  F7 skip — H7 specialty section not found")
        return
    # stop at the next `## ` (skip the Spearman correlation table)
    next_hdr = txt.find("\n## ", idx + len(marker))
    end = next_hdr if next_hdr > 0 else idx + 5000
    sub = txt[idx + len(marker): end]

    headers = None
    rows = []
    for ln in sub.splitlines():
        ln = ln.strip()
        if not ln.startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells):
            continue
        if headers is None:
            headers = cells
            continue
        rows.append(cells)
    if not rows or not headers or len(headers) < 3:
        print(f"  F7 skip — parse failed, headers={headers}, rows={len(rows or [])}")
        return

    agents = [h.replace("`", "") for h in headers[1:]]
    n_agents = len(agents)
    specs = []
    mat = []
    for r in rows:
        spec = r[0]
        cols = r[1:1 + n_agents]
        # pad/truncate to exact n_agents columns
        if len(cols) < n_agents:
            cols = cols + [""] * (n_agents - len(cols))
        cols = cols[:n_agents]
        vals = []
        any_num = False
        for c in cols:
            m = re.match(r"^(-?[\d.]+)", c)
            if m:
                vals.append(float(m.group(1)))
                any_num = True
            else:
                vals.append(0.0)
        if any_num:
            specs.append(spec)
            mat.append(vals)

    if not mat:
        print("  F7 skip — empty matrix")
        return
    arr = np.array(mat)
    fig, ax = plt.subplots(figsize=(0.85 * len(agents) + 5, 0.36 * len(specs) + 2.5))
    im = ax.imshow(arr, aspect="auto", cmap="YlOrRd", vmin=0, vmax=0.7)
    # cell annotations
    for i in range(len(specs)):
        for j in range(len(agents)):
            v = arr[i, j]
            ax.text(j, i, f"{v:.2f}" if v > 0 else "—",
                    ha="center", va="center", fontsize=7,
                    color="white" if v > 0.4 else "black")
    ax.set_xticks(range(len(agents)))
    ax.set_xticklabels(agents, rotation=30, ha="right", fontsize=9)
    ax.set_yticks(range(len(specs)))
    ax.set_yticklabels(specs, fontsize=8)
    fig.colorbar(im, ax=ax, label="R@1", shrink=0.7)
    ax.set_title("F7 — H7: Per-specialty R@1 cross-agent (HPO organ-system axis)\n"
                 "Universal weak (low across row): nervous, metabolic, digestive — "
                 "classical inverts on nervous (LIRICAL 0.35, VC-RDAgent 0.43)",
                 fontsize=10)
    plt.tight_layout()
    out = FIG / "fig7_specialty_h7.png"
    plt.savefig(out, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  F7 wrote {out}")


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--figs-only", action="store_true",
                    help="skip receipts regen (slow gold-load), only figures")
    args = ap.parse_args()

    if not args.figs_only:
        print("Loading gold maps…")
        gold = load_gold_map()
        print(f"  {len(gold)} gold cases")
        print("Regenerating receipts…")
        receipt_per_cell(gold)
    print("Figures:")
    fig4_a6_scatter()
    fig5_prevalence_curve()
    fig6_hpo_density()
    fig7_specialty_heatmap()


if __name__ == "__main__":
    main()
