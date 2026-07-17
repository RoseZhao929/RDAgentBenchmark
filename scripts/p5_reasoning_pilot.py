"""Round 2 Phase 1 — Pillar 5 reasoning-trace pilot.

Setup (per round2_plan.md §3):
- 10 PP-Store cases, seed=42 (first 10 of the same shuffle as mini pilot).
- 4 agents: llm_control, mdagents, maidxo, deeprare.
- Backbone: Gemini Flash via OpenRouter.
- LLM-judge: Gemini Flash with a 4-axis (1-5) rubric.

Each (agent, case) emits a PredictionLog with `reasoning_trace`. We then send
each trace to Gemini Flash as a judge with the rubric in `_JUDGE_PROMPT`. The
judge returns JSON `{factual_accuracy, relevance, depth, faithfulness, notes}`.

Per round2_plan.md: 40 agent calls + 40 judge calls ≈ $0.20 on Gemini Flash.

Output:
  data/round2/phase1/p5_reasoning_results.jsonl (per-agent predict log)
  data/round2/phase1/p5_judge_scores.jsonl     (per-(agent,case,judge) score)
  data/round2/phase1/P5_REPORT.md
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def load_env(env_path: Path = PROJECT_ROOT / ".env") -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


# --------------- sample ----------------------

def build_pp_sample(seed: int = 42, n: int = 10) -> list:
    """First N of the seed-42 PP-Store shuffle."""
    from harness.ingest import ingest_phenopacket_store
    rng = random.Random(seed)
    pp_all = list(ingest_phenopacket_store(
        str(PROJECT_ROOT / "data" / "phenopacket_store" / "notebooks")
    ))
    rng.shuffle(pp_all)
    return pp_all[:n]


# --------------- adapter factory ---------------

def make_adapter(name: str, backbone_id: str):
    from harness.agents import (
        LLMControlAdapter,
        MDAgentsAdapter,
        MaiDxOAdapter,
        DeepRareAdapter,
    )
    if name == "llm_control":
        return LLMControlAdapter(backbone_id=backbone_id)
    if name == "mdagents":
        # Force intermediate difficulty to guarantee a reasoning_trace dump
        # (basic difficulty path in adapter does NOT populate reasoning_trace).
        return MDAgentsAdapter(
            backbone_id=backbone_id,
            agent_extra={"difficulty": "intermediate"},
        )
    if name == "maidxo":
        return MaiDxOAdapter(
            backbone_id=backbone_id,
            agent_extra={"mode": "no_budget", "max_iter": 1},
        )
    if name == "deeprare":
        return DeepRareAdapter(backbone_id=backbone_id)
    raise ValueError(f"unknown agent {name}")


# --------------- LLM judge -----------------------

_JUDGE_SYSTEM = (
    "You are a senior clinical reviewer scoring the quality of an AI agent's "
    "reasoning trace on a rare-disease diagnostic task. Return STRICT JSON only."
)

_JUDGE_PROMPT = """You are a senior clinical reviewer. Given a rare-disease case and an AI agent's reasoning trace, score the trace on 4 axes (1-5 each):
- factual_accuracy: are medical claims correct?
- relevance: do they address the actual differential?
- depth: thorough vs surface-level?
- faithfulness: do the conclusions match what the trace establishes?

Case:
{vignette}

Gold diagnosis: {gold_disease}

Agent ranked predictions (top 5): {ranked}

Reasoning trace:
{trace}

Return STRICT JSON of the form:
{{"factual_accuracy": <1-5>, "relevance": <1-5>, "depth": <1-5>, "faithfulness": <1-5>, "notes": "<short 1-2 sentence comment>"}}

JSON only, no markdown fence."""


def _strip_or_prefix(model_id: str) -> str:
    if model_id.startswith("openrouter/"):
        return model_id[len("openrouter/"):]
    return model_id


_JSON_RE = re.compile(r"\{[^{}]*\"factual_accuracy\"[^{}]*\}", re.DOTALL)


def _chunk_trace(trace: str, chunk_size: int = 3000, overlap: int = 500) -> List[str]:
    """FIX P5-4 (2026-05-15): split very long traces into overlapping chunks.

    DeepRare produces ~18k-char traces that exceed our prior 8k clip; chunking
    lets the LLM judge see all sections. Chunks overlap by `overlap` chars so
    a sentence cut mid-section doesn't lose context. Returns >=1 chunk.
    """
    if not trace:
        return [""]
    if len(trace) <= chunk_size:
        return [trace]
    chunks: List[str] = []
    step = max(1, chunk_size - overlap)
    i = 0
    while i < len(trace):
        chunks.append(trace[i : i + chunk_size])
        if i + chunk_size >= len(trace):
            break
        i += step
    return chunks


def _judge_single(
    vignette: str,
    gold_disease: str,
    ranked: List[str],
    trace_segment: str,
    judge_model: str,
    max_tokens: int,
    chunk_label: str = "",
) -> Dict[str, Any]:
    """One judge call for a single (possibly-chunked) trace segment."""
    from harness.logging.openrouter_wrapper import timed_openrouter_chat
    vignette_clipped = vignette[:3000] if vignette else "(no vignette)"
    trace_for_judge = trace_segment if trace_segment else "(empty trace)"
    if chunk_label:
        trace_for_judge = f"[{chunk_label}]\n" + trace_for_judge
    msg = _JUDGE_PROMPT.format(
        vignette=vignette_clipped,
        gold_disease=gold_disease or "(unknown)",
        ranked=", ".join(ranked[:5]) if ranked else "(none)",
        trace=trace_for_judge,
    )
    messages = [
        {"role": "system", "content": _JUDGE_SYSTEM},
        {"role": "user", "content": msg},
    ]
    try:
        resp, latency_ms = timed_openrouter_chat(
            _strip_or_prefix(judge_model),
            messages,
            max_tokens=max_tokens,
            temperature=0.0,
            timeout=180,
        )
    except Exception as e:  # noqa: BLE001
        return {"error": f"judge_call_failed: {type(e).__name__}: {e}", "latency_ms": 0}

    content = ""
    try:
        choice = resp["choices"][0]["message"]["content"]
        if isinstance(choice, str):
            content = choice
        elif isinstance(choice, list):
            content = "\n".join(
                c.get("text", "") for c in choice if isinstance(c, dict)
            )
    except Exception:
        return {"error": "no content in judge response", "latency_ms": latency_ms}

    # Strip markdown fences if model added them despite the instruction.
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        m = _JSON_RE.search(content)
        if not m:
            return {"error": "judge JSON parse failed",
                    "raw": content[:600], "latency_ms": latency_ms}
        try:
            data = json.loads(m.group(0))
        except Exception as e:  # noqa: BLE001
            return {"error": f"judge JSON parse failed: {e}",
                    "raw": content[:600], "latency_ms": latency_ms}

    # coerce to int in 1..5 (clamp)
    out: Dict[str, Any] = {}
    for k in ("factual_accuracy", "relevance", "depth", "faithfulness"):
        v = data.get(k)
        try:
            iv = int(v)
        except (TypeError, ValueError):
            iv = -1
        if 1 <= iv <= 5:
            out[k] = iv
        else:
            out[k] = None
    out["notes"] = data.get("notes", "")
    out["latency_ms"] = latency_ms
    usage = resp.get("usage") or {}
    out["judge_prompt_tokens"] = int(usage.get("prompt_tokens", 0) or 0)
    out["judge_completion_tokens"] = int(usage.get("completion_tokens", 0) or 0)
    return out


def call_judge(
    vignette: str,
    gold_disease: str,
    ranked: List[str],
    trace: str,
    judge_model: str = "anthropic/claude-sonnet-4.5",
    max_tokens: int = 800,
    chunk_threshold: int = 5000,
    chunk_size: int = 3000,
    chunk_overlap: int = 500,
) -> Dict[str, Any]:
    """Send judge prompt(s), parse strict-JSON, average across chunks if long.

    FIX P5-3 (2026-05-15): judge_model default flipped to a non-Gemini family
    (Claude Sonnet 4.5) so we can detect self-preference bias against the
    Gemini-Flash backbone running under test.

    FIX P5-4 (2026-05-15): if `trace` exceeds `chunk_threshold` chars, split
    into overlapping chunks (`chunk_size` chars, `chunk_overlap` overlap),
    judge each, and return the per-axis MEAN score. The result records
    `judge_chunks_used` so downstream audits can see whether a row came from
    a single call or an averaged multi-chunk call.
    """
    if trace and len(trace) > chunk_threshold:
        chunks = _chunk_trace(trace, chunk_size=chunk_size, overlap=chunk_overlap)
    else:
        chunks = [trace]

    axes = ("factual_accuracy", "relevance", "depth", "faithfulness")
    per_axis: Dict[str, List[int]] = {a: [] for a in axes}
    notes_parts: List[str] = []
    sum_prompt_t = 0
    sum_completion_t = 0
    sum_latency = 0
    last_error: Optional[str] = None
    chunks_used = 0
    chunk_results: List[Dict[str, Any]] = []

    for idx, chunk in enumerate(chunks):
        label = f"chunk {idx+1}/{len(chunks)}" if len(chunks) > 1 else ""
        result = _judge_single(
            vignette=vignette,
            gold_disease=gold_disease,
            ranked=ranked,
            trace_segment=chunk,
            judge_model=judge_model,
            max_tokens=max_tokens,
            chunk_label=label,
        )
        chunk_results.append(result)
        sum_latency += int(result.get("latency_ms") or 0)
        if result.get("error"):
            last_error = result["error"]
            continue
        chunks_used += 1
        sum_prompt_t += int(result.get("judge_prompt_tokens") or 0)
        sum_completion_t += int(result.get("judge_completion_tokens") or 0)
        any_axis = False
        for a in axes:
            v = result.get(a)
            if isinstance(v, int) and 1 <= v <= 5:
                per_axis[a].append(v)
                any_axis = True
        if any_axis and result.get("notes"):
            notes_parts.append(str(result["notes"]))

    if chunks_used == 0:
        # All chunks failed
        return {
            "error": last_error or "judge JSON parse failed",
            "judge_chunks_used": 0,
            "judge_chunks_total": len(chunks),
            "latency_ms": sum_latency,
        }

    out: Dict[str, Any] = {}
    for a in axes:
        vs = per_axis[a]
        out[a] = round(sum(vs) / len(vs), 2) if vs else None
    out["notes"] = " | ".join(notes_parts)[:1000]
    out["latency_ms"] = sum_latency
    out["judge_prompt_tokens"] = sum_prompt_t
    out["judge_completion_tokens"] = sum_completion_t
    out["judge_chunks_used"] = chunks_used
    out["judge_chunks_total"] = len(chunks)
    return out


# --------------- vignette / trace helpers -------

def case_vignette_for_judge(case) -> str:
    """Plain HPO-listing summary for the judge to read."""
    parts: List[str] = []
    age = case.demographics.age_at_onset_years
    sex = case.demographics.sex
    demo = []
    if age is not None:
        demo.append(f"age at onset {age:.0f} y")
    if sex and sex != "unknown":
        demo.append(sex)
    if demo:
        parts.append("Demographics: " + ", ".join(demo) + ".")
    present = [t for t in case.gold_hpo_terms if not t.negated]
    if present:
        parts.append(
            "Clinical phenotypes (HPO): "
            + "; ".join((t.label or t.id) for t in present)
            + "."
        )
    return "\n".join(parts)


def extract_trace(log) -> str:
    """Prefer log.reasoning_trace; fall back to raw_response_excerpt."""
    if log.reasoning_trace:
        return log.reasoning_trace
    if log.raw_response_excerpt:
        return log.raw_response_excerpt
    return ""


# --------------- resume helpers -------------------

def load_done_predictions(path: Path) -> set:
    if not path.exists():
        return set()
    seen = set()
    with path.open() as f:
        for line in f:
            try:
                r = json.loads(line)
                seen.add((r["agent_id"], r["case_id"]))
            except (json.JSONDecodeError, KeyError):
                continue
    return seen


def load_done_judge(path: Path) -> set:
    if not path.exists():
        return set()
    seen = set()
    with path.open() as f:
        for line in f:
            try:
                r = json.loads(line)
                seen.add((r["agent_id"], r["case_id"]))
            except (json.JSONDecodeError, KeyError):
                continue
    return seen


# --------------- main loop ------------------------

def run(
    agents: List[str],
    backbone_id: str,
    judge_model: str,
    pred_path: Path,
    judge_path: Path,
    n: int = 10,
    seed: int = 42,
    resume: bool = True,
    skip_predict: bool = False,
) -> None:
    from harness.logging import JsonlPredictionLogger, read_logs

    print(f"[p5] sample: PP-Store n={n} seed={seed}", flush=True)
    cases = build_pp_sample(seed=seed, n=n)
    print(f"  cases ready: {len(cases)}", flush=True)

    done_pred = load_done_predictions(pred_path) if resume else set()
    done_judge = load_done_judge(judge_path) if resume else set()
    if done_pred:
        print(f"[p5] resume: {len(done_pred)} predictions in log", flush=True)
    if done_judge:
        print(f"[p5] resume: {len(done_judge)} judge rows in log", flush=True)

    pred_path.parent.mkdir(parents=True, exist_ok=True)
    pred_logger = JsonlPredictionLogger(pred_path)
    judge_f = judge_path.open("a", buffering=1)

    run_id = f"p5_phase1_{int(time.time())}"

    # Phase A: generate predictions
    if not skip_predict:
        for agent_name in agents:
            print(f"\n[p5] === predict :: {agent_name} ===", flush=True)
            try:
                adapter = make_adapter(agent_name, backbone_id)
            except Exception as e:
                print(f"  [p5] adapter init FAIL: {type(e).__name__}: {e}", flush=True)
                traceback.print_exc()
                continue

            for case in cases:
                if (agent_name, case.case_id) in done_pred:
                    continue
                t0 = time.time()
                try:
                    log = adapter.predict(
                        case,
                        pillar="P5_reasoning_communication",
                        eval_mode="gold_hpo",
                        run_id=run_id,
                    )
                except Exception as e:  # noqa: BLE001
                    print(f"  [p5] {agent_name} / {case.case_id}: predict FAILED "
                          f"{type(e).__name__}: {e}", flush=True)
                    traceback.print_exc()
                    continue

                pred_logger.write(log)
                trace_len = len(log.reasoning_trace or "")
                print(
                    f"  [predict] {agent_name} / {case.case_id[:30]:30s} "
                    f"st={log.status:14s} {int(time.time()-t0):4d}s  "
                    f"trace_len={trace_len:5d}  "
                    f"top1={log.ranked_predictions[:1]}",
                    flush=True,
                )

    pred_logger.close()

    # Phase B: judge each (agent, case) prediction
    print(f"\n[p5] === judge :: {judge_model} ===", flush=True)
    all_logs = read_logs(pred_path)
    by_key = {(L.agent_id, L.case_id): L for L in all_logs}
    case_by_id = {c.case_id: c for c in cases}

    judged_count = 0
    for (agent_name, case_id), log in by_key.items():
        if (agent_name, case_id) in done_judge:
            continue
        case = case_by_id.get(case_id)
        if case is None:
            continue
        trace = extract_trace(log)
        if not trace:
            # Log a no-trace stub anyway so resume is idempotent
            judge_f.write(json.dumps({
                "agent_id": agent_name,
                "case_id": case_id,
                "scores": {"error": "no trace to judge"},
                "trace_len": 0,
                "ranked": log.ranked_predictions[:5],
                "gold_disease": case.gold_label.disease_name,
            }) + "\n")
            continue
        vignette = case_vignette_for_judge(case)
        gold_disease = case.gold_label.disease_name or "(unknown)"
        scores = call_judge(
            vignette=vignette,
            gold_disease=gold_disease,
            ranked=log.ranked_predictions[:5],
            trace=trace,
            judge_model=judge_model,
        )
        judged_count += 1
        judge_f.write(json.dumps({
            "agent_id": agent_name,
            "case_id": case_id,
            "scores": scores,
            "trace_len": len(trace),
            "ranked": log.ranked_predictions[:5],
            "gold_disease": gold_disease,
        }) + "\n")
        score_str = ",".join(
            f"{k[:3]}={scores.get(k, 'NA')}"
            for k in ("factual_accuracy", "relevance", "depth", "faithfulness")
        )
        print(f"  [judge] {agent_name} / {case_id[:30]:30s}  {score_str}", flush=True)

    judge_f.close()
    print(f"\n[p5] done. predictions → {pred_path}; judge rows → {judge_path}", flush=True)


# --------------- aggregate + report ---------------

def aggregate_and_report(
    judge_path: Path,
    report_path: Path,
    judge_model: str = "anthropic/claude-sonnet-4.5",
) -> None:
    if not judge_path.exists():
        print(f"[p5] no judge file at {judge_path}; nothing to aggregate.")
        return

    rows = []
    with judge_path.open() as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    axes = ("factual_accuracy", "relevance", "depth", "faithfulness")
    by_agent: dict[str, dict] = {}
    for r in rows:
        agent = r["agent_id"]
        s = r.get("scores") or {}
        by_agent.setdefault(agent, {"per_axis": {a: [] for a in axes},
                                     "trace_lens": [],
                                     "judge_errors": 0,
                                     "chunks_used": [],
                                     "n": 0})
        by_agent[agent]["n"] += 1
        by_agent[agent]["trace_lens"].append(r.get("trace_len", 0))
        if s.get("error"):
            by_agent[agent]["judge_errors"] += 1
            continue
        ch = s.get("judge_chunks_used")
        if isinstance(ch, int):
            by_agent[agent]["chunks_used"].append(ch)
        for a in axes:
            v = s.get(a)
            # FIX P5-4: chunked scores are floats (means); accept any numeric in [1,5].
            if isinstance(v, (int, float)) and 1 <= v <= 5:
                by_agent[agent]["per_axis"][a].append(float(v))

    md = ["# Round 2 Phase 1 — Pillar 5 (Reasoning Trace) Report (v2)\n"]
    md.append(f"\n- Sample: 10 Phenopacket-Store cases (seed=42)")
    md.append(f"- Agents: {', '.join(sorted(by_agent.keys())) if by_agent else '(none)'}")
    md.append(f"- LLM judge: `{judge_model}` (non-Gemini family to mitigate self-preference bias)\n")
    md.append("## Per-agent mean (1-5) scores\n")
    md.append("| Agent | n | factual | relevance | depth | faithful | mean trace_len | mean chunks | judge errors |")
    md.append("|---|---|---|---|---|---|---|---|---|")

    def mean(xs):
        return sum(xs) / len(xs) if xs else float("nan")

    for agent, info in sorted(by_agent.items()):
        means = {a: mean(info["per_axis"][a]) for a in axes}
        trace_mean = mean(info["trace_lens"])
        chunks_mean = mean(info["chunks_used"]) if info["chunks_used"] else float("nan")
        md.append(
            f"| `{agent}` | {info['n']} | "
            f"{means['factual_accuracy']:.2f} | "
            f"{means['relevance']:.2f} | "
            f"{means['depth']:.2f} | "
            f"{means['faithfulness']:.2f} | "
            f"{trace_mean:.0f} | "
            f"{chunks_mean:.2f} | "
            f"{info['judge_errors']} |"
        )

    # Chunk-distribution per agent
    md.append("\n## Trace chunking (judge_chunks_used)\n")
    md.append("| Agent | n graded | min | max | distribution |")
    md.append("|---|---|---|---|---|")
    for agent, info in sorted(by_agent.items()):
        ch = info["chunks_used"]
        if not ch:
            md.append(f"| `{agent}` | 0 | – | – | (no graded rows) |")
            continue
        from collections import Counter
        dist = Counter(ch)
        dist_str = ", ".join(f"{k}×{v}" for k, v in sorted(dist.items()))
        md.append(f"| `{agent}` | {len(ch)} | {min(ch)} | {max(ch)} | {dist_str} |")

    md.append("\n## Notes\n")
    md.append(f"- Judge model: `{judge_model}` — picked **outside** the Gemini Flash "
              "family used by the agents under test, so any residual self-preference bias "
              "would push *against* `llm_control` rather than toward it.")
    md.append("- Score scale: 1 (poor) → 5 (excellent) per axis. Chunked traces report the mean across chunks (so values can be fractional).")
    md.append("- `judge_chunks_used` > 1 indicates the trace exceeded 5 000 chars and "
              "was split into 3 000-char chunks (500-char overlap); each chunk was judged "
              "independently and the per-axis scores were averaged.")
    md.append("- `judge errors` counts rows where every chunk failed JSON parsing or the trace was empty.")

    report_path.write_text("\n".join(md))
    print(f"[p5] report → {report_path}")
    print("\n".join(md))


# --------------- CLI -------------------------------

if __name__ == "__main__":
    load_env()
    p = argparse.ArgumentParser()
    p.add_argument("--agents", default="llm_control,mdagents,maidxo,deeprare")
    p.add_argument("--backbone", default="openrouter/google/gemini-3-flash-preview")
    # FIX P5-3: default judge flipped to a non-Gemini family (Claude Sonnet
    # 4.5) so we can detect self-preference bias against scaffolded agents.
    p.add_argument("--judge", default="anthropic/claude-sonnet-4.5")
    p.add_argument("--n", type=int, default=10)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", default="data/round2/phase1/p5_reasoning_results.jsonl")
    p.add_argument("--judge-out", default="data/round2/phase1/p5_judge_scores.jsonl")
    p.add_argument("--report", default="data/round2/phase1/P5_REPORT.md")
    p.add_argument("--report-only", action="store_true")
    p.add_argument("--skip-predict", action="store_true",
                   help="Re-judge existing predictions without re-running agents.")
    p.add_argument("--no-resume", action="store_true")
    args = p.parse_args()

    pred_path = Path(args.out)
    judge_path = Path(args.judge_out)
    report_path = Path(args.report)
    agents = [a.strip() for a in args.agents.split(",") if a.strip()]

    if not args.report_only:
        run(
            agents=agents,
            backbone_id=args.backbone,
            judge_model=args.judge,
            pred_path=pred_path,
            judge_path=judge_path,
            n=args.n,
            seed=args.seed,
            resume=not args.no_resume,
            skip_predict=args.skip_predict,
        )

    aggregate_and_report(judge_path, report_path, judge_model=args.judge)
