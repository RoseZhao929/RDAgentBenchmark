"""Score the de-leaked MIMIC-IV note eval subset with an LLM backbone.

Reads the credentialed note subset (model_input = de-leaked presentation,
gold in evaluation_only), asks a backbone for a ranked rare-disease
differential, writes recompute-engine-compatible receipts, and scores R@1/R@5
with the SAME cross-map hit logic used for every other dataset
(harness.metrics.cross_map.gold_hit_with_crossmap). Failures/timeouts/parser
errors are kept in the attempted denominator.

Safety
------
* Hard cost ceiling (--max-usd); the run aborts before a call that would exceed
  it. Live cost is tracked from the API's usage field.
* Defaults to --dry-run (no API calls): prints the plan and a cost estimate.
* Concurrency-limited, deterministic ordering, resumable (skips case_ids that
  already have a receipt in the output file).

DUA: model_input is credentialed MIMIC-derived text. Keep receipts under
gitignored data/. Only aggregate metrics are safe to copy.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE_URL = "https://litellm.dealism.ai"
PROMPT = (
    "You are an expert physician. Based ONLY on the following early hospital "
    "presentation (chief complaint, history, exam, labs, imaging), give your "
    "ranked differential diagnosis of the single most likely RARE disease.\n"
    "Return EXACTLY a numbered list of up to 5 disease names, most likely "
    "first, no commentary:\n"
    "1. <disease name>\n2. <disease name>\n...\n\n"
    "PRESENTATION:\n{note}\n"
)

RANK_RE = re.compile(r"^\s*\d+[.)]\s*(.+?)\s*$", re.M)


def parse_ranked(text: str) -> list[str]:
    out = []
    for m in RANK_RE.finditer(text or ""):
        name = m.group(1).strip().strip("*").strip()
        # drop trailing parentheticals / ORPHA ids left in
        name = re.sub(r"\s*\((?:ORPHA|OMIM)[:\s].*?\)\s*$", "", name, flags=re.I)
        if name:
            out.append(name)
    return out[:5]


def call_backbone(model: str, note: str, api_key: str, timeout: int,
                  max_tokens: int) -> dict[str, Any]:
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": PROMPT.format(note=note)}],
        "temperature": 0.0,
        "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/v1/chat/completions", data=body,
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    latency_ms = int((time.time() - t0) * 1000)
    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {}) or {}
    return {"content": content, "usage": usage, "latency_ms": latency_ms}


# DeepSeek V4 flash pricing (per 1M tokens) — override with --in-price/--out-price
DEFAULT_IN = 0.14
DEFAULT_OUT = 0.28


def est_cost(pt: int, ct: int, in_price: float, out_price: float) -> float:
    return pt / 1e6 * in_price + ct / 1e6 * out_price


def load_done(path: Path) -> set[str]:
    done = set()
    if path.exists():
        for line in path.open():
            try:
                done.add(json.loads(line)["case_id"])
            except Exception:
                pass
    return done


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path,
                    default=Path("data/mimic_iv_rd_slice/note_eval_cap10_v2.jsonl"))
    ap.add_argument("--output", type=Path,
                    default=Path("data/mimic_iv_rd_slice/predictions_mimic_note_deepseek_v4.jsonl"))
    ap.add_argument("--model", default="deepseek-v4-flash")
    ap.add_argument("--backbone-id", default="litellm/deepseek-v4-flash")
    ap.add_argument("--agent-id", default="llm_control")
    ap.add_argument("--max-usd", type=float, default=5.0)
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--in-price", type=float, default=DEFAULT_IN)
    ap.add_argument("--out-price", type=float, default=DEFAULT_OUT)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--live", dest="dry_run", action="store_false",
                    help="Actually call the API (spend money).")
    args = ap.parse_args()

    rows = [json.loads(l) for l in args.input.open() if l.strip()]
    if args.limit:
        rows = rows[: args.limit]

    if args.dry_run:
        chars = sum(r["input_char_len"] for r in rows)
        est_pt = int(chars / 4) + len(rows) * 80  # + prompt boilerplate
        est_ct = len(rows) * 60                   # ~5 short lines
        cost = est_cost(est_pt, est_ct, args.in_price, args.out_price)
        print(json.dumps({
            "mode": "DRY-RUN (no API calls)",
            "model": args.model,
            "n_cases": len(rows),
            "est_prompt_tokens": est_pt,
            "est_completion_tokens": est_ct,
            "est_cost_usd": round(cost, 4),
            "max_usd_ceiling": args.max_usd,
            "to_run_live": "re-run with --live",
        }, indent=2))
        return

    api_key = os.environ.get("LITELLM_API_KEY")
    if not api_key:
        print("ERROR: set LITELLM_API_KEY env var", file=sys.stderr)
        sys.exit(1)

    from harness.canonical_case import GoldLabel
    from harness.metrics.cross_map import gold_hit_with_crossmap

    done = load_done(args.output)
    spent = 0.0
    h1 = h5 = n_attempted = n_ok = 0
    out = args.output.open("a")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        for i, r in enumerate(rows):
            cid = r["case_id"]
            if cid in done:
                continue
            n_attempted += 1
            ev = r["evaluation_only"]
            gold = GoldLabel(orphanet_id=ev["gold_orpha"],
                             disease_name=ev["gold_disease"],
                             ccrd_id=None, omim_id=None)
            rec: dict[str, Any] = {
                "agent_id": args.agent_id, "backbone_id": args.backbone_id,
                "backbone_temperature": 0.0,
                "case_id": cid, "source_dataset": "mimic_note_deleaked",
                "source_split": "note", "pillar": "P2_phenotype_ddx",
                "eval_mode": "note_presentation",
                "task_version": r.get("task_version"),
            }
            try:
                res = call_backbone(args.model, r["model_input"], api_key,
                                    args.timeout, args.max_tokens)
                preds = parse_ranked(res["content"])
                usage = res["usage"]
                pt = usage.get("prompt_tokens", 0)
                ct = usage.get("completion_tokens", 0)
                # Prefer the provider's real cost when present; else estimate.
                call_cost = usage.get("cost")
                if call_cost is None:
                    call_cost = est_cost(pt, ct, args.in_price, args.out_price)
                spent += call_cost
                rec["ranked_predictions"] = preds
                rec["raw_response_excerpt"] = (res["content"] or "")[:500]
                rec["total_latency_ms"] = res["latency_ms"]
                rec["cost"] = {"prompt_tokens": pt, "completion_tokens": ct,
                               "cost_usd": round(call_cost, 6),
                               "provider": "litellm"}
                rec["status"] = "ok" if preds else "parser_error"
                if preds:
                    n_ok += 1
                    hit1 = gold_hit_with_crossmap(preds[0], gold)
                    hit5 = any(gold_hit_with_crossmap(p, gold) for p in preds[:5])
                    h1 += hit1
                    h5 += hit5
                    rec["_hit1"] = bool(hit1)
                    rec["_hit5"] = bool(hit5)
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
                rec["status"] = "agent_error"
                rec["ranked_predictions"] = []
                rec["error_message"] = str(e)[:200]

            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()

            if (i + 1) % 25 == 0:
                print(f"  {i+1}/{len(rows)}  spent=${spent:.4f}  "
                      f"R@1={h1/max(n_ok,1):.3f}(ok) latest_status={rec['status']}",
                      file=sys.stderr)
            if spent >= args.max_usd:
                print(f"COST CEILING hit (${spent:.4f} >= ${args.max_usd}); stopping.",
                      file=sys.stderr)
                break
    finally:
        out.close()

    print(json.dumps({
        "mode": "LIVE",
        "model": args.model,
        "n_attempted_this_run": n_attempted,
        "n_ok": n_ok,
        "R@1_variant_aware_attempted": round(h1 / n_attempted, 4) if n_attempted else None,
        "R@5_variant_aware_attempted": round(h5 / n_attempted, 4) if n_attempted else None,
        "R@1_success_denom": round(h1 / n_ok, 4) if n_ok else None,
        "spent_usd": round(spent, 4),
        "output": str(args.output),
    }, indent=2))


if __name__ == "__main__":
    main()
