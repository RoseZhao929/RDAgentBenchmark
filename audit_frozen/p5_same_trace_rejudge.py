"""补4 — P5 same-trace re-judge (Gemini judge on the v2 repaired traces).

The paper's P5 self-preference contrast (rho=0.098 Gemini vs rho=0.616 Claude)
is confounded: the two judges scored DIFFERENT traces (Gemini v1 saw
truncated/zero traces; Claude v2 saw repaired full traces). This script fixes
that by running the Gemini judge on the SAME v2 repaired traces Claude scored,
so both judges see identical inputs.

Judge prompt/logic is copied verbatim from scripts/p5_reasoning_pilot.py
(_JUDGE_SYSTEM/_JUDGE_PROMPT, chunking >5000 chars, per-axis mean). Transport
is LiteLLM (OpenAI-compatible) instead of OpenRouter.

Outputs:
  audit_frozen/_p5_gemini_same_trace_scores.jsonl
  audit_frozen/_p5_same_trace_report.json
"""
from __future__ import annotations
import sys, json, re, os, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO)); os.chdir(REPO)
from openai import OpenAI  # noqa: E402
from scipy import stats  # noqa: E402
import recompute_engine as eng  # noqa: E402  (orphadata + fuzzy patches + gold)
from harness.metrics.cross_map import gold_hit_with_crossmap  # noqa: E402
_GOLD, _ = eng.load_gold()

LITELLM_BASE = 'https://litellm.dealism.ai/v1'
LITELLM_KEY = os.environ.get('LITELLM_API_KEY', '')  # set LITELLM_API_KEY in env; do NOT hardcode
GEMINI_JUDGE = 'google/gemini-3-flash-preview'   # same family as paper's v1 Gemini judge
OUT = REPO / 'audit_frozen'

_client = OpenAI(api_key=LITELLM_KEY, base_url=LITELLM_BASE)

# ---- judge prompt copied verbatim from scripts/p5_reasoning_pilot.py ----
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

_JSON_RE = re.compile(r"\{[^{}]*\"factual_accuracy\"[^{}]*\}", re.DOTALL)
AXES = ("factual_accuracy", "relevance", "depth", "faithfulness")


def _chunk_trace(trace, chunk_size=3000, overlap=500):
    if not trace:
        return [""]
    if len(trace) <= chunk_size:
        return [trace]
    chunks, step, i = [], max(1, chunk_size - overlap), 0
    while i < len(trace):
        chunks.append(trace[i:i + chunk_size])
        if i + chunk_size >= len(trace):
            break
        i += step
    return chunks


def _judge_single(vignette, gold_disease, ranked, trace_segment, max_tokens=2500, label=""):
    trace_for_judge = trace_segment or "(empty trace)"
    if label:
        trace_for_judge = f"[{label}]\n" + trace_for_judge
    msg = _JUDGE_PROMPT.format(
        vignette=(vignette or "(no vignette)")[:3000],
        gold_disease=gold_disease or "(unknown)",
        ranked=", ".join(ranked[:5]) if ranked else "(none)",
        trace=trace_for_judge,
    )
    t0 = time.time()
    try:
        resp = _client.chat.completions.create(
            model=GEMINI_JUDGE,
            messages=[{"role": "system", "content": _JUDGE_SYSTEM},
                      {"role": "user", "content": msg}],
            max_tokens=max_tokens, temperature=0.0,
        )
    except Exception as e:  # noqa: BLE001
        return {"error": f"judge_call_failed: {type(e).__name__}: {e}", "latency_ms": 0}
    lat = int((time.time() - t0) * 1000)
    content = resp.choices[0].message.content or ""
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        m = _JSON_RE.search(content)
        if not m:
            return {"error": "judge JSON parse failed", "raw": content[:400], "latency_ms": lat}
        data = json.loads(m.group(0))
    out = {}
    for k in AXES:
        try:
            iv = int(data.get(k))
        except (TypeError, ValueError):
            iv = -1
        out[k] = iv if 1 <= iv <= 5 else None
    out["notes"] = data.get("notes", "")
    out["latency_ms"] = lat
    u = resp.usage
    out["judge_prompt_tokens"] = u.prompt_tokens if u else 0
    out["judge_completion_tokens"] = u.completion_tokens if u else 0
    return out


def call_judge(vignette, gold_disease, ranked, trace, chunk_threshold=5000):
    chunks = _chunk_trace(trace) if (trace and len(trace) > chunk_threshold) else [trace]
    per_axis = {a: [] for a in AXES}
    notes, used, ptok, ctok, lat, last_err = [], 0, 0, 0, 0, None
    for idx, ch in enumerate(chunks):
        label = f"chunk {idx+1}/{len(chunks)}" if len(chunks) > 1 else ""
        r = _judge_single(vignette, gold_disease, ranked, ch, label=label)
        lat += int(r.get("latency_ms") or 0)
        if r.get("error"):
            last_err = r["error"]; continue
        used += 1; ptok += r.get("judge_prompt_tokens", 0); ctok += r.get("judge_completion_tokens", 0)
        for a in AXES:
            v = r.get(a)
            if isinstance(v, int) and 1 <= v <= 5:
                per_axis[a].append(v)
        if r.get("notes"):
            notes.append(str(r["notes"]))
    if used == 0:
        return {"error": last_err or "all chunks failed", "judge_chunks_used": 0,
                "judge_chunks_total": len(chunks), "latency_ms": lat}
    out = {a: (round(sum(v) / len(v), 2) if v else None) for a, v in per_axis.items()}
    out["notes"] = " | ".join(notes)[:1000]
    out["latency_ms"] = lat; out["judge_prompt_tokens"] = ptok
    out["judge_completion_tokens"] = ctok; out["judge_chunks_used"] = used
    out["judge_chunks_total"] = len(chunks)
    return out


def load_v2_traces():
    """v2 repaired reasoning traces + the gold/ranked context Claude scored."""
    recs = {}
    for l in open('data/round2/phase1/p5_reasoning_results_v2.jsonl'):
        r = json.loads(l)
        recs[(r['agent_id'], r['case_id'])] = r
    return recs


def load_claude_scores():
    """v2 judge scores = Claude on the same traces."""
    d = {}
    for l in open('data/round2/phase1/p5_judge_scores_v2.jsonl'):
        r = json.loads(l)
        d[(r['agent_id'], r['case_id'])] = r
    return d


def top1_hit(agent, case_id, ranked):
    """True Pillar-2 diagnostic correctness: does top-1 prediction hit gold?"""
    _, g = _GOLD.get(case_id, (None, None))
    if not g or not ranked:
        return None
    return 1 if gold_hit_with_crossmap(ranked[0], g) else 0


def spearman_faith_vs_acc(rows):
    """Spearman rho between judge faithfulness score and ACTUAL Pillar-2
    diagnostic correctness (top-1 hit 0/1) — the paper's decoupling test
    (faithfulness rank vs accuracy rank), NOT faithfulness vs the judge's own
    factual_accuracy axis."""
    f = [r['faithfulness'] for r in rows if r.get('faithfulness') is not None and r.get('top1_hit') is not None]
    a = [r['top1_hit'] for r in rows if r.get('faithfulness') is not None and r.get('top1_hit') is not None]
    if len(f) < 3:
        return None, None, len(f)
    rho, p = stats.spearmanr(f, a)
    return round(float(rho), 3), float(p), len(f)


def main():
    v2 = load_v2_traces()
    claude = load_claude_scores()
    out_path = OUT / '_p5_gemini_same_trace_scores.jsonl'
    fout = out_path.open('w')

    gemini_rows = []
    print(f"re-judging {len(v2)} v2 traces with Gemini ({GEMINI_JUDGE}) via LiteLLM...", file=sys.stderr)
    for (agent, case_id), rec in sorted(v2.items()):
        trace = rec.get('reasoning_trace') or rec.get('raw_response_excerpt') or ""
        # vignette: reconstruct from the record's own context if present, else empty
        gold = None
        cl = claude.get((agent, case_id))
        gold = (cl or {}).get('gold_disease')
        ranked = rec.get('ranked_predictions') or (cl or {}).get('ranked') or []
        sc = call_judge(vignette=rec.get('_vignette') or "", gold_disease=gold, ranked=ranked, trace=trace)
        row = {'agent_id': agent, 'case_id': case_id, 'trace_len': len(trace),
               'judge': 'gemini-3-flash-preview', 'scores': sc}
        fout.write(json.dumps(row) + "\n")
        g = {a: sc.get(a) for a in AXES}
        g.update({'agent_id': agent, 'case_id': case_id, 'trace_len': len(trace),
                  'top1_hit': top1_hit(agent, case_id, ranked)})
        gemini_rows.append(g)
        print(f"  [{agent}/{case_id[:24]:24s}] tl={len(trace):6d} "
              f"F={sc.get('faithfulness')} A={sc.get('factual_accuracy')} "
              f"chunks={sc.get('judge_chunks_used')}", file=sys.stderr)
    fout.close()

    # Claude rows on the SAME traces (from v2 judge file)
    claude_rows = []
    for (agent, case_id), r in claude.items():
        s = r.get('scores') or {}
        ranked = r.get('ranked') or (v2.get((agent, case_id), {}) or {}).get('ranked_predictions') or []
        claude_rows.append({'agent_id': agent, 'case_id': case_id,
                            'faithfulness': s.get('faithfulness'),
                            'factual_accuracy': s.get('factual_accuracy'),
                            'top1_hit': top1_hit(agent, case_id, ranked),
                            'trace_len': r.get('trace_len')})

    g_rho, g_p, g_n = spearman_faith_vs_acc(gemini_rows)
    c_rho, c_p, c_n = spearman_faith_vs_acc(claude_rows)

    # cross-judge agreement on faithfulness (same traces, both judges)
    pairs = []
    gmap = {(r['agent_id'], r['case_id']): r for r in gemini_rows}
    for r in claude_rows:
        k = (r['agent_id'], r['case_id'])
        if k in gmap and r.get('faithfulness') is not None and gmap[k].get('faithfulness') is not None:
            pairs.append((r['faithfulness'], gmap[k]['faithfulness']))
    cross_rho = cross_p = None
    if len(pairs) >= 3:
        cross_rho, cross_p = stats.spearmanr([x for x, _ in pairs], [y for _, y in pairs])
        cross_rho = round(float(cross_rho), 3); cross_p = float(cross_p)

    report = {
        'setup': 'SAME v2 repaired traces scored by BOTH judges (fixes the paper confound)',
        'gemini_judge': GEMINI_JUDGE, 'claude_judge': 'anthropic/claude-sonnet-4.5 (v2, pre-existing)',
        'n_traces': len(v2),
        'faithfulness_vs_accuracy_spearman': {
            'gemini_same_trace': {'rho': g_rho, 'p': g_p, 'n': g_n},
            'claude_same_trace': {'rho': c_rho, 'p': c_p, 'n': c_n},
        },
        'paper_confounded_values': {'gemini_v1': 0.098, 'claude_v2': 0.616,
                                    'note': 'v1 Gemini scored truncated/zero traces; not comparable'},
        'cross_judge_faithfulness_agreement_same_trace': {'rho': cross_rho, 'p': cross_p, 'n_pairs': len(pairs)},
        'verdict': 'With both judges on identical repaired traces, the Gemini-vs-Claude faithfulness/'
                   'accuracy decoupling can now be compared apples-to-apples; any remaining gap is a '
                   'true judge-family effect, not the trace-capture artifact.',
    }
    (OUT / '_p5_same_trace_report.json').write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))


if __name__ == '__main__':
    main()
