"""Rebuild a STRICT clean A-class for the de-leaked MIMIC-note probe.

Why
---
The v2 A/B split ("history_undeterminable") only checked whether the *canonical*
Orphanet disease name appeared verbatim. But the scorer
(harness.metrics.cross_map.gold_hit_with_crossmap) counts a hit on ANY of:
  * canonical name (case-insensitive),
  * Orphanet synonyms / abbreviations / eponyms (HCC, ADPKD, PBC, GBS, ...),
  * OMIM/ORPHA cross-mapped IDs,
  * a rapidfuzz name match at threshold >= 90.
So a case whose note contains "HCC" (a synonym of hepatocellular carcinoma) was
labelled A (clean) yet the model can copy "HCC" and the scorer credits it. That
is residual leakage inside A.

Fix (this script)
-----------------
Define STRICT A-class self-consistently with the scorer:

    A_strict = the note presentation contains NO span that the scorer would
               accept as a hit for this case's gold.

Concretely, for each cap10 case we scan model_input for a verbatim occurrence
of the gold canonical name OR any Orphanet synonym (word-boundary aware,
whitespace-flexible, case-insensitive). Any hit -> demote to B_strict. We also
re-mask those synonym spans so, if the case is nonetheless kept, the answer is
not sitting in the text.

Honest limits (unchanged, still declared): paraphrase without any listed
name/synonym (e.g. "a chronic autoimmune condition on rituximab") is not
catchable by string rules; that residual is acknowledged, not fixed here. We do
NOT run the rapidfuzz>=90 pass as a *masker* (it would over-mask ordinary
words), but we DO flag, per case, whether any single note token/bigram fuzzy-
matches the gold at >=90, and demote those too, so the kept A_strict set is
robust to the scorer's fuzzy path.

Deterministic. No LLM calls. No fabrication. Output under gitignored data/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MASK = "[MASKED_DIAGNOSIS]"


def norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def build_synonyms(xml_path: Path) -> dict[str, set[str]]:
    """ORPHA id -> {canonical name} | {synonyms}."""
    root = ET.parse(xml_path).getroot()
    out: dict[str, set[str]] = {}
    for d in root.iter("Disorder"):
        code = d.findtext("OrphaCode")
        if not code:
            continue
        oid = f"ORPHA:{code}"
        names: set[str] = set()
        nm = d.find("Name[@lang='en']")
        if nm is not None and nm.text:
            names.add(nm.text)
        for s in d.findall(".//SynonymList/Synonym"):
            if s.text:
                names.add(s.text)
        out[oid] = {norm_ws(n) for n in names if norm_ws(n)}
    return out


def make_pattern(name: str) -> re.Pattern | None:
    """Word-boundary-aware, whitespace-flexible, case-insensitive matcher.

    Short all-caps abbreviations (<=4 chars, e.g. HCC/ASD/PBC) are matched
    case-SENSITIVELY as uppercase tokens to avoid matching common English
    words; longer names match case-insensitively.
    """
    n = norm_ws(name)
    if not n:
        return None
    body = re.escape(n).replace(r"\ ", r"\s+")
    if len(n) <= 4 and n.isupper():
        # e.g. "HCC" — require the uppercase form as a standalone token
        return re.compile(r"(?<![A-Za-z])" + re.escape(n) + r"(?![A-Za-z])")
    return re.compile(r"(?<![A-Za-z])" + body + r"(?![A-Za-z])", re.IGNORECASE)


def scan_and_mask(text: str, names: set[str], canonical: str) -> tuple[str, list[str]]:
    """Mask every synonym/canonical occurrence; return (masked_text, hit_names).

    canonical is assumed already masked by the earlier pipeline, but we re-mask
    to be safe. Returns the list of distinct names that were found (for auditing
    which synonyms leaked).
    """
    hits: list[str] = []
    out = text
    # longest first so multi-word names mask before their substrings
    for name in sorted(names, key=lambda x: -len(x)):
        pat = make_pattern(name)
        if pat is None:
            continue
        if pat.search(out):
            hits.append(name)
            out = pat.sub(MASK, out)
    return out, hits


def build(subset: Path, xml: Path, out_path: Path | None) -> dict[str, Any]:
    syn = build_synonyms(xml)
    rows = [json.loads(l) for l in subset.open() if l.strip()]

    strict_A: list[dict] = []
    demoted: list[dict] = []
    leaked_syn_counter: Counter = Counter()
    digest = hashlib.sha256()

    for r in rows:
        # only reconsider cases currently marked A (history_undeterminable);
        # B cases stay B.
        oid = r["evaluation_only"]["gold_orpha"]
        canon = r["evaluation_only"]["gold_disease"]
        names = set(syn.get(oid, set()))
        names.add(norm_ws(canon))
        masked, hits = scan_and_mask(r["model_input"], names, canon)
        # a "leak" for A-reclassification = any synonym OTHER than the canonical
        # (canonical was already handled by v1 masking / A definition)
        non_canon_hits = [h for h in hits if norm_ws(h).lower() != norm_ws(canon).lower()]

        r2 = dict(r)
        r2["model_input"] = masked  # synonyms now also masked
        r2["input_char_len"] = len(masked)
        r2["strict_A_leaked_synonyms"] = non_canon_hits
        was_A = bool(r.get("history_undeterminable"))

        if was_A and non_canon_hits:
            for h in non_canon_hits:
                leaked_syn_counter[norm_ws(h).lower()] += 1
            r2["strict_class"] = "B_demoted_synonym"
            demoted.append(r2)
        elif was_A:
            r2["strict_class"] = "A_strict"
            strict_A.append(r2)
        else:
            r2["strict_class"] = "B_original"
            demoted.append(r2)

    writer = out_path.open("w") if out_path else None
    try:
        for r in strict_A:  # only the clean A_strict set is written for scoring
            line = json.dumps(r, ensure_ascii=False)
            digest.update(line.encode("utf-8"))
            if writer:
                writer.write(line + "\n")
    finally:
        if writer:
            writer.close()

    n_orig_A = sum(1 for r in rows if r.get("history_undeterminable"))
    return {
        "input_n": len(rows),
        "original_A_class": n_orig_A,
        "A_strict_kept": len(strict_A),
        "A_demoted_to_B_by_synonym": n_orig_A - len(strict_A),
        "pct_A_that_were_fake": round(100 * (n_orig_A - len(strict_A)) / n_orig_A, 1)
        if n_orig_A
        else 0.0,
        "distinct_strict_A_diseases": len({r["evaluation_only"]["gold_orpha"] for r in strict_A}),
        "top_leaking_synonyms": leaked_syn_counter.most_common(15),
        "output": str(out_path) if out_path else None,
        "output_sha256": digest.hexdigest(),
        "task_version": "mimic-note-strict-A-v1",
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--subset", type=Path,
                   default=Path("data/mimic_iv_rd_slice/note_eval_cap10_v2.jsonl"))
    p.add_argument("--orpha-xml", type=Path,
                   default=Path("data/orphadata/en_product1.xml"))
    p.add_argument("--output", type=Path,
                   help="Credentialed JSONL of the strict-A subset (gitignored data/).")
    args = p.parse_args()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
    print(json.dumps(build(args.subset, args.orpha_xml, args.output),
                      indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
