"""Round 2 Phase 1 — Opus 4.7 silver-gold HPO/diagnosis extraction.

Why this script exists
----------------------
The original P1 pilot (scripts/p1_extraction_pilot.py) uses
`synthesize_vignette_from_hpo(case)` on Phenopacket-Store cases. That makes
the LLM read a vignette synthesized from the very gold HPO labels we then ask
it to recover — leaky tautology, phrase_F1 → 1.0 (see round2_worklog.md
"P1 methodology" entry).

A clean P1 evaluation needs:
  1. Real narrative free-text (we have it: PMC OA `case_excerpt`).
  2. Gold HPO labels from a *different* backbone than the testing agents.

This script provides #2: it takes the top 100 `match_type=exact_name`
candidates from `data/pmc_oa_holdout/06_candidates_for_review.jsonl` (highest
match-quality bucket, 1,047 available) and asks **Claude Opus 4.7** via
OpenRouter to re-annotate gold HPO phenotypes and the final diagnosis from
the raw `case_excerpt`. Claude Opus is independent of our test backbones
(Gemini 3 Flash, DeepSeek v3.2, GPT-5).

Outputs
-------
- data/round2/phase1/silver_gold_opus.jsonl  (100 lines, one per case)
- data/round2/phase1/SILVER_GOLD_REPORT.md

Resume support
--------------
- Checkpoint after every 10 cases.
- Re-running the script skips PMC IDs already in the output JSONL.

Budget enforcement
------------------
- Running cost printed every 10 cases.
- Hard stop if running cost > $15 (planned headroom under $20 cap).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

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


load_env()

from harness.logging.openrouter_wrapper import openrouter_chat  # noqa: E402


# Verified live 2026-05-15 via OpenRouter ping:
#   anthropic/claude-opus-4.7 → model_returned = anthropic/claude-4.7-opus-20260416
# OpenRouter usage.cost field is returned per-call; we trust it as authoritative
# (rather than re-deriving from a price table) because Opus 4.7 is not in our
# local _PRICES table in harness/logging/openrouter_wrapper.py.
OPUS_MODEL_ID = "anthropic/claude-opus-4.7"

CANDIDATES_PATH = (
    PROJECT_ROOT / "data" / "pmc_oa_holdout" / "06_candidates_for_review.jsonl"
)
OUT_DIR = PROJECT_ROOT / "data" / "round2" / "phase1"
OUT_PATH = OUT_DIR / "silver_gold_opus.jsonl"
REPORT_PATH = OUT_DIR / "SILVER_GOLD_REPORT.md"

N_CASES = 100
CHECKPOINT_EVERY = 10
HARD_COST_CAP_USD = 15.0  # below the $20 nominal cap to leave margin

SYSTEM_PROMPT = (
    "You are a senior clinical reviewer annotating gold-standard phenotype "
    "terms from a rare-disease case report. You return strict JSON only — no "
    "prose, no markdown fences."
)

USER_PROMPT_TEMPLATE = """\
You are a senior clinical reviewer annotating gold-standard phenotype terms
from a rare-disease case report. Given the patient narrative below, extract:

1. HPO phenotypes — clinical features the patient EXHIBITS (not differential
   diagnoses, not measurement values without phenotype interpretation, not
   things mentioned in passing about other family members unless explicitly
   the proband's findings).
2. Final diagnosis — as a disease name (the paper's confirmed dx).

Patient narrative:
---
{case_excerpt}
---

Return strict JSON only:
{{
  "hpo_phenotypes": [
    {{"phrase": "<NL clinical feature>", "hpo_id_guess": "<HP:NNNNNNN or null if not confident>"}}
  ],
  "final_diagnosis": "<disease name>",
  "notes": "<any uncertainty>"
}}
"""


# ------------------------- helpers -----------------------------------------


def select_cases(n: int = N_CASES) -> list[dict]:
    """First N exact_name match_type candidates from 06_candidates_for_review.jsonl.

    Deterministic by file order; the file itself was produced under seed=42
    in the upstream review-candidate pipeline (see data/pmc_oa_holdout/).
    """
    out: list[dict] = []
    with CANDIDATES_PATH.open() as f:
        for line in f:
            r = json.loads(line)
            if r.get("match_type") != "exact_name":
                continue
            out.append(r)
            if len(out) >= n:
                break
    return out


def load_done_pmc_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    done: set[str] = set()
    with path.open() as f:
        for line in f:
            try:
                r = json.loads(line)
                pid = r.get("pmc_id")
                if pid:
                    done.add(str(pid))
            except Exception:
                continue
    return done


def strip_json_fences(text: str) -> str:
    """If the model wrapped JSON in ```json ... ``` fences, peel them."""
    t = text.strip()
    if t.startswith("```"):
        # remove the opening fence (with optional language tag)
        first_newline = t.find("\n")
        if first_newline != -1:
            t = t[first_newline + 1 :]
        if t.endswith("```"):
            t = t[: -3]
        t = t.strip()
    return t


def parse_silver_gold(content: str) -> tuple[Optional[dict], Optional[str]]:
    """Return (parsed_dict, error_str). Tolerant of fenced JSON / trailing text."""
    if not content or not content.strip():
        return None, "empty content"
    cleaned = strip_json_fences(content)
    # First try direct.
    try:
        return json.loads(cleaned), None
    except Exception as e1:
        # Try to find the outermost {...} block.
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1]), None
            except Exception as e2:
                return None, f"json_decode_failed: {e2}"
        return None, f"json_decode_failed: {e1}"


# ------------------------- main loop ---------------------------------------


def main() -> int:
    if "OPENROUTER_API_KEY" not in os.environ:
        print("[FATAL] OPENROUTER_API_KEY missing", file=sys.stderr)
        return 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    cases = select_cases(N_CASES)
    print(f"[info] selected {len(cases)} exact_name candidates")

    done = load_done_pmc_ids(OUT_PATH)
    if done:
        print(f"[info] resume — {len(done)} cases already in {OUT_PATH.name}")

    running_cost = 0.0
    running_in_tokens = 0
    running_out_tokens = 0
    n_done = 0
    n_parse_fail = 0

    # Pre-compute prior running cost from existing file (if resuming) so the
    # hard-cap is global across runs.
    if OUT_PATH.exists():
        with OUT_PATH.open() as f:
            for line in f:
                try:
                    r = json.loads(line)
                    running_cost += float(r.get("cost_usd") or 0.0)
                    running_in_tokens += int(r.get("tokens_in") or 0)
                    running_out_tokens += int(r.get("tokens_out") or 0)
                    n_done += 1
                    if r.get("_error"):
                        n_parse_fail += 1
                except Exception:
                    continue
        if n_done:
            print(
                f"[info] prior running totals: cost=${running_cost:.4f} "
                f"in={running_in_tokens} out={running_out_tokens}"
            )

    with OUT_PATH.open("a") as out_f:
        for i, case in enumerate(cases):
            pmc_id = str(case["pmc_id"])
            if pmc_id in done:
                continue

            if running_cost > HARD_COST_CAP_USD:
                print(
                    f"[stop] running_cost ${running_cost:.3f} exceeds hard cap "
                    f"${HARD_COST_CAP_USD:.2f}. Stopping."
                )
                break

            excerpt = case.get("case_excerpt") or ""
            if not excerpt.strip():
                rec = {
                    "pmc_id": pmc_id,
                    "matched_orpha_name": case.get("matched_orpha_name"),
                    "case_excerpt": excerpt,
                    "silver_gold": None,
                    "extractor_model": OPUS_MODEL_ID,
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "cost_usd": 0.0,
                    "_error": "empty_case_excerpt",
                }
                out_f.write(json.dumps(rec) + "\n")
                out_f.flush()
                n_done += 1
                n_parse_fail += 1
                continue

            user_prompt = USER_PROMPT_TEMPLATE.format(case_excerpt=excerpt)
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]

            silver: Optional[dict] = None
            err: Optional[str] = None
            tokens_in = 0
            tokens_out = 0
            cost_usd = 0.0
            content = ""

            try:
                t0 = time.time()
                resp = openrouter_chat(
                    OPUS_MODEL_ID,
                    messages,
                    max_tokens=2000,
                    temperature=0.0,
                    timeout=180,
                )
                dt_ms = int((time.time() - t0) * 1000)

                usage = resp.get("usage", {}) or {}
                tokens_in = int(usage.get("prompt_tokens") or 0)
                tokens_out = int(usage.get("completion_tokens") or 0)
                # OpenRouter returns authoritative cost — use it directly.
                cost_usd = float(usage.get("cost") or 0.0)

                choices = resp.get("choices") or []
                if choices:
                    content = (choices[0].get("message") or {}).get("content") or ""
                silver, err = parse_silver_gold(content)
            except Exception as e:
                err = f"call_failed: {type(e).__name__}: {str(e)[:200]}"
                dt_ms = -1

            rec = {
                "pmc_id": pmc_id,
                "matched_orpha_name": case.get("matched_orpha_name"),
                "case_excerpt": excerpt,
                "silver_gold": silver,
                "extractor_model": OPUS_MODEL_ID,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost_usd": cost_usd,
                "latency_ms": dt_ms,
            }
            if err:
                rec["_error"] = err
                rec["_raw_excerpt"] = (content or "")[:1000]
                n_parse_fail += 1

            out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out_f.flush()

            running_cost += cost_usd
            running_in_tokens += tokens_in
            running_out_tokens += tokens_out
            n_done += 1

            if n_done % CHECKPOINT_EVERY == 0 or i == len(cases) - 1:
                print(
                    f"[ckpt] {n_done}/{len(cases)}  cost=${running_cost:.4f}  "
                    f"in_tok={running_in_tokens}  out_tok={running_out_tokens}  "
                    f"parse_fail={n_parse_fail}  last_latency_ms={dt_ms}"
                )

    print(
        f"[done] wrote {n_done} records to {OUT_PATH}  "
        f"total_cost=${running_cost:.4f}  parse_fail={n_parse_fail}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
