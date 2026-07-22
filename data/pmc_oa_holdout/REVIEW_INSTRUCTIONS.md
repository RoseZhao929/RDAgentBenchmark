# PMC OA Holdout — Candidate Pool for Manual Review

Generated from `06_candidates_for_review.jsonl` (sorted top → bottom by match quality).

## Pool summary

- Total PMC OA case reports fetched (pub date ≥ 2024-01-01): 2,394
- Successfully LLM-extracted with definitive diagnosis: 2,343
- Orphanet exact_name matches:    **1,047**
- Orphanet exact_synonym matches: **0**
- Orphanet fuzzy (score ≥95):     **386**
- Filtered out (no Orpha):        302
- Filtered out (fuzzy too low):   608
- Filtered out (not definitive):  0
- **Final candidate pool:** **1,433** cases

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

1. **Tier 1 (top 1,047):** exact_name + exact_synonym matches. Highest confidence — work through these first.

2. **Tier 2 (next 386):** fuzzy ≥95 matches. Likely correct but verify name match more carefully (false positives like "dengue shock syndrome" → "CK syndrome" can happen — both share "syndrome" / similar consonants).

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
- Pipeline: see `harness.pmc_oa.{search,linking,fetch,extract,orphanet,finalize}`
- Generated: 2026-05-14

**Reviewer must complete before OSF pre-registration unblinding the holdout
in main experiment.**
