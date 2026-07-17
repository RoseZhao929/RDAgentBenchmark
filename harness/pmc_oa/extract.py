"""Step 3: LLM extraction of structured fields from PMC OA JATS XML.

For each XML, ask Gemini 3 Flash to extract:
- final_diagnosis (disease name)
- diagnosis_certainty (definitive / suspected / differential)
- hpo_phenotypes (list of clinical features in natural language)
- demographics (age, sex)
- has_family_history (bool)
- pub_date_in_text (for cutoff verification — paper says X, but does text reference earlier reports?)
- raw_case_excerpt (the verbatim case description for downstream use)

This is meant to run on 2,398 PMC OA case reports → produce structured JSON
ready for Orphanet mapping (Step 4) and manual review (Step 5).
"""

from __future__ import annotations

import gzip
import json
import os
import re
import time
from pathlib import Path
from typing import Iterable, Optional
from xml.etree import ElementTree as ET

import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = os.environ.get("CANARY_BACKBONE_MODEL", "google/gemini-3-flash-preview")

EXTRACT_PROMPT = """\
You are extracting structured fields from a published rare-disease case report
for a research benchmark. Return ONLY valid JSON (no prose, no markdown fences).

Fields to extract:
- final_diagnosis: the final/established diagnosis as stated in the paper
                   (string). If multiple are listed, return only the
                   definitively confirmed one. If only "suspected" or
                   differential, set to null.
- diagnosis_certainty: one of "definitive", "suspected", "differential", "none"
- hpo_phenotypes: a list of short English phrases for clinical features
                   present in the patient. Aim for terms that would map to HPO
                   (e.g., "intellectual disability", "macrocephaly",
                   "elevated serum creatine kinase").
- age_at_presentation_years: numeric (float) or null
- sex: "male", "female", or null
- has_family_history: boolean — does the report mention affected relatives,
                       pedigree, or trio analysis?
- pub_year_in_text: integer year that the paper says the case was managed
                     (NOT the publication date — the text often says "in 2019
                     a 5yo presented"). If unspecified, null.
- case_excerpt: a 500-1500 char verbatim excerpt of the case description
                 (the clinical narrative, not figures/tables).

Case report XML follows:

---
{xml_text}
---

Output strict JSON only.
"""


def _read_xml(xml_path: Path) -> str:
    if str(xml_path).endswith(".gz"):
        with gzip.open(xml_path, "rt", errors="replace") as f:
            return f.read()
    return xml_path.read_text(errors="replace")


def _xml_to_text(xml_str: str, max_chars: int = 20000) -> str:
    """Strip JATS XML to text, capped at max_chars."""
    try:
        root = ET.fromstring(xml_str)
        text = "".join(root.itertext())
    except ET.ParseError:
        text = re.sub(r"<[^>]+>", " ", xml_str)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def _strip_json_fences(s: str) -> str:
    """LLMs sometimes wrap JSON in markdown fences despite instructions."""
    s = s.strip()
    if s.startswith("```"):
        # remove opening fence
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()


def extract_one(xml_text: str, model: str = DEFAULT_MODEL, api_key: Optional[str] = None) -> dict:
    """Call OpenRouter to extract structured fields from one case report XML."""
    key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY missing")

    prompt = EXTRACT_PROMPT.format(xml_text=_xml_to_text(xml_text))
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 2000,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    r = requests.post(OPENROUTER_URL, headers=headers, json=body, timeout=120)
    r.raise_for_status()
    resp = r.json()

    raw = resp["choices"][0]["message"]["content"]
    parsed = json.loads(_strip_json_fences(raw))

    # attach metadata
    usage = resp.get("usage", {})
    parsed["_meta"] = {
        "model": resp.get("model", model),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "id": resp.get("id"),
    }
    return parsed


def batch_extract_from_dir(
    xml_dir: Path | str,
    out_path: Path | str,
    pmc_ids: Optional[Iterable[str]] = None,
    model: str = DEFAULT_MODEL,
    limit: Optional[int] = None,
    skip_existing: bool = True,
) -> dict[str, int]:
    """Run LLM extraction on every PMC XML in xml_dir, append JSONL to out_path.

    If pmc_ids given, only process those IDs. Otherwise process all .xml.gz / .xml.
    """
    xml_root = Path(xml_dir)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # detect already-processed PMC IDs to support resume
    done: set[str] = set()
    if skip_existing and out_path.exists():
        with out_path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    done.add(rec.get("pmc_id", ""))
                except json.JSONDecodeError:
                    pass

    stats = {"ok": 0, "fail": 0, "skipped": 0}

    if pmc_ids is not None:
        files = [xml_root / f"PMC{pid}.xml.gz" for pid in pmc_ids]
    else:
        files = sorted(list(xml_root.glob("*.xml.gz")) + list(xml_root.glob("*.xml")))

    with out_path.open("a") as out_f:
        for fp in files:
            if not fp.exists():
                continue
            pmc_id = fp.stem.replace(".xml", "").lstrip("PMC")
            if pmc_id in done:
                stats["skipped"] += 1
                continue
            try:
                xml_text = _read_xml(fp)
                rec = extract_one(xml_text, model=model)
                rec["pmc_id"] = pmc_id
                out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                out_f.flush()
                stats["ok"] += 1
            except Exception as e:
                stats["fail"] += 1
                out_f.write(json.dumps({"pmc_id": pmc_id, "_error": str(e)}) + "\n")
                out_f.flush()

            if (stats["ok"] + stats["fail"]) >= (limit or float("inf")):
                break

            if (stats["ok"] + stats["fail"]) % 50 == 0:
                print(f"  [extract] ok={stats['ok']} fail={stats['fail']} "
                      f"skipped={stats['skipped']}", flush=True)

            time.sleep(0.1)   # gentle rate-limit-friendly

    return stats


__all__ = ["extract_one", "batch_extract_from_dir"]
