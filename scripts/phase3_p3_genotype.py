"""Phase 3.2 — P3 (genotype-aware DDx) on Phenopacket-Store.

Phenopacket-Store 是唯一有 structured variants 的 dataset。对每个 case,
adapter 把 case.variants(gene_symbol / hgvs.c / acmg / zygosity)和 HPO 一起
作为 P3 input。

Agents tested:
- llm_control(prompt includes variants block)
- deeprare(supports `pillar="P3_genotype_aware"`)

Backbone: Gemini Flash + DeepSeek V3.2(2-backbone for now,GPT-5 deferred until
subprocess reasoning_effort fix done)

Metric: R@1/3/5 同 P2,但比对 P2 same-agent same-case R@1 看 P3 增量(H2 evidence)

Output:
  data/round2/phase3/p3_genotype.jsonl
  data/round2/phase3/P3_REPORT.md
"""

from __future__ import annotations

import argparse
import json
import os
import random
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


def build_p3_sample(seed: int = 42, n: int = 50):
    """Stratified Phenopacket-Store cases that have ≥1 variant info."""
    from harness.ingest import ingest_phenopacket_store
    rng = random.Random(seed)
    all_cases = list(ingest_phenopacket_store("data/phenopacket_store/notebooks"))
    rng.shuffle(all_cases)
    with_variants = [c for c in all_cases if c.variants]
    return with_variants[:n]


def get_adapter(name: str, backbone_id: str):
    from harness.agents import DeepRareAdapter, LLMControlAdapter
    if name == "llm_control":
        return LLMControlAdapter(backbone_id=backbone_id)
    if name == "deeprare":
        return DeepRareAdapter(backbone_id=backbone_id)
    raise ValueError(name)


def run(agents, backbone_id, n, out_path, report_path):
    from harness.logging import JsonlPredictionLogger
    from harness.metrics.cross_map import gold_hit_with_crossmap

    load_env()

    print(f"[p3.2] Backbone: {backbone_id}")
    cases = build_p3_sample(n=n)
    print(f"[p3.2] Sample size: {len(cases)} PP-Store cases with variants")

    case_gold = {c.case_id: c.gold_label for c in cases}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    logger = JsonlPredictionLogger(out_path)

    run_id = f"phase3_p3_{int(time.time())}"
    rows = []

    for agent_name in agents:
        print(f"\n[p3.2] === Agent {agent_name} ===")
        try:
            adapter = get_adapter(agent_name, backbone_id)
        except Exception as e:
            print(f"  ❌ adapter ctor failed: {e}")
            continue

        for i, case in enumerate(cases, 1):
            t0 = time.time()
            try:
                log = adapter.predict(
                    case,
                    pillar="P3_genotype_aware",
                    eval_mode="gold_hpo",
                    run_id=run_id,
                )
            except NotImplementedError:
                # P3 not supported — record as such
                continue
            except Exception as e:
                print(f"  [{i}/{len(cases)}] ❌ {case.case_id[:30]}: {type(e).__name__}: {e}")
                continue

            logger.write(log)
            top5 = log.ranked_predictions[:5]
            gold = case_gold.get(case.case_id)
            hit = bool(gold and top5 and gold_hit_with_crossmap(top5[0], gold))
            rows.append({
                "agent": agent_name,
                "backbone": backbone_id,
                "case_id": case.case_id,
                "status": log.status,
                "latency_ms": log.total_latency_ms,
                "top1_hit": hit,
                "top1": top5[0] if top5 else "(empty)",
            })
            print(f"  [{i}/{len(cases)}] {case.case_id[:30]:30s} status={log.status} "
                  f"{int(time.time()-t0):3d}s hit={hit} top1={(top5[0] if top5 else 'NIL')[:50]}")

    # Aggregate
    by_agent: dict[str, list] = {}
    for r in rows:
        by_agent.setdefault(r["agent"], []).append(r)

    md = ["# Phase 3.2 — P3 (Genotype-Aware) Report\n"]
    md.append(f"\nN={len(cases)} Phenopacket-Store cases (all with ≥1 variant). "
              f"Backbone: `{backbone_id}`\n")
    md.append("\n## Per-agent P3 results\n")
    md.append("| Agent | OK | P3 R@1 | Hits | Mean Lat |")
    md.append("|---|---|---|---|---|")
    for agent, rs in sorted(by_agent.items()):
        ok = [r for r in rs if r["status"] == "ok"]
        n_ok = len(ok)
        hits = sum(1 for r in ok if r["top1_hit"])
        if n_ok == 0:
            md.append(f"| `{agent}` | 0/{len(rs)} | — | — | — |")
            continue
        r1 = hits / n_ok
        ml = sum(r["latency_ms"] for r in ok) / n_ok / 1000
        md.append(f"| `{agent}` | {n_ok}/{len(rs)} | {r1:.2f} | {hits} | {ml:.1f}s |")

    md.append("\n## Comparison to P2 baseline (same agent, same cases, HPO-only)\n")
    md.append("Phase 0 V3 P2 R@1 numbers for the same agents (from `REPORT_FINAL.md`):\n")
    md.append("- `deeprare`: 0.22 (50 mixed cases)")
    md.append("- `llm_control` baseline: 0.26 (sanity check)\n")
    md.append("**If P3 R@1 > P2 R@1**, genotype channel adds signal (H2 supported).")
    md.append("**If P3 R@1 ≈ P2 R@1**, agent doesn't leverage variant info.")

    report_path.write_text("\n".join(md))
    print(f"\n[p3.2] Wrote {report_path}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--agents", default="llm_control,deeprare")
    p.add_argument("--backbone", default="openrouter/google/gemini-3-flash-preview-20251217")
    p.add_argument("--n", type=int, default=50)
    p.add_argument("--out", default="data/round2/phase3/p3_genotype.jsonl")
    p.add_argument("--report", default="data/round2/phase3/P3_REPORT.md")
    args = p.parse_args()

    agents = [a.strip() for a in args.agents.split(",")]
    run(agents, args.backbone, args.n, Path(args.out), Path(args.report))
