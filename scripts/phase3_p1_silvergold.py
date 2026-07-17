"""Phase 3.1 — P1 (HPO extraction) on Opus silver gold(replaces leaky tautology).

Run llm_control + RDMA + DeepRare on 50 PMC OA cases. Input = `case_excerpt`
(real free text). Gold = Opus 4.7 extracted HPO phrases. Metric = phrase-level
Jaccard against silver gold(via `hpo_phrase_to_id` normalization for both
sides).

This replaces Phase 1's `p1_extraction_pilot.py` which used synth vignette
from gold HPO labels — leaky tautology(phrase_f1 ≈ 1.0 trivially).

Output:
  data/round2/phase3/p1_silvergold_results.jsonl
  data/round2/phase3/P1_SILVERGOLD_REPORT.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def load_env(env_path: Path = Path(".env")) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def load_silver_gold(path: Path, limit: int = 50) -> list:
    """Read silver_gold_opus.jsonl(99 entries),return first `limit` valid ones."""
    out = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("_error"): continue
            if not rec.get("silver_gold", {}).get("hpo_phenotypes"):
                continue
            out.append(rec)
            if len(out) >= limit: break
    return out


def make_canonical_case_from_pmc(silver_rec: dict):
    """Project silver_gold record to a CanonicalCase-shaped object for adapter."""
    from harness.canonical_case import CanonicalCase, Demographics, GoldLabel, HpoTerm

    # Silver gold has hpo_phenotypes: [{phrase, hpo_id_guess}]
    sg = silver_rec["silver_gold"]
    gold_hpo = []
    for ent in sg.get("hpo_phenotypes", []):
        hp_id = ent.get("hpo_id_guess") or "HP:0000000"
        if not isinstance(hp_id, str) or not hp_id.startswith("HP:"):
            hp_id = "HP:0000000"
        gold_hpo.append(HpoTerm(id=hp_id, label=ent.get("phrase")))

    return CanonicalCase(
        case_id=f"pmc_{silver_rec['pmc_id']}",
        source_dataset="pmc_oa_holdout",
        source_split="silver_gold_opus",
        language="en",
        demographics=Demographics(),
        free_text_vignette=silver_rec.get("case_excerpt"),
        synthetic_vignette=None,
        gold_hpo_terms=gold_hpo,
        variants=[],
        family=None,
        gold_label=GoldLabel(
            orphanet_id=silver_rec.get("orpha_id"),
            disease_name=silver_rec.get("matched_orpha_name") or sg.get("final_diagnosis"),
        ),
        metadata={"pmc_id": silver_rec["pmc_id"]},
    )


def get_extractor(name: str, backbone_id: str):
    from harness.agents import LLMControlAdapter, RDMAAdapter, DeepRareAdapter
    if name == "llm_control":
        return LLMControlAdapter(backbone_id=backbone_id)
    if name == "rdma":
        return RDMAAdapter(backbone_id=backbone_id)
    if name == "deeprare":
        return DeepRareAdapter(backbone_id=backbone_id)
    raise ValueError(name)


def normalize_phrases_to_ids(phrases: list[str]) -> set[str]:
    """Phrase list → set of HP IDs via hpo_phrase_to_id; drop unresolved."""
    from harness.metrics.hpo_phrase_to_id import phrase_to_hp_id
    out = set()
    for p in phrases:
        if not p: continue
        hp = phrase_to_hp_id(p)
        if hp: out.add(hp)
    return out


def jaccard(a: set, b: set) -> float:
    if not a and not b: return 1.0
    if not a or not b: return 0.0
    return len(a & b) / len(a | b)


def run(agents, backbone_id, n, out_path, report_path):
    load_env()
    from harness.logging import JsonlPredictionLogger

    silver = load_silver_gold(
        Path("data/round2/phase1/silver_gold_opus.jsonl"), limit=n)
    print(f"[p3] {len(silver)} silver-gold cases loaded")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    logger = JsonlPredictionLogger(out_path)

    rows = []
    for agent_name in agents:
        print(f"\n[p3] === Agent {agent_name} ===")
        try:
            adapter = get_extractor(agent_name, backbone_id)
        except Exception as e:
            print(f"  ❌ {e}")
            continue
        for i, rec in enumerate(silver, 1):
            case = make_canonical_case_from_pmc(rec)
            gold_phrases = [t.label for t in case.gold_hpo_terms if t.label]
            gold_ids = normalize_phrases_to_ids(gold_phrases)
            t0 = time.time()
            try:
                phrases_extracted = adapter.extract_phenotypes(case)
                pred_phrases = [t.label or t.id for t in phrases_extracted if t.label or t.id]
                pred_ids = normalize_phrases_to_ids(pred_phrases)
                j = jaccard(pred_ids, gold_ids)
                prec = (len(pred_ids & gold_ids) / len(pred_ids)) if pred_ids else 0.0
                rec_r = (len(pred_ids & gold_ids) / len(gold_ids)) if gold_ids else 0.0
                f1 = (2 * prec * rec_r / (prec + rec_r)) if (prec + rec_r) > 0 else 0.0
                status = "ok"
                err = None
                latency_ms = int((time.time() - t0) * 1000)
            except NotImplementedError:
                pred_phrases = []
                pred_ids = set()
                j = prec = rec_r = f1 = 0.0
                status = "not_implemented"
                err = "extract_phenotypes not implemented"
                latency_ms = 0
            except Exception as e:
                pred_phrases = []
                pred_ids = set()
                j = prec = rec_r = f1 = 0.0
                status = "agent_error"
                err = str(e)[:300]
                latency_ms = int((time.time() - t0) * 1000)

            row = {
                "agent": agent_name,
                "pmc_id": rec["pmc_id"],
                "status": status,
                "error": err,
                "latency_ms": latency_ms,
                "n_gold_phrases": len(gold_phrases),
                "n_gold_resolved": len(gold_ids),
                "n_pred_phrases": len(pred_phrases),
                "n_pred_resolved": len(pred_ids),
                "jaccard": j,
                "precision": prec,
                "recall": rec_r,
                "f1": f1,
            }
            rows.append(row)
            print(f"  [{i}/{len(silver)}] {rec['pmc_id'][:30]:30s} status={status:15s} "
                  f"pred={len(pred_ids):2d} gold={len(gold_ids):2d} f1={f1:.2f}")

    # Aggregate
    by_agent = {}
    for r in rows:
        by_agent.setdefault(r["agent"], []).append(r)

    md = ["# Phase 3.1 — P1 Extraction on Opus Silver Gold(non-leaky)\n"]
    md.append(f"\nN={n} PMC OA cases | Backbone={backbone_id}\n")
    md.append("\n## Per-agent micro-averaged P/R/F1(phrase→HP-ID normalized)\n")
    md.append("| Agent | OK | Mean Prec | Mean Recall | Mean F1 | Mean Jaccard | Mean latency |")
    md.append("|---|---|---|---|---|---|---|")
    for agent, rs in sorted(by_agent.items()):
        ok = [r for r in rs if r["status"] == "ok"]
        n_ok = len(ok)
        if not ok:
            md.append(f"| `{agent}` | 0/{len(rs)} | — | — | — | — | — |")
            continue
        mp = sum(r["precision"] for r in ok) / n_ok
        mr = sum(r["recall"] for r in ok) / n_ok
        mf = sum(r["f1"] for r in ok) / n_ok
        mj = sum(r["jaccard"] for r in ok) / n_ok
        ml = sum(r["latency_ms"] for r in ok) / n_ok / 1000
        md.append(f"| `{agent}` | {n_ok}/{len(rs)} | {mp:.3f} | {mr:.3f} | {mf:.3f} | {mj:.3f} | {ml:.1f}s |")

    md.append("\n## What this replaces\n")
    md.append("- Phase 1 `p1_extraction_pilot.py` used `synthesize_vignette_from_hpo(case)` "
              "for Phenopacket-Store cases — phrase_f1≈1.0 was leaky tautology(LLM read its "
              "own synthesized labels).")
    md.append("- This pilot uses **real PMC OA case_excerpt as input** + **Opus 4.7 silver gold** "
              "as reference. Disagreement is real(Opus vs Gemini Jaccard 0.41,§Round 2 worklog).")

    report_path.write_text("\n".join(md))
    print(f"\n[p3] Wrote {out_path}")
    print(f"[p3] Wrote {report_path}")

    # Persist raw rows
    with (out_path.parent / "p1_silvergold_rows.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--agents", default="llm_control,rdma,deeprare")
    p.add_argument("--backbone", default="openrouter/google/gemini-3-flash-preview-20251217")
    p.add_argument("--n", type=int, default=50)
    p.add_argument("--out", default="data/round2/phase3/p1_silvergold.jsonl")
    p.add_argument("--report", default="data/round2/phase3/P1_SILVERGOLD_REPORT.md")
    args = p.parse_args()

    agents = [a.strip() for a in args.agents.split(",")]
    run(agents, args.backbone, args.n, Path(args.out), Path(args.report))
