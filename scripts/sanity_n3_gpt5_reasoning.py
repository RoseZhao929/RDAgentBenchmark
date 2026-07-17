"""N=3 sanity check for the 2026-05-19 GPT-5 reasoning_effort propagation fix.

Background: per `round2_worklog.md` Retrospective Checkpoint #4, four subprocess
adapters (medagents, agentclinic, maidxo, deeprare) failed 46-50/50 on GPT-5
in Phase 2 because their vendor venv LLM clients (openai 0.27/0.28/1.x or
LiteLLM via swarms) did NOT propagate `reasoning_effort=minimal`. GPT-5
default reasoning consumes the entire `max_tokens` budget on hidden CoT,
leaving `content=null` or hitting our 600s timeout.

This script runs each of the 5 LLM-based subprocess adapters on 3 cases (the
first 3 from the same stratified Phase 0 sample as `mini_round2_pilot.py`,
seed=42, n_per_layer=25 → 50 cases). For each agent we report:

  - status (ok / parser_error / timeout / agent_error)
  - latency (s)
  - cost (prompt + completion tokens)
  - top-1 prediction

Pass criteria per agent:
  - 3/3 status=ok
  - token cost > 0
  - 3 top-1 NOT all identical (so the fix didn't introduce a constant-output bug)
  - none time out

Usage:
    OPENROUTER_API_KEY=... python3 scripts/sanity_n3_gpt5_reasoning.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def load_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def _run_one_agent(name: str, adapter, cases) -> dict:
    """Run an adapter against the 3 cases; return per-case results dict."""
    print(f"\n=== {name} ===", flush=True)
    rows = []
    for i, case in enumerate(cases, 1):
        t0 = time.time()
        try:
            log = adapter.predict(
                case,
                pillar="P2_phenotype_ddx",
                eval_mode="gold_hpo",
                run_id=f"sanity_n3_gpt5_{name}_{int(t0)}",
            )
            status = log.status
            top1 = log.ranked_predictions[0] if log.ranked_predictions else "NIL"
            pt = log.cost.prompt_tokens
            ct = log.cost.completion_tokens
            err = log.error_message or ""
        except Exception as e:  # noqa: BLE001
            status = "exception"
            top1 = "NIL"
            pt = ct = 0
            err = f"{type(e).__name__}: {e}"
        elapsed = int(time.time() - t0)
        rows.append(
            {
                "case": case.case_id,
                "status": status,
                "top1": top1,
                "prompt_tokens": pt,
                "completion_tokens": ct,
                "latency_s": elapsed,
                "error": err[:200],
            }
        )
        print(
            f"  [{i}/3] {case.case_id[:35]:35s}  "
            f"status={status:13s}  {elapsed:4d}s  "
            f"tok={pt:>6d}+{ct:>6d}  top1={top1!r}",
            flush=True,
        )
        if err:
            print(f"      err: {err[:160]}", flush=True)

    # Verdict per agent
    statuses = [r["status"] for r in rows]
    tops = [r["top1"] for r in rows]
    n_ok = sum(1 for s in statuses if s == "ok")
    n_timeout = sum(1 for s in statuses if s == "timeout")
    total_tokens = sum(r["prompt_tokens"] + r["completion_tokens"] for r in rows)
    unique_tops = len({t.lower() for t in tops if t != "NIL"})
    pass_ok = n_ok == 3
    pass_tok = total_tokens > 0
    pass_unique = unique_tops >= 2
    pass_timeout = n_timeout == 0
    overall = pass_ok and pass_tok and pass_unique and pass_timeout
    verdict = {
        "agent": name,
        "n_ok": n_ok,
        "n_timeout": n_timeout,
        "total_tokens": total_tokens,
        "unique_top1": unique_tops,
        "rows": rows,
        "pass_ok": pass_ok,
        "pass_tokens_nonzero": pass_tok,
        "pass_top1_diverse": pass_unique,
        "pass_no_timeout": pass_timeout,
        "pass_overall": overall,
    }
    print(
        f"  -> {name}: ok={n_ok}/3, timeouts={n_timeout}, "
        f"tokens={total_tokens}, unique_top1={unique_tops}, "
        f"PASS={overall}",
        flush=True,
    )
    return verdict


def main() -> int:
    load_env()
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("OPENROUTER_API_KEY not set", file=sys.stderr)
        return 2

    backbone = os.environ.get("SANITY_BACKBONE", "openrouter/openai/gpt-5")

    # Reuse the exact case-selection logic of mini_round2_pilot.
    from scripts.mini_round2_pilot import build_sample

    cases = build_sample(seed=42, n_per_layer=25)
    sample = cases[:3]
    print(f"Sanity check on {len(sample)} cases (backbone={backbone}):")
    for c in sample:
        print(f"  - {c.case_id}  gold={c.gold_label.disease_name}")

    from harness.agents import (
        AgentClinicAdapter,
        DeepRareAdapter,
        MaiDxOAdapter,
        MDAgentsAdapter,
        MedAgentsAdapter,
    )

    results: list[dict] = []

    # mdagents: lightweight (a P2-OK on Phase 2). Keep timeout short.
    results.append(
        _run_one_agent(
            "mdagents",
            MDAgentsAdapter(backbone_id=backbone, agent_extra={"timeout_s": 300}),
            sample,
        )
    )

    # medagents: 3-stage pipeline, ~5-7 LLM calls. Bump timeout.
    results.append(
        _run_one_agent(
            "medagents",
            MedAgentsAdapter(backbone_id=backbone, agent_extra={"timeout_s": 400}),
            sample,
        )
    )

    # agentclinic: OSCE w/ ~8 inferences + a follow-up call.
    results.append(
        _run_one_agent(
            "agentclinic",
            AgentClinicAdapter(
                backbone_id=backbone,
                agent_extra={"timeout_s": 500, "total_inferences": 6},
            ),
            sample,
        )
    )

    # maidxo: 8-agent panel. Use no_budget with max_iterations=2 for cost.
    results.append(
        _run_one_agent(
            "maidxo",
            MaiDxOAdapter(
                backbone_id=backbone,
                agent_extra={
                    "mode": "no_budget",
                    "max_iterations": 2,
                    "timeout_seconds": 600,
                },
            ),
            sample,
        )
    )

    # deeprare: torch + sentence-transformers heavy; allow more time.
    results.append(
        _run_one_agent(
            "deeprare",
            DeepRareAdapter(backbone_id=backbone, agent_extra={"timeout_seconds": 900}),
            sample,
        )
    )

    # Final summary
    print("\n\n=== SUMMARY ===")
    for r in results:
        print(
            f"  {r['agent']:11s}: ok={r['n_ok']}/3, "
            f"timeout={r['n_timeout']}, tokens={r['total_tokens']:>7d}, "
            f"unique_top1={r['unique_top1']}, "
            f"PASS={r['pass_overall']}"
        )

    overall_pass = all(r["pass_overall"] for r in results)
    print(f"\nOverall: {'PASS' if overall_pass else 'PARTIAL/FAIL'}")

    # Persist
    out_path = PROJECT_ROOT / "tmp" / "gpt5_n3_sanity.log"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        f.write(
            f"# GPT-5 reasoning_effort N=3 sanity (2026-05-19)\n"
            f"# backbone={backbone}\n"
            f"# cases={[c.case_id for c in sample]}\n\n"
        )
        for r in results:
            f.write(f"## {r['agent']}\n")
            f.write(json.dumps(r, indent=2) + "\n\n")
        f.write(f"overall_pass: {overall_pass}\n")
    print(f"\nLog written to {out_path}")

    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
