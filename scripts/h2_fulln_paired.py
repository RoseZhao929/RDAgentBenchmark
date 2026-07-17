"""H2 full-N — paired variant-channel lift (P3 with variants vs P2 without),
same llm_control agent, same PP-Store variant cases, same backbone.

Upgrades the pilot H2 (n=50, holm-adj p=0.074 borderline) to full-N so the
+~20pp genotype-channel lift can be tested with adequate power. Paired McNemar
+ 2-proportion z on identical case_ids.

Output: data/round2/phase3/H2_fullN.{jsonl,md}
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.agents._adapter_utils import load_dotenv
load_dotenv()
from harness.ingest import ingest_phenopacket_store
from harness.agents.llm_control import LLMControlAdapter
from harness.metrics.cross_map import gold_hit_with_crossmap

N = int(sys.argv[1]) if len(sys.argv) > 1 else 500
BACKBONE = "openrouter/google/gemini-3-flash-preview-20251217"
OUT = Path("data/round2/phase3/H2_fullN.jsonl")
MD = Path("data/round2/phase3/H2_fullN.md")


def sample(seed=42, n=500):
    import random
    allc = list(ingest_phenopacket_store("data/phenopacket_store/notebooks"))
    wv = [c for c in allc if c.variants]
    random.Random(seed).shuffle(wv)
    return wv[:n]


def main():
    cases = sample(n=N)
    print(f"[H2] {len(cases)} PP-Store variant cases; backbone Gemini Flash", flush=True)
    ad = LLMControlAdapter(backbone_id=BACKBONE)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fout = OUT.open("w")
    rows = []
    for i, c in enumerate(cases, 1):
        gold = c.gold_label
        rec = {"case_id": c.case_id}
        for pillar, key in [("P2_phenotype_ddx", "p2"), ("P3_genotype_aware", "p3")]:
            try:
                log = ad.predict(c, pillar=pillar, eval_mode="gold_hpo")
                d = log.model_dump() if hasattr(log, "model_dump") else log
                preds = d.get("ranked_predictions", [])
                hit = bool(gold and preds and gold_hit_with_crossmap(preds[0], gold))
                rec[key] = {"status": d.get("status"), "hit": hit, "top1": preds[0] if preds else None}
            except Exception as e:
                rec[key] = {"status": f"err:{type(e).__name__}", "hit": False, "top1": None}
        fout.write(json.dumps(rec) + "\n"); fout.flush()
        rows.append(rec)
        if i % 25 == 0:
            p2h = sum(r["p2"]["hit"] for r in rows); p3h = sum(r["p3"]["hit"] for r in rows)
            print(f"  [{i}/{len(cases)}] P2={p2h}/{i} P3={p3h}/{i}", flush=True)
    fout.close()

    # paired analysis on cases where both modes returned ok
    ok = [r for r in rows if not str(r["p2"]["status"]).startswith("err")
          and not str(r["p3"]["status"]).startswith("err")]
    n = len(ok)
    p2h = sum(r["p2"]["hit"] for r in ok); p3h = sum(r["p3"]["hit"] for r in ok)
    # McNemar discordant pairs
    b = sum(1 for r in ok if r["p3"]["hit"] and not r["p2"]["hit"])   # P3 win
    c_ = sum(1 for r in ok if r["p2"]["hit"] and not r["p3"]["hit"])  # P2 win
    # 2-prop z (one-sided P3>P2)
    import math
    p1, p2 = p3h / n, p2h / n
    pp = (p3h + p2h) / (2 * n)
    se = math.sqrt(2 * pp * (1 - pp) / n) if pp not in (0, 1) else 0
    z = (p1 - p2) / se if se > 0 else float("inf")
    # McNemar chi2 (continuity-corrected)
    mcnemar = ((abs(b - c_) - 1) ** 2) / (b + c_) if (b + c_) > 0 else 0

    md = []
    md.append("# H2 full-N — variant-channel lift (paired, PP-Store)\n")
    md.append(f"llm_control, Gemini Flash, N={n} paired variant cases (both modes ok).\n")
    md.append("| Mode | R@1 | hits |")
    md.append("|---|---|---|")
    md.append(f"| P2 (HPO only) | {p2/1:.3f} | {p2h}/{n} |")
    md.append(f"| P3 (HPO + variants) | {p1:.3f} | {p3h}/{n} |")
    md.append(f"| **Lift** | **{p1-p2:+.3f}** | — |\n")
    md.append(f"- Paired McNemar discordant: P3-win={b}, P2-win={c_}; χ²(cc)={mcnemar:.2f}")
    md.append(f"- 2-prop z (one-sided P3>P2): z={z:.2f}")
    md.append(f"- Pre-registered H2: lift ≥ +10 pp → {'SUPPORTED' if (p1-p2)>=0.10 else 'not met'}")
    MD.write_text("\n".join(md))
    print("\n".join(md))
    print(f"\n[H2] wrote {OUT} + {MD}")
    print(f"H2_RESULT z={z:.3f} p3h={p3h} p2h={p2h} n={n} b={b} c={c_}")


if __name__ == "__main__":
    main()
