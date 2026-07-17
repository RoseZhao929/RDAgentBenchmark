"""A4 cross-map audit — verify that adapter's NL output gets correctly
fuzzy-matched to ORPHA / OMIM IDs by `harness.pmc_oa.orphanet.map_diagnosis`.

Concern (from Retrospective Checkpoint #1):
Many adapters output ranked diagnoses as natural-language strings (e.g.
"Metachondromatosis"), not as ORPHA: / OMIM: prefix IDs. The `_adapter_utils`
helper `map_names_to_ids` runs each NL string through `map_diagnosis` and
keeps the top fuzzy hit if score ≥ some threshold. If that threshold misses
common synonyms, agents would be artificially penalised on R@1.

This audit:
1. Loads predictions.jsonl + predictions_v2.jsonl from Phase 0.
2. For each (agent, case), inspects ranked_predictions.
3. Categorises each prediction:
   - "id"        — already starts with OMIM:/ORPHA:/CCRD:, no fuzzy needed
   - "name_exact" — runs map_diagnosis, gets exact_name hit
   - "name_fuzzy_ok"  — fuzzy ≥ 90 (current threshold), accepted
   - "name_fuzzy_borderline" — score 70-89 (rejected by current threshold,
                                 but maybe real)
   - "name_nohit" — no Orphanet match at all
4. Reports per-agent breakdown + 20 random "borderline" samples for manual
   inspection.

Use:
    python3 scripts/audit_crossmap.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.pmc_oa.orphanet import map_diagnosis, parse_orphadata


def is_prefix_id(s: str) -> bool:
    return any(s.startswith(p) for p in ("OMIM:", "ORPHA:", "CCRD:", "HP:"))


def categorise(pred: str, tables: dict) -> dict:
    pred = (pred or "").strip()
    if not pred:
        return {"category": "empty", "score": 0.0}
    if is_prefix_id(pred):
        return {"category": "id", "score": 100.0, "matched": pred}

    res = map_diagnosis(pred, tables, fuzzy_threshold=90)
    mt = res["match_type"]
    score = res["score"]

    if mt == "exact_name":
        return {"category": "name_exact", "score": score,
                "matched": res["orpha_id"], "matched_name": res["matched_name"]}
    if mt == "fuzzy" and score >= 90:
        return {"category": "name_fuzzy_ok", "score": score,
                "matched": res["orpha_id"], "matched_name": res["matched_name"]}
    if res.get("top_candidates") and res["top_candidates"][0]["score"] >= 70:
        # below current threshold but still suspicious
        top = res["top_candidates"][0]
        return {"category": "name_fuzzy_borderline", "score": top["score"],
                "matched": top["orpha_id"], "matched_name": top["name"]}
    return {"category": "name_nohit", "score": score}


def audit_files(paths: list[Path]) -> dict:
    print("[audit] Parsing Orphadata (53MB XML, cached)...", flush=True)
    tables = parse_orphadata()
    print(f"  ready: {len(tables['name_to_orpha'])} aliases", flush=True)

    by_agent: dict[str, Counter] = {}
    borderline_samples: list[dict] = []
    nohit_samples: list[dict] = []

    n_total_predictions = 0
    n_total_preds_per_case = []

    for path in paths:
        if not path.exists():
            print(f"  [audit] skip missing {path}")
            continue
        print(f"[audit] reading {path.name}...", flush=True)
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                agent = rec.get("agent_id", "?")
                preds = rec.get("ranked_predictions", []) or []
                n_total_preds_per_case.append(len(preds))
                # Only audit top-5 (the rank window we report metrics on)
                for rank, pred in enumerate(preds[:5], 1):
                    n_total_predictions += 1
                    cat = categorise(pred, tables)
                    by_agent.setdefault(agent, Counter())[cat["category"]] += 1

                    if cat["category"] == "name_fuzzy_borderline":
                        borderline_samples.append({
                            "agent": agent,
                            "case_id": rec.get("case_id"),
                            "rank": rank,
                            "pred": pred,
                            "matched": cat.get("matched"),
                            "matched_name": cat.get("matched_name"),
                            "score": cat["score"],
                        })
                    elif cat["category"] == "name_nohit":
                        nohit_samples.append({
                            "agent": agent,
                            "case_id": rec.get("case_id"),
                            "rank": rank,
                            "pred": pred,
                        })

    return {
        "n_total_predictions_audited": n_total_predictions,
        "mean_preds_per_case": (sum(n_total_preds_per_case) / len(n_total_preds_per_case)
                                if n_total_preds_per_case else 0),
        "by_agent": {a: dict(c) for a, c in by_agent.items()},
        "borderline_samples": borderline_samples,
        "nohit_samples": nohit_samples,
    }


if __name__ == "__main__":
    paths = [
        Path("data/round2/phase0/predictions.jsonl"),
        Path("data/round2/phase0/predictions_v2.jsonl"),
    ]
    result = audit_files(paths)

    out_path = Path("data/round2/phase0/CROSSMAP_AUDIT.md")
    md = ["# A4 Cross-Map Audit — Phase 0 Predictions\n"]
    md.append(f"\nAudited {result['n_total_predictions_audited']:,} predictions "
              f"(top-5 of each case × all agents). "
              f"Mean predictions/case: {result['mean_preds_per_case']:.1f}\n")

    md.append("\n## Per-agent prediction category breakdown\n")
    md.append("| Agent | id | name_exact | name_fuzzy_ok | borderline | nohit | empty |")
    md.append("|---|---|---|---|---|---|---|")
    cats = ["id", "name_exact", "name_fuzzy_ok",
            "name_fuzzy_borderline", "name_nohit", "empty"]
    for agent, counts in sorted(result["by_agent"].items()):
        row = [f"`{agent}`"] + [str(counts.get(c, 0)) for c in cats]
        md.append("| " + " | ".join(row) + " |")

    md.append(f"\n## Borderline samples (n={len(result['borderline_samples'])})\n")
    md.append("Predictions where fuzzy score is 70-89 — current threshold 90 rejects, "
              "but the match may be a legitimate synonym we're missing.\n")
    md.append("| Agent | Case | Rank | Predicted | Matched Orpha | Name | Score |")
    md.append("|---|---|---|---|---|---|---|")
    import random
    rng = random.Random(42)
    sample = rng.sample(result["borderline_samples"],
                        min(20, len(result["borderline_samples"])))
    for s in sample:
        md.append(f"| `{s['agent']}` | {s['case_id'][:30]} | {s['rank']} | "
                  f"{s['pred'][:60]} | {s['matched']} | {(s['matched_name'] or '')[:50]} | "
                  f"{s['score']:.1f} |")

    md.append(f"\n## No-hit samples (n={len(result['nohit_samples'])}, showing 20)\n")
    md.append("Predictions with no Orphanet match at all (even fuzzy <70). Either:\n")
    md.append("- The agent output a non-disease string (e.g. 'present in', 'Unable to establish ...')\n")
    md.append("- The disease is not in Orphanet (true rare miss)\n")
    md.append("- The output is a too-truncated phrase\n")
    md.append("\n| Agent | Case | Rank | Predicted |")
    md.append("|---|---|---|---|")
    nohit_sample = rng.sample(result["nohit_samples"],
                              min(20, len(result["nohit_samples"])))
    for s in nohit_sample:
        md.append(f"| `{s['agent']}` | {s['case_id'][:30]} | {s['rank']} | "
                  f"{s['pred'][:80]} |")

    md.append("\n## Verdict\n")
    md.append("(Filled in after reviewing borderline + nohit samples manually.)\n")

    out_path.write_text("\n".join(md))
    print(f"\nWrote audit to: {out_path}")
    print(f"\nTotal predictions audited: {result['n_total_predictions_audited']:,}")
    print(f"Borderline (70-89 score): {len(result['borderline_samples'])}")
    print(f"No-hit: {len(result['nohit_samples'])}")
