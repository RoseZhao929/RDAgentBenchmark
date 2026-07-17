"""A6 contamination audit — TS-Guessing approximation via PubMed mention count.

Hypothesis: if R@1 correlates strongly with pre-cutoff PubMed-mention count,
the LLM may be exploiting training-frequency rather than phenotype-disease
reasoning. We treat low Spearman ρ as evidence against memorisation; high
ρ as a contamination flag.

Inputs:
  - data/round2/phase4a/predictions_*.jsonl   (per-case predictions)
  - data/orphadata/en_product9_prev.xml       (ORPHA name lookup)
  - PubMed E-utilities esearch                (mention counts pre-cutoff)

Outputs:
  - data/round2/ablations/A6_contamination.md
  - data/round2/ablations/A6_contamination.json
"""
from __future__ import annotations
import glob, json, os, re, sys, time
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

ROOT = Path("/Users/yutianzhao/Desktop/RDAgentBenchmark")
sys.path.insert(0, str(ROOT))
from harness.metrics.cross_map import gold_hit_with_crossmap
from harness.canonical_case import CanonicalCase
from harness.ingest import ingest_phenopacket_store, ingest_rarearena, ingest_rarebench

PHASE4A = ROOT / "data/round2/phase4a"
PREVALENCE_XML = ROOT / "data/orphadata/en_product9_prev.xml"
OUT_DIR = ROOT / "data/round2/ablations"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_MD = OUT_DIR / "A6_contamination.md"
OUT_JSON = OUT_DIR / "A6_contamination.json"

# Conservative cutoff that covers all 4 backbones
PUBMED_CUTOFF = "2024/06/30"
PUBMED_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

# Backbone cutoffs (kept for per-backbone refinement)
BACKBONE_CUTOFF = {
    "gemini": "2024/06/30",
    "v4-flash": "2024/06/30",
    "v4-pro": "2024/06/30",
    "gpt-5": "2024/06/30",
}


# ------------------------------------------------------------------
# 1) Disease name lookup
# ------------------------------------------------------------------
def load_orpha_names() -> dict[int, str]:
    print("Loading ORPHA names…")
    tree = ET.parse(PREVALENCE_XML)
    root = tree.getroot()
    out = {}
    for d in root.iter("Disorder"):
        ocode = d.findtext("OrphaCode")
        name = d.findtext("Name")
        if ocode and name:
            out[int(ocode)] = name
    print(f"  {len(out)} ORPHA names")
    return out


# ------------------------------------------------------------------
# 2) Build per-disease, per-backbone R@1 from phase4a predictions
# ------------------------------------------------------------------
def load_gold_map():
    print("Loading gold maps…")
    out = {}
    for c in ingest_phenopacket_store("data/phenopacket_store/notebooks"):
        out[c.case_id] = c.gold_label
    for c in ingest_rarearena("data/rarearena/benchmark_data/RDS_benchmark.jsonl", "RDS"):
        out[c.case_id] = c.gold_label
    for split in ("RAMEDIS", "LIRICAL", "MME", "HMS"):
        for c in ingest_rarebench(f"data/rarebench_hf/data_unzipped/data/{split}.jsonl", split):
            out[c.case_id] = c.gold_label
    with open("data/mimic_iv_rd_slice/cases_filtered_diverse.jsonl") as f:
        for line in f:
            c = CanonicalCase.model_validate_json(line)
            out[c.case_id] = c.gold_label
    print(f"  {len(out)} gold cases")
    return out


def extract_orpha_from_gold(gold) -> int | None:
    """gold is GoldLabel pydantic obj. Try orphanet_id direct, else None."""
    if gold.orphanet_id:
        m = re.match(r"ORPHA:(\d+)", gold.orphanet_id)
        if m:
            return int(m.group(1))
    return None


def build_perdisease_r1(gold_map, max_files=None):
    print("Scanning phase4a predictions…")
    # per_disease_backbone[(orpha, backbone)] = {ok, hits}
    per = defaultdict(lambda: {"ok": 0, "h1s": 0})
    files = sorted(glob.glob(str(PHASE4A / "predictions_*.jsonl")))
    if max_files:
        files = files[:max_files]
    for fi, p in enumerate(files):
        fn = os.path.basename(p)
        # backbone hint from filename
        bb = "other"
        if "gemini" in fn:
            bb = "gemini"
        elif "v4-flash" in fn:
            bb = "v4-flash"
        elif "v4-pro" in fn:
            bb = "v4-pro"
        elif "gpt-5" in fn:
            bb = "gpt-5"
        elif "lirical" in fn:
            bb = "lirical"
        elif "vc_rdagent" in fn:
            bb = "vc_rdagent"

        # dedupe by case_id, prefer ok
        best = {}
        try:
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
        except FileNotFoundError:
            continue

        for r in best.values():
            if r.get("status") != "ok":
                continue
            gold = gold_map.get(r["case_id"])
            if not gold:
                continue
            orpha = extract_orpha_from_gold(gold)
            if orpha is None:
                continue
            preds = r.get("ranked_predictions", [])
            if not preds:
                continue
            hit = gold_hit_with_crossmap(preds[0], gold)
            per[(orpha, bb)]["ok"] += 1
            if hit:
                per[(orpha, bb)]["h1s"] += 1
        if (fi + 1) % 20 == 0:
            print(f"  {fi + 1}/{len(files)} files")
    return per


# ------------------------------------------------------------------
# 3) PubMed mention count (E-utilities esearch)
# ------------------------------------------------------------------
def pubmed_count(disease_name: str, cutoff: str = PUBMED_CUTOFF) -> int | None:
    """Query PubMed esearch with strict daterange filter pre-cutoff.
    Returns count (int) or None on failure."""
    if not disease_name or len(disease_name) < 3:
        return None
    # quote disease name for phrase search
    q = f'"{disease_name}"[All Fields]'
    params = {
        "db": "pubmed",
        "term": q,
        "datetype": "pdat",
        "mindate": "1900/01/01",
        "maxdate": cutoff,
        "retmode": "json",
        "rettype": "count",
    }
    try:
        r = requests.get(PUBMED_URL, params=params, timeout=20)
        if r.status_code != 200:
            return None
        data = r.json()
        return int(data["esearchresult"].get("count", 0))
    except Exception:
        return None


def fetch_pubmed_counts(orpha_names: dict[int, str], orphas_to_query: list[int],
                        workers: int = 4) -> dict[int, int]:
    """Query PubMed mention count for each ORPHA's name."""
    print(f"Querying PubMed for {len(orphas_to_query)} disease names (workers={workers})…")
    out = {}
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {}
        for o in orphas_to_query:
            name = orpha_names.get(o)
            if not name:
                continue
            # NCBI throttling: stagger by 0.3s/worker to keep under 3 req/s
            time.sleep(0.3 / workers)
            futs[ex.submit(pubmed_count, name)] = (o, name)
        for i, fut in enumerate(as_completed(futs), 1):
            o, name = futs[fut]
            try:
                c = fut.result()
                if c is not None:
                    out[o] = c
            except Exception:
                pass
            if i % 50 == 0 or i == len(futs):
                dt = time.time() - t0
                print(f"  {i}/{len(futs)} queried, {dt:.0f}s elapsed, "
                      f"{i / max(dt, 1):.1f} req/s avg")
    return out


# ------------------------------------------------------------------
# 4) Spearman ρ
# ------------------------------------------------------------------
def spearman_rho(xs, ys):
    """Pure-python Spearman ρ. xs/ys same length, no ties handled specially."""
    n = len(xs)
    if n < 3:
        return None
    rx = _ranks(xs)
    ry = _ranks(ys)
    d2 = sum((rx[i] - ry[i]) ** 2 for i in range(n))
    return 1 - 6 * d2 / (n * (n * n - 1))


def _ranks(vals):
    pairs = sorted(enumerate(vals), key=lambda x: x[1])
    ranks = [0] * len(vals)
    i = 0
    while i < len(pairs):
        j = i
        while j + 1 < len(pairs) and pairs[j + 1][1] == pairs[i][1]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[pairs[k][0]] = avg
        i = j + 1
    return ranks


# ------------------------------------------------------------------
def main():
    orpha_names = load_orpha_names()
    gold_map = load_gold_map()
    per = build_perdisease_r1(gold_map)

    # Pick top-N diseases by total occurrences (across all backbones)
    occ = defaultdict(int)
    for (orpha, bb), v in per.items():
        occ[orpha] += v["ok"]
    top = sorted(occ.items(), key=lambda x: -x[1])

    # cap by N-occurrences to keep PubMed cost bounded
    top_diseases = [o for o, c in top if c >= 5][:600]  # ≥5 cases each, top 600
    print(f"\n{len(top_diseases)} diseases with ≥5 cases across backbones; "
          f"querying PubMed…")

    pm_counts = fetch_pubmed_counts(orpha_names, top_diseases, workers=4)

    # Aggregate: for each backbone, build x=log(mention+1), y=R@1
    by_bb = defaultdict(list)
    for orpha in top_diseases:
        if orpha not in pm_counts:
            continue
        name = orpha_names.get(orpha, "(unknown)")
        mention = pm_counts[orpha]
        for bb in ("gemini", "v4-flash", "v4-pro", "gpt-5", "lirical", "vc_rdagent"):
            st = per.get((orpha, bb))
            if not st or st["ok"] < 3:
                continue
            r1 = st["h1s"] / st["ok"]
            by_bb[bb].append({
                "orpha": orpha, "name": name, "mention": mention,
                "n": st["ok"], "h1": st["h1s"], "r1": r1,
            })

    rhos = {}
    for bb, rows in by_bb.items():
        if len(rows) < 10:
            continue
        # use log(mention+1) for skew correction
        import math
        xs = [math.log(r["mention"] + 1) for r in rows]
        ys = [r["r1"] for r in rows]
        rhos[bb] = {
            "n_diseases": len(rows),
            "spearman_rho": spearman_rho(xs, ys),
            "median_mention": sorted([r["mention"] for r in rows])[len(rows) // 2],
            "median_r1": sorted(ys)[len(ys) // 2],
        }

    # Write outputs
    md_lines = [
        f"# A6 — TS-Guessing Contamination Audit\n",
        f"**Cutoff date for PubMed query**: {PUBMED_CUTOFF}\n",
        "**Question**: does R@1 correlate with pre-cutoff PubMed-mention count? ",
        "High ρ → potential training-frequency exploitation; low ρ → "
        "evidence against memorisation.\n",
        "## Result — Spearman ρ (log mention count vs R@1) per backbone\n",
        "| Backbone | n diseases | Spearman ρ | Interpretation |",
        "|---|---|---|---|",
    ]
    for bb, info in sorted(rhos.items()):
        rho = info["spearman_rho"]
        if rho is None:
            interp = "(insufficient n)"
        elif abs(rho) < 0.2:
            interp = "✅ no detectable correlation"
        elif abs(rho) < 0.4:
            interp = "🟡 weak"
        elif abs(rho) < 0.6:
            interp = "🟠 moderate (possible bias)"
        else:
            interp = "🔴 strong (contamination signal)"
        md_lines.append(f"| `{bb}` | {info['n_diseases']} | "
                        f"{rho:.3f} | {interp} |" if rho is not None else
                        f"| `{bb}` | {info['n_diseases']} | n/a | {interp} |")
    md_lines += [
        "\n## Interpretation\n",
        "We treat |ρ| < 0.2 as evidence the agents' R@1 is **independent** of "
        "the disease's pre-cutoff PubMed exposure, defeating the simplest "
        "data-contamination critique (reviewer attack #1). Higher |ρ| would "
        "warrant the post-cutoff holdout (L4) as the primary evaluation lens.\n",
        f"\n**Methodology**:",
        f"\n- Disease list: top-{len(top_diseases)} ORPHA codes by occurrence in our "
        f"phase4a predictions (≥5 cases each).",
        f"\n- PubMed mention: `esearch.fcgi` with `\"<disease name>\"[All Fields]` and "
        f"`maxdate={PUBMED_CUTOFF}`.",
        f"\n- R@1: gold_hit_with_crossmap on Top-1 prediction, aggregated per "
        f"(disease, backbone), requiring ≥3 cases per disease in that backbone.",
        f"\n- Spearman ρ: ranks log(mention+1) vs R@1.",
    ]
    OUT_MD.write_text("\n".join(md_lines))
    out_data = {
        "cutoff": PUBMED_CUTOFF,
        "n_diseases_queried": len(top_diseases),
        "n_pubmed_results": len(pm_counts),
        "rhos": rhos,
        "by_backbone": dict(by_bb),
    }
    OUT_JSON.write_text(json.dumps(out_data, indent=2, default=str))
    print(f"\nWrote {OUT_MD} and {OUT_JSON}")
    print("\nSummary:")
    for bb, info in sorted(rhos.items()):
        print(f"  {bb}: ρ={info['spearman_rho']:.3f}  n={info['n_diseases']}")


if __name__ == "__main__":
    os.chdir(ROOT)
    main()
