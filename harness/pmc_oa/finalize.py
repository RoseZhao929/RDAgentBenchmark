"""Step 4.5: Dedup + filter + rank → final candidate pool for human review.

Reads:
- `data/pmc_oa_holdout/04_extracted.jsonl` (LLM extracted)
- `data/pmc_oa_holdout/05_orphanet_mapped.jsonl` (Orphanet mapped)

Writes:
- `data/pmc_oa_holdout/06_candidates_for_review.jsonl` — clean candidate list
- `data/pmc_oa_holdout/REVIEW_INSTRUCTIONS.md` — human reviewer guide

Filtering policy (conservative, prefers precision over recall — humans want
≤200 high-quality cases not ~3000 noise):
- Definitive diagnosis only (filter on 04's `diagnosis_certainty`)
- Successfully Orphanet-mapped (orpha_id != null)
- Match type ∈ {exact_name, exact_synonym} OR (fuzzy AND score >= 95)
- Deduplicated by PMC ID (keep first / highest-score occurrence)

Ranking (top → bottom for review):
1. exact_name matches (score=100) first
2. then exact_synonym
3. then fuzzy ≥ 95, sorted by score desc
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Optional

PMC_HOLDOUT = Path("/Users/yutianzhao/Desktop/RDAgentBenchmark/data/pmc_oa_holdout")


def finalize_candidates(
    extracted_path: Path = PMC_HOLDOUT / "04_extracted.jsonl",
    mapped_path: Path = PMC_HOLDOUT / "05_orphanet_mapped.jsonl",
    out_path: Path = PMC_HOLDOUT / "06_candidates_for_review.jsonl",
    fuzzy_threshold: int = 95,
) -> dict[str, int]:
    """Produce the clean candidate pool."""

    # 1. Load extracted JSONL → {pmc_id: list of records (may dupe)}
    extracted_by_pmc: dict[str, list[dict]] = defaultdict(list)
    n_lines_04 = 0
    with extracted_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            n_lines_04 += 1
            try:
                rec = json.loads(line)
                pid = rec.get("pmc_id")
                if pid:
                    extracted_by_pmc[pid].append(rec)
            except json.JSONDecodeError:
                continue

    # 2. Load orphanet mapped JSONL → {pmc_id: best mapping}
    mapped_by_pmc: dict[str, dict] = {}
    n_lines_05 = 0
    with mapped_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            n_lines_05 += 1
            try:
                rec = json.loads(line)
                pid = rec.get("pmc_id")
                if not pid:
                    continue
                # Keep highest-score per PMC ID (dedup)
                existing = mapped_by_pmc.get(pid)
                if existing is None or rec.get("score", 0) > existing.get("score", 0):
                    mapped_by_pmc[pid] = rec
            except json.JSONDecodeError:
                continue

    stats = {
        "total_extracted_lines": n_lines_04,
        "unique_pmc_in_04": len(extracted_by_pmc),
        "total_mapped_lines": n_lines_05,
        "unique_pmc_in_05": len(mapped_by_pmc),
        "definitive_diagnosis": 0,
        "passed_filter": 0,
        "exact_name": 0,
        "exact_synonym": 0,
        "fuzzy_high": 0,
        "filtered_no_orpha": 0,
        "filtered_fuzzy_low": 0,
        "filtered_not_definitive": 0,
    }

    candidates = []
    for pmc_id, mapping in mapped_by_pmc.items():
        # pick best extracted record (definitive preferred)
        ex_recs = extracted_by_pmc.get(pmc_id, [])
        if not ex_recs:
            continue
        # Prefer definitive
        ex = next(
            (r for r in ex_recs if r.get("diagnosis_certainty") == "definitive"),
            ex_recs[0],
        )

        if ex.get("diagnosis_certainty") != "definitive":
            stats["filtered_not_definitive"] += 1
            continue
        stats["definitive_diagnosis"] += 1

        if not mapping.get("orpha_id"):
            stats["filtered_no_orpha"] += 1
            continue

        match_type = mapping.get("match_type", "")
        score = float(mapping.get("score", 0.0))

        if match_type == "exact_name":
            stats["exact_name"] += 1
        elif match_type == "exact_synonym":
            stats["exact_synonym"] += 1
        elif match_type == "fuzzy" and score >= fuzzy_threshold:
            stats["fuzzy_high"] += 1
        else:
            stats["filtered_fuzzy_low"] += 1
            continue

        stats["passed_filter"] += 1
        candidates.append({
            "pmc_id": pmc_id,
            "orpha_id": mapping["orpha_id"],
            "omim_ids": mapping.get("omim_ids", []),
            "matched_orpha_name": mapping.get("matched_name"),
            "extracted_diagnosis": mapping.get("extracted_diagnosis"),
            "match_type": match_type,
            "match_score": score,
            "age_at_presentation_years": ex.get("age_at_presentation_years"),
            "sex": ex.get("sex"),
            "has_family_history": ex.get("has_family_history"),
            "pub_year_in_text": ex.get("pub_year_in_text"),
            "hpo_phenotypes": ex.get("hpo_phenotypes", []),
            "case_excerpt": ex.get("case_excerpt", "")[:2000],   # cap length
            "pmc_url": f"https://pmc.ncbi.nlm.nih.gov/articles/PMC{pmc_id}/",
            # for reviewer:
            "top_candidates": mapping.get("top_candidates", [])[:3],
        })

    # Rank: exact_name > exact_synonym > fuzzy (score desc)
    match_rank = {"exact_name": 0, "exact_synonym": 1, "fuzzy": 2}
    candidates.sort(key=lambda c: (match_rank.get(c["match_type"], 99), -c["match_score"]))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        for c in candidates:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    stats["written"] = len(candidates)
    return stats


def write_review_instructions(stats: dict, out_path: Path = PMC_HOLDOUT / "REVIEW_INSTRUCTIONS.md"):
    md = f"""# PMC OA Holdout — Candidate Pool for Manual Review

Generated from `06_candidates_for_review.jsonl` (sorted top → bottom by match quality).

## Pool summary

- Total PMC OA case reports fetched (pub date ≥ 2024-01-01): {stats['unique_pmc_in_04']:,}
- Successfully LLM-extracted with definitive diagnosis: {stats['definitive_diagnosis']:,}
- Orphanet exact_name matches:    **{stats['exact_name']:,}**
- Orphanet exact_synonym matches: **{stats['exact_synonym']:,}**
- Orphanet fuzzy (score ≥95):     **{stats['fuzzy_high']:,}**
- Filtered out (no Orpha):        {stats['filtered_no_orpha']:,}
- Filtered out (fuzzy too low):   {stats['filtered_fuzzy_low']:,}
- Filtered out (not definitive):  {stats['filtered_not_definitive']:,}
- **Final candidate pool:** **{stats['written']:,}** cases

## Review goal: pick ~200 high-quality cases

For each candidate, verify in **5–10 min**:

1. **Diagnosis match correct?** Open `pmc_url`, find the section where the diagnosis is established. Confirm the LLM-extracted diagnosis matches the paper's final/established diagnosis (not a "suspected" / "differential includes" mention). The Orphanet ID match should genuinely represent the disease.

2. **HPO phenotypes accurate?** Skim the case description. The `hpo_phenotypes` list should be **clinical features actually present in the patient**, not features mentioned in passing for differential diagnoses. Drop any clearly irrelevant terms.

3. **Cutoff verification.** Confirm the case is **not** a republication of a pre-2024 case. Check:
   - `pub_year_in_text` if available
   - Search Google Scholar for the author + disease + earlier dates
   - Author's other papers in the same field

4. **Rare disease confirmation.** The Orphanet ID should map to a true rare disease (prevalence ≤ 1/2000 EU or equivalent). Use the Orphanet website (orpha.net) to confirm prevalence band.

5. **Mark verdict** in your review spreadsheet:
   - `✓ accept` — all 4 checks pass
   - `✗ reject` — any check fails
   - `?` — uncertain, flag for second reviewer

## Review tiers (suggested order)

1. **Tier 1 (top {stats['exact_name'] + stats['exact_synonym']:,}):** exact_name + exact_synonym matches. Highest confidence — work through these first.

2. **Tier 2 (next {stats['fuzzy_high']:,}):** fuzzy ≥95 matches. Likely correct but verify name match more carefully (false positives like "dengue shock syndrome" → "CK syndrome" can happen — both share "syndrome" / similar consonants).

## Target: ~200 accepted cases

Suggested split (to ensure disease diversity):
- ≤3 cases per Orphanet ID (avoid one disease dominating)
- Span across 14 body-system specialties (DeepRare taxonomy) if possible
- Include both adult and pediatric cases

## Output format

Save accepted cases (after review) to `data/pmc_oa_holdout/07_curated_holdout.jsonl`
with the same schema as `06_candidates_for_review.jsonl` plus a `review_decision`
field and `reviewer_notes`.

## Field reference (per JSONL line)

- `pmc_id`: PMC article ID (open `pmc_url` to read full text)
- `orpha_id` / `omim_ids`: gold diagnosis IDs (Orphanet + cross-mapped OMIM)
- `matched_orpha_name`: Orphanet canonical name
- `extracted_diagnosis`: what the LLM extracted from the paper (compare to gold)
- `match_type`: exact_name / exact_synonym / fuzzy
- `match_score`: 100 = exact, 95–99 = high-fuzzy
- `top_candidates`: alternate Orphanet IDs the LLM might have matched
- `hpo_phenotypes`: clinical features the LLM extracted
- `case_excerpt`: 500–1500 char verbatim excerpt of the case description
- `age_at_presentation_years`, `sex`, `has_family_history`, `pub_year_in_text`

## Versioning

- Source dataset: PMC OA (pub date ≥ 2024-01-01, MeSH = Rare Diseases ∨ Genetic Diseases Inborn ∨ "case reports" Publication Type ∨ "pubmed pmc open access"[sb])
- Pipeline: see `harness.pmc_oa.{{search,linking,fetch,extract,orphanet,finalize}}`
- Generated: 2026-05-14

**Reviewer must complete before OSF pre-registration unblinding the holdout
in main experiment.**
"""
    out_path.write_text(md)


if __name__ == "__main__":
    stats = finalize_candidates()
    write_review_instructions(stats)
    print("=== Finalization stats ===")
    for k, v in stats.items():
        print(f"  {k}: {v:,}" if isinstance(v, int) else f"  {k}: {v}")
    print(f"\nOutput: data/pmc_oa_holdout/06_candidates_for_review.jsonl")
    print(f"Instructions: data/pmc_oa_holdout/REVIEW_INSTRUCTIONS.md")
