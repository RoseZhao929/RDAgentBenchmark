"""Auto Check 3 (cutoff verification) — LLM agent over PMC XMLs.

For each candidate, judge whether the case is genuinely a *post-2024 new report*
or a republication/case-series of pre-cutoff cases.

Output: data/pmc_oa_holdout/auto_check3_results.jsonl
Each row:
  {pmc_id, decision: pass|fail|uncertain, reason: str,
   evidence_quote: str, model: str, pmc_pub_date: str}

Decision semantics (mirror HANDOFF INSTRUCTIONS §3 Check 3):
  - pass:        PMC pub-date ≥ 2024-01-01 AND no republication signal AND
                 (no pre-2024 admission dates in case body OR none < 2022 with no >=2024 admission)
  - fail:        body has "case series of patients managed YYYY-YYYY" with YYYY<2024,
                 OR "previously reported in [pre-2024 ref]",
                 OR "first described in YYYY" YYYY<2024 of the SAME case,
                 OR retrospective/follow-up of older cohort,
                 OR pub_year_in_text <2022 and no recent re-evaluation
  - uncertain:   ambiguous; needs human glance

Cost estimate: 250 calls × ~5k input tokens × $0.50/M = $0.625; output tiny.
"""
from __future__ import annotations
import argparse
import csv
import gzip
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path("/Users/yutianzhao/Desktop/RDAgentBenchmark")
sys.path.insert(0, str(ROOT))
from harness.logging.openrouter_wrapper import openrouter_chat

HOLDOUT_DIR = ROOT / "data/pmc_oa_holdout"
OLD_HANDOFF = HOLDOUT_DIR / "HANDOFF"
XML_CACHE = HOLDOUT_DIR / "03_xml"
OUT_PATH = HOLDOUT_DIR / "auto_check3_results.jsonl"

MODEL = "google/gemini-3-flash-preview-20251217"

SYSTEM_PROMPT = """You are a careful date-verification reviewer for a rare-disease case benchmark.

You will be given:
1. The PMC article's publication date (machine-extracted, reliable).
2. An excerpt from the article body (abstract + intro + earliest case section).

Your job: decide whether this article is a *genuine post-2024 new case report* (PASS)
or a republication / retrospective of pre-cutoff cases (FAIL), or genuinely ambiguous (UNCERTAIN).

PASS criteria (ALL must hold):
  - PMC publication date >= 2024-01-01 (you'll be told this).
  - No statement like "case series of patients managed YYYY-YYYY" with all YYYY < 2024.
  - No "previously reported in [pre-2024 reference]" about the same case.
  - No "first described in YYYY" with YYYY < 2024 referring to THIS patient.
  - No clearly retrospective framing of a cohort with admissions years before 2022.
  - It's acceptable that the AUTHORS previously published related but DIFFERENT cases —
    that's not a republication of the same case.
  - A single patient with admission in e.g. 2023 (close to cutoff) is acceptable.

FAIL signals (any one is enough):
  - Title or abstract uses "case series", "retrospective", "literature review",
    "follow-up of [pre-2024 cohort]" — AND patient details are clearly pre-2024.
  - Patient cohort table lists admission dates all < 2024.
  - "Previously reported in [Author, YYYY]" with YYYY < 2024 about THIS proband.
  - Repeated long-term follow-up reports where the index event was pre-2022.

UNCERTAIN:
  - Mixed cohort with some 2024+ and some pre-2024 cases.
  - Cannot tell whether "previously reported" refers to this proband or a relative.
  - No admission dates anywhere AND PMC pub-date >= 2024-01-01 — default to PASS not UNCERTAIN,
    we're testing 'is this from the 2024+ publication window', not 'when did the patient present'.

Output strict JSON ONLY:
{"decision": "pass" | "fail" | "uncertain",
 "reason": "<one-sentence explanation>",
 "evidence_quote": "<≤200 char verbatim quote from text supporting your decision, or empty>"}
"""


def parse_pmc(pmc_id: str) -> tuple[str, str]:
    """Return (pub_date_iso, excerpt_text). excerpt is abstract+intro+first case section."""
    path = XML_CACHE / f"PMC{pmc_id}.xml.gz"
    if not path.exists():
        return "", ""
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        txt = f.read()

    # pub date
    pub_date = ""
    for pub_type in ("epub", "epub-ppub", "electronic", "pmc-release", "ppub", "collection"):
        m = re.search(
            r'<pub-date[^>]*pub-type="' + pub_type + r'"[^>]*>(.*?)</pub-date>',
            txt, re.DOTALL,
        )
        if m:
            blk = m.group(1)
            y = re.search(r"<year>(\d{4})</year>", blk)
            mo = re.search(r"<month>(\d{1,2})</month>", blk)
            d = re.search(r"<day>(\d{1,2})</day>", blk)
            if y:
                pub_date = y.group(1)
                if mo:
                    pub_date += f"-{int(mo.group(1)):02d}"
                    if d:
                        pub_date += f"-{int(d.group(1)):02d}"
                break

    title = ""
    tm = re.search(r"<article-title[^>]*>(.*?)</article-title>", txt, re.DOTALL)
    if tm:
        title = re.sub(r"<[^>]+>", " ", tm.group(1))
        title = re.sub(r"\s+", " ", title).strip()

    abstract = ""
    am = re.search(r"<abstract[^>]*>(.*?)</abstract>", txt, re.DOTALL)
    if am:
        abstract = re.sub(r"<[^>]+>", " ", am.group(1))
        abstract = re.sub(r"\s+", " ", abstract).strip()

    body = ""
    bm = re.search(r"<body[^>]*>(.*?)</body>", txt, re.DOTALL)
    if bm:
        body = re.sub(r"<[^>]+>", " ", bm.group(1))
        body = re.sub(r"\s+", " ", body).strip()

    # Build cutoff-relevant excerpt: title + abstract + first 3000 char of body
    # (intro/methods/first-case usually appear early)
    excerpt_parts = []
    if title:
        excerpt_parts.append(f"TITLE: {title}")
    if abstract:
        excerpt_parts.append(f"ABSTRACT: {abstract[:1500]}")
    if body:
        excerpt_parts.append(f"BODY (first 3000 char): {body[:3000]}")

    # Plus: tail scan for explicit "first reported in YYYY" / "previously reported"
    # phrases anywhere in body
    flags = []
    for pat in [
        r"previously reported in [^.]{0,80}",
        r"first (?:described|reported) in \d{4}[^.]{0,80}",
        r"case series of[^.]{0,80}",
        r"retrospective(?:ly)?[^.]{0,80}",
        r"follow-up of[^.]{0,80}",
        r"(?:patients|cases) (?:diagnosed|admitted|treated) (?:between|from) (?:19|20)\d\d (?:and|to|-) (?:19|20)\d\d",
    ]:
        for m in re.finditer(pat, body, re.IGNORECASE):
            snip = m.group(0)
            if snip not in flags:
                flags.append(snip)
            if len(flags) >= 6:
                break
        if len(flags) >= 6:
            break
    if flags:
        excerpt_parts.append("FLAGGED PHRASES IN BODY: " + " | ".join(flags))

    return pub_date, "\n\n".join(excerpt_parts)


def classify(pmc_id: str) -> dict:
    pub_date, excerpt = parse_pmc(pmc_id)
    if not excerpt:
        return {
            "pmc_id": pmc_id,
            "decision": "uncertain",
            "reason": "No cached PMC XML found.",
            "evidence_quote": "",
            "pmc_pub_date": pub_date,
            "model": MODEL,
        }

    user_msg = (
        f"PMC publication date (machine-extracted): {pub_date or 'unknown'}\n\n"
        f"--- Article excerpt ---\n{excerpt}\n--- end ---\n\n"
        "Decide: pass / fail / uncertain. Return JSON only."
    )

    try:
        resp = openrouter_chat(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=400,
            temperature=0.0,
        )
        content = resp["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return {
            "pmc_id": pmc_id,
            "decision": "uncertain",
            "reason": f"LLM call failed: {e}",
            "evidence_quote": "",
            "pmc_pub_date": pub_date,
            "model": MODEL,
        }

    # extract JSON (sometimes wrapped in ```json)
    m = re.search(r"\{.*\}", content, re.DOTALL)
    if not m:
        return {
            "pmc_id": pmc_id,
            "decision": "uncertain",
            "reason": f"Non-JSON output: {content[:200]}",
            "evidence_quote": "",
            "pmc_pub_date": pub_date,
            "model": MODEL,
        }
    try:
        parsed = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return {
            "pmc_id": pmc_id,
            "decision": "uncertain",
            "reason": f"JSON parse failed: {e}; raw: {content[:200]}",
            "evidence_quote": "",
            "pmc_pub_date": pub_date,
            "model": MODEL,
        }

    dec = (parsed.get("decision") or "").strip().lower()
    if dec not in ("pass", "fail", "uncertain"):
        dec = "uncertain"
    return {
        "pmc_id": pmc_id,
        "decision": dec,
        "reason": (parsed.get("reason") or "")[:500],
        "evidence_quote": (parsed.get("evidence_quote") or "")[:300],
        "pmc_pub_date": pub_date,
        "model": MODEL,
    }


def load_pmc_ids():
    with open(OLD_HANDOFF / "review_template.csv") as f:
        return [r["pmc_id"] for r in csv.DictReader(f)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=0, help="limit (0=all)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--resume", action="store_true", help="skip pmc_ids already in output")
    args = ap.parse_args()

    pmc_ids = load_pmc_ids()
    if args.n:
        pmc_ids = pmc_ids[: args.n]

    done = set()
    if args.resume and OUT_PATH.exists():
        with open(OUT_PATH) as f:
            for line in f:
                try:
                    done.add(json.loads(line)["pmc_id"])
                except Exception:
                    pass
        print(f"Resume: {len(done)} already done")

    todo = [p for p in pmc_ids if p not in done]
    print(f"Classify {len(todo)} cases with {args.workers} workers")

    t0 = time.time()
    n_pass = n_fail = n_unc = 0
    with open(OUT_PATH, "a") as fout, ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(classify, p): p for p in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            res = fut.result()
            fout.write(json.dumps(res) + "\n")
            fout.flush()
            if res["decision"] == "pass":
                n_pass += 1
            elif res["decision"] == "fail":
                n_fail += 1
            else:
                n_unc += 1
            if i <= 10 or i % 25 == 0:
                print(
                    f"  [{i}/{len(todo)}] PMC{res['pmc_id']} "
                    f"({res['pmc_pub_date']}) -> {res['decision']}: {res['reason'][:80]}"
                )
    dt = time.time() - t0
    print(f"\nDone in {dt:.0f}s.  pass={n_pass}  fail={n_fail}  uncertain={n_unc}")


if __name__ == "__main__":
    main()
