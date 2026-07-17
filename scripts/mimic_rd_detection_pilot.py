"""MIMIC-IV rare-disease detection pilot — alternative metric for MIMIC.

Per 2026-05-19 reframe(user-approved):MIMIC structured-only slice has
disease names directly in `synthetic_vignette`(ICD long titles). Standard
DDx prompts encourage LLM to over-think and synthesize unifying diagnoses
instead of extracting the named rare disease. This pilot uses a different
task framing:

  "Patient has these documented conditions: [list]. Which one is the
   rare disease that should be the diagnostic focus?"

Output: agent picks one condition from the comorbidity list.
Metric: binary correctness (matches gold rare disease ORPHA via name).

This is what MIMIC structured slice can actually meaningfully evaluate:
agent's ability to **identify** rare disease in comorbidity context.
NOT a DDx-from-clinical-features task.
"""

from __future__ import annotations

import argparse
import json
import os
import re
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


def load_mimic_diverse(limit: int = 50):
    from harness.canonical_case import CanonicalCase
    out = []
    with open("data/mimic_iv_rd_slice/cases_filtered_diverse.jsonl") as f:
        for line in f:
            try:
                c = CanonicalCase.model_validate_json(line)
                out.append(c)
            except Exception as e:
                continue
            if len(out) >= limit: break
    return out


def extract_icd_conditions(case) -> list[str]:
    """Pull the ICD long titles from synthetic_vignette / metadata."""
    # synthetic_vignette: "...documented conditions: X; Y; Z."
    v = case.synthetic_vignette or ""
    m = re.search(r"conditions:\s*(.+?)\.?\s*$", v, re.IGNORECASE | re.DOTALL)
    if m:
        return [s.strip() for s in m.group(1).split(";") if s.strip()]
    return []


def build_rd_detection_prompt(case, conditions: list[str]) -> str:
    age = case.demographics.age_at_diagnosis_years if case.demographics else None
    sex = case.demographics.sex if case.demographics else None
    demo = f"A {int(age) if age else '?'}-year-old {sex or 'patient'}" if age else "A patient"

    cond_lines = "\n".join(f"  - {c}" for c in conditions)
    return f"""{demo} was admitted with the following ICD-10-documented conditions:

{cond_lines}

Question: Among these conditions, which ONE is the rare disease (Orphanet-listed, prevalence < 1 in 2,000) that should be the primary diagnostic focus?

Reply with ONLY the rare disease name from the list above, exactly as written. Do not add explanation."""


def call_llm(prompt: str, backbone_id: str) -> str:
    """Single LLM call via OpenRouter."""
    from openai import OpenAI
    api_key = os.environ["OPENROUTER_API_KEY"]
    client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
    model = backbone_id.removeprefix("openrouter/")
    extra = {}
    if "gpt-5" in model.lower() or model.lower().startswith("openai/o-"):
        extra["reasoning"] = {"effort": "minimal"}
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=128,
        temperature=0,
        extra_body=extra,
    )
    return (resp.choices[0].message.content or "").strip()


def is_match(picked: str, gold_name: str, gold_orpha_id: str | None,
             conditions: list[str], orpha_tables=None) -> bool:
    """Pick is correct if it matches gold by any of:
    1. case-insensitive exact / substring,
    2. rapidfuzz partial_ratio ≥ 85,
    3. picked → ORPHA via Orphadata (fuzzy ≥ 90) matches gold_orpha_id,
    4. picked → ORPHA cross-maps to same OMIM as gold's ORPHA.

    Catches synonym misses like 'Cholangiocarcinoma' vs
    'Intrahepatic bile duct carcinoma' (2026-05-19 fix).
    """
    if not picked or not gold_name:
        return False
    p = picked.lower().strip()
    g = gold_name.lower().strip()
    if p == g: return True
    if g in p or p in g: return True
    try:
        from rapidfuzz.fuzz import partial_ratio
        if partial_ratio(p, g) >= 85: return True
    except ImportError:
        pass
    # ORPHA-based match
    if gold_orpha_id and orpha_tables is not None:
        try:
            from harness.pmc_oa.orphanet import map_diagnosis
            res = map_diagnosis(picked, orpha_tables, fuzzy_threshold=90)
            if res.get("orpha_id") == gold_orpha_id:
                return True
            # Cross-map: predicted ORPHA's OMIMs ∩ gold ORPHA's OMIMs?
            if res.get("orpha_id"):
                p_omims = set(orpha_tables.get("orpha_to_omim", {}).get(res["orpha_id"], []))
                g_omims = set(orpha_tables.get("orpha_to_omim", {}).get(gold_orpha_id, []))
                if p_omims & g_omims:
                    return True
        except Exception:
            pass
    return False


def run(n: int, backbone: str, out: Path):
    load_env()
    cases = load_mimic_diverse(limit=n)
    print(f"[mimic-rd] N={len(cases)} backbone={backbone}", flush=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Pre-load Orphadata for ORPHA-based fuzzy match (2026-05-19 fix)
    from harness.pmc_oa.orphanet import parse_orphadata
    orpha_tables = parse_orphadata()
    rows = []
    hits = 0
    for i, case in enumerate(cases, 1):
        conditions = extract_icd_conditions(case)
        gold_name = case.gold_label.disease_name if case.gold_label else None
        if not conditions or not gold_name:
            rows.append({"case_id": case.case_id, "status": "no_conditions_or_gold"})
            continue
        prompt = build_rd_detection_prompt(case, conditions)
        t0 = time.time()
        try:
            picked = call_llm(prompt, backbone)
        except Exception as e:
            rows.append({"case_id": case.case_id, "status": "llm_error",
                         "error": str(e)[:200]})
            print(f"  [{i}/{len(cases)}] LLM ERR: {e}", flush=True)
            continue
        hit = is_match(picked, gold_name, case.gold_label.orphanet_id, conditions, orpha_tables)
        if hit: hits += 1
        rows.append({
            "case_id": case.case_id,
            "status": "ok",
            "conditions": conditions,
            "gold_disease": gold_name,
            "gold_orpha": case.gold_label.orphanet_id,
            "picked": picked,
            "hit": hit,
            "latency_ms": int((time.time() - t0) * 1000),
        })
        if i % 10 == 0 or i == len(cases):
            print(f"  [{i}/{len(cases)}] rd_detection_acc={hits}/{i} = {hits/i:.2f}", flush=True)

    with out.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    # Aggregate
    n_ok = sum(1 for r in rows if r.get("status") == "ok")
    n_hit = sum(1 for r in rows if r.get("hit"))
    print(f"\n[mimic-rd] FINAL rd_detection_acc = {n_hit}/{n_ok} = {n_hit/n_ok if n_ok else 0:.2f}")
    print(f"[mimic-rd] Wrote {out}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=50)
    p.add_argument("--backbone", default="openrouter/google/gemini-3-flash-preview-20251217")
    p.add_argument("--out", default="data/round2/phase4_pilot/mimic_rd_detection_gemini.jsonl")
    args = p.parse_args()
    run(args.n, args.backbone, Path(args.out))
