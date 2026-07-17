"""Mini Round 2 Phase 0 — 6 low-risk agents × 50 cases × Gemini Flash × Pillar 2.

Goal: validate 8/8-adapter machinery on a real sample, compare against the
existing sanity-check LLM control baseline (Gemini Flash R@1=0.26 on same sample).

Sample: stratified 25 Phenopacket-Store + 25 RareArena RDS, seed=42
(identical to scripts/sanity_check_pilot.py for direct A/B with llm_control).

Agents:
- mdagents, medagents, agentclinic, maidxo, lirical, vc_rdagent
- skipped: deeprare (~130s/case — Phase 0 separate), rdma (P1 specialist)

Eval: Pillar 2 only, gold_hpo mode (PP-Store has gold HPO directly; RareArena
uses free_text_vignette wrapped in a "given these HPO terms ..." prompt).

Output: data/round2/phase0/predictions.jsonl + REPORT.md
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import traceback
from pathlib import Path
from typing import Optional


def load_env(env_path: Path = Path(".env")) -> None:
    """Load OPENROUTER_API_KEY etc. into os.environ from .env."""
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def build_sample(seed: int = 42, n_per_layer: int = 25) -> list:
    """Stratified 25 PP-Store + 25 RareArena RDS, deterministic by seed."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from harness.ingest import ingest_phenopacket_store, ingest_rarearena

    rng = random.Random(seed)
    pp_all = list(ingest_phenopacket_store("data/phenopacket_store/notebooks"))
    rng.shuffle(pp_all)
    pp = pp_all[:n_per_layer]

    ra_all = list(ingest_rarearena(
        "data/rarearena/benchmark_data/RDS_benchmark.jsonl", "RDS"))
    rng.shuffle(ra_all)
    ra = ra_all[:n_per_layer]

    return pp + ra


def get_adapter(name: str, backbone_id: str):
    """Lazy import each adapter to avoid loading all on import."""
    from harness.agents import (
        AgentClinicAdapter, DeepRareAdapter, LIRICALAdapter, LLMControlAdapter,
        MDAgentsAdapter, MaiDxOAdapter, MedAgentsAdapter, RDMAAdapter,
        VCRDAgentAdapter,
    )
    if name == "mdagents":
        return MDAgentsAdapter(backbone_id=backbone_id)
    if name == "medagents":
        return MedAgentsAdapter(backbone_id=backbone_id)
    if name == "agentclinic":
        return AgentClinicAdapter(backbone_id=backbone_id)
    if name == "maidxo":
        # FIX D1 (2026-05-15): use `max_iterations` (the correct key) and
        # default to 3 so the panel actually iterates (1 round = degenerate).
        return MaiDxOAdapter(
            backbone_id=backbone_id,
            agent_extra={"mode": "no_budget", "max_iterations": 3},
        )
    if name == "lirical":
        return LIRICALAdapter(backbone_id="lirical-2.4.0")  # placeholder backbone_id
    if name == "vc_rdagent":
        return VCRDAgentAdapter(backbone_id="vc_rdagent-offline-v1")
    if name == "deeprare":
        # FIX B1 (2026-05-15): register deeprare in pilot script (was missing).
        # DeepRare adapter requires DEEPRARE_NO_WEB=1 + DEEPRARE_LOCAL_EMBEDDING=1
        # in env (per round2_worklog "Bug Fix 2026-05-15" section of deeprare).
        return DeepRareAdapter(backbone_id=backbone_id)
    if name == "llm_control":
        # 2026-05-19 FIX: llm_control was missing from registry — caused 3
        # parallel v4 reruns to fail immediately with "unknown adapter".
        return LLMControlAdapter(backbone_id=backbone_id)
    if name == "rdma":
        # RDMA is a Pillar 1 specialist — predict() will return status="skipped"
        # for P2, but include here so phase 2 grid can run end-to-end without
        # adapter-not-found errors.
        return RDMAAdapter(backbone_id=backbone_id)
    raise ValueError(f"unknown adapter: {name}")


def already_done(log_path: Path) -> set:
    """Read existing log to support resume — skip (agent, case_id) pairs done."""
    if not log_path.exists():
        return set()
    seen = set()
    with log_path.open() as f:
        for line in f:
            try:
                r = json.loads(line)
                seen.add((r["agent_id"], r["case_id"]))
            except (json.JSONDecodeError, KeyError):
                continue
    return seen


def run(
    agents: list[str],
    backbone_id: str,
    out_path: Path,
    seed: int = 42,
    n_per_layer: int = 25,
    resume: bool = True,
) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from harness.logging import JsonlPredictionLogger

    print(f"[mini-r2] Building sample (seed={seed}, n_per_layer={n_per_layer})...",
          flush=True)
    cases = build_sample(seed=seed, n_per_layer=n_per_layer)
    print(f"  total cases: {len(cases)}", flush=True)

    done = already_done(out_path) if resume else set()
    if done:
        print(f"[mini-r2] Resume: {len(done)} (agent, case) pairs already in log",
              flush=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    logger = JsonlPredictionLogger(out_path)

    run_id = f"mini_round2_phase0_{int(time.time())}"
    total = len(agents) * len(cases)
    done_count = len(done)

    for agent_name in agents:
        print(f"\n[mini-r2] === Agent {agent_name} ===", flush=True)
        try:
            adapter = get_adapter(agent_name, backbone_id)
        except Exception as e:
            print(f"  ❌ Failed to construct adapter: {e}", flush=True)
            continue

        for i, case in enumerate(cases, 1):
            if (agent_name, case.case_id) in done:
                continue
            t0 = time.time()
            # FIX D3 (2026-05-15): for LIRICAL / VC-RDAgent on RareArena cases
            # (no gold_hpo, only free_text_vignette), switch to end_to_end mode
            # so the adapter does upstream LLM HPO extraction. PP-Store cases
            # keep gold_hpo (their original verified behaviour).
            per_case_eval_mode = "gold_hpo"
            if agent_name in ("lirical", "vc_rdagent"):
                if not case.gold_hpo_terms and (
                    case.free_text_vignette or case.synthetic_vignette
                ):
                    per_case_eval_mode = "end_to_end"
            try:
                log = adapter.predict(
                    case,
                    pillar="P2_phenotype_ddx",
                    eval_mode=per_case_eval_mode,
                    run_id=run_id,
                )
                logger.write(log)
                done_count += 1
                top5 = log.ranked_predictions[:5]
                print(
                    f"  [{done_count}/{total}] {agent_name} / {case.case_id[:25]:25s} "
                    f"→ {log.status:5s} {int(time.time()-t0):3d}s  top1={top5[0] if top5 else 'NIL'}",
                    flush=True,
                )
            except Exception as e:
                print(f"  [{done_count}/{total}] {agent_name} / {case.case_id} "
                      f"❌ {type(e).__name__}: {e}", flush=True)
                traceback.print_exc()

    logger.close()
    print(f"\n[mini-r2] DONE. Wrote {out_path}", flush=True)


def aggregate_and_report(
    log_path: Path,
    report_path: Path,
) -> None:
    """Read predictions, compute per-agent metrics, write REPORT.md."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from harness.logging import read_logs
    from harness.metrics import (
        median_rank, mrr, recall_at_k_table,
    )
    from harness.metrics.cross_map import gold_hit_with_crossmap

    logs = read_logs(log_path)
    if not logs:
        print("No logs to aggregate.", flush=True)
        return

    # Get case_id → gold_label map via re-ingesting (cheap, cached)
    cases = build_sample(seed=42, n_per_layer=25)
    case_gold = {c.case_id: c.gold_label for c in cases}

    by_agent: dict[str, list] = {}
    for log in logs:
        by_agent.setdefault(log.agent_id, []).append(log)

    rows: list[dict] = []
    for agent_id, agent_logs in sorted(by_agent.items()):
        # filter to ok status with gold
        good = [L for L in agent_logs if L.status == "ok" and L.case_id in case_gold]
        n_ok = len(good)
        n_total = len(agent_logs)

        # Cross-map hit-aware rank for each log
        preds = [L.ranked_predictions for L in good]
        golds = [case_gold[L.case_id] for L in good]

        # Override is_hit with cross-map version: monkey-patch ranking
        def cm_rank_of_hit(preds_list, gold):
            for i, p in enumerate(preds_list, 1):
                if gold_hit_with_crossmap(p, gold):
                    return i
            return None

        ranks = [cm_rank_of_hit(p[:10], g) for p, g in zip(preds, golds)]
        r_at_k = {f"R@{k}": sum(1 for r in ranks if r is not None and r <= k) / len(ranks)
                  if ranks else 0.0
                  for k in (1, 3, 5, 10)}
        mr_val = (sum(r for r in ranks if r is not None) / sum(1 for r in ranks if r)
                  if any(r is not None for r in ranks) else float("inf"))
        mrr_val = sum(1.0 / r for r in ranks if r is not None) / len(ranks) if ranks else 0.0

        total_cost = sum(L.cost.cost_usd for L in good)
        total_in = sum(L.cost.prompt_tokens for L in good)
        total_out = sum(L.cost.completion_tokens for L in good)
        mean_lat_s = sum(L.total_latency_ms for L in good) / len(good) / 1000 if good else 0

        rows.append({
            "agent": agent_id,
            "n_ok": n_ok,
            "n_total": n_total,
            **r_at_k,
            "MRR": mrr_val,
            "MeanRank_hit": mr_val,
            "cost_usd": total_cost,
            "tokens_in": total_in,
            "tokens_out": total_out,
            "mean_latency_s": mean_lat_s,
        })

    # Write REPORT.md
    md = ["# Mini Round 2 Phase 0 — Report\n"]
    md.append(f"\nLogs read: {len(logs)} predictions, {len(case_gold)} ground-truth cases.\n")
    md.append("\n## Per-agent results (Pillar 2, gold_hpo, 50 case sample)\n")
    md.append("| Agent | OK | R@1 | R@3 | R@5 | R@10 | MRR | Cost($) | Mean Lat |")
    md.append("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        md.append(
            f"| `{r['agent']}` | {r['n_ok']}/{r['n_total']} | "
            f"{r['R@1']:.2f} | {r['R@3']:.2f} | {r['R@5']:.2f} | {r['R@10']:.2f} | "
            f"{r['MRR']:.3f} | {r['cost_usd']:.3f} | {r['mean_latency_s']:.1f}s |"
        )

    md.append("\n## Baseline comparison\n")
    md.append("Sanity-check (2026-05-14) ran `llm_control` (Gemini Flash, no scaffolding) "
              "on the **same 50-case sample, seed=42**:")
    md.append("- R@1=0.26, R@3=0.32, R@5=0.40, MRR=0.305, cost=$0.05, mean lat 3.5s\n")
    md.append("**Scaffolded agents must beat 0.26 R@1 to justify their overhead.**\n")

    report_path.write_text("\n".join(md))
    print(f"Report written: {report_path}", flush=True)
    print("\n".join(md))


if __name__ == "__main__":
    load_env()

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--agents",
        default="mdagents,medagents,agentclinic,maidxo,lirical,vc_rdagent",
        help="Comma-separated agent names (default: 6 low-risk)",
    )
    parser.add_argument(
        "--backbone",
        default="openrouter/google/gemini-3-flash-preview",
    )
    parser.add_argument(
        "--out",
        default="data/round2/phase0/predictions.jsonl",
    )
    parser.add_argument(
        "--report",
        default="data/round2/phase0/REPORT.md",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-per-layer", type=int, default=25)
    parser.add_argument("--report-only", action="store_true",
                        help="Skip running, just aggregate existing log to REPORT.md")
    args = parser.parse_args()

    out_path = Path(args.out)
    report_path = Path(args.report)
    agents = [a.strip() for a in args.agents.split(",") if a.strip()]

    if not args.report_only:
        run(
            agents=agents,
            backbone_id=args.backbone,
            out_path=out_path,
            seed=args.seed,
            n_per_layer=args.n_per_layer,
        )

    aggregate_and_report(out_path, report_path)
