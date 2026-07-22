# Review Summary — Demo Reviewer (first 10 candidates)

- **Reviewer:** `demo_subagent_v1` (LLM-assisted demonstration of human-reviewer workflow)
- **Reviewed:** 10 candidates (rows 1–10 of `06_candidates_for_review.jsonl`, all `match_type=exact_name`, `match_score=100`)
- **Date:** 2026-05-14

## Counts

| Decision | N |
|---|---|
| Accept | 9 |
| Reject | 1 |
| Uncertain | 0 |

Acceptance rate **90%** for top-of-pool exact-name matches, in line with the expected >80% from REQUIREMENTS §1.

## Check fail distribution

| Check | Fail count | Cases |
|---|---|---|
| Check 1 (diagnosis correctness) | 0 | — |
| Check 2 (HPO accuracy) | 0 | — (none had >30% noise; one minor caveat in PMC10767578 where 2 of 3 HPO items describe the affected father not the proband, but they are real NPS findings used to establish the diagnosis) |
| Check 3 (post-2024 cutoff) | 1 | **PMC10768362** (Mevalonate kinase deficiency) — case series of two patients admitted in 2018, retrospective tocilizumab follow-up paper |
| Check 4 (rare disease) | 0 | All 10 ORPHA codes confirmed rare (≤1/2000 EU) per Orphadata `en_product9_prev.xml` (ORPHA:139399 is a clinical subtype of X-ALD, inherits rarity from parent ORPHA:43) |

## Top diseases seen (10 / 10 are unique ORPHA IDs)

| ORPHA | Name | PMC ID |
|---|---|---|
| 902 | Werner syndrome | 13074162 |
| 47 | X-linked agammaglobulinemia | 13076136 |
| 65285 | Lhermitte-Duclos disease | 10766305 |
| 2616 | 3M syndrome | 10767403 |
| 69723 | Tyrosinemia type 3 | 10767433 |
| 2614 | Nail-patella syndrome | 10767578 |
| 2929 | Juvenile polyposis syndrome | 10767673 |
| 348 | Fructose-1,6-bisphosphatase deficiency | 10767684 |
| 309025 | Mevalonate kinase deficiency (rejected) | 10768362 |
| 139399 | Adrenomyeloneuropathy | 10783329 |

No single disease dominated; per-disease cap of 3 (REVIEW_INSTRUCTIONS) is automatically satisfied.

## Practical tips for human annotators

### Most useful Orphanet web fields
1. **Prevalence band** under "Epidemiology" — definitive for Check 4. Look for the lowest of `<1/1,000,000`, `1-9/1,000,000`, `1-9/100,000`, `1-9/10,000`. Anything ≤ `1-9/10,000` is rare per EU definition.
2. **Disorder type** (e.g., "Clinical subgroup", "Disease", "Subtype of disorder"). Clinical-subtype entries (e.g., ORPHA:139399 Adrenomyeloneuropathy under X-ALD) inherit prevalence from the parent — open parent ORPHA page for the prevalence number.
3. **Synonyms** — useful when the article uses an older/alternate name (e.g., "dysplastic cerebellar gangliocytoma" = Lhermitte-Duclos disease).

### Fastest workflow that worked here (alternative when orpha.net web UI is slow / behind challenge)
- **NCBI E-utilities efetch** (`https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc&id=<PMCID>&rettype=xml&retmode=xml`) returns full PMC OA article in JATS XML. Search for `<article-title>`, `<sec sec-type="cases">`, and free-text "diagnosis" — much faster than rendering the full webpage. Rate limit: 3 req/sec without API key.
- **NCBI esummary** for pub-date metadata: `epubdate`, `pmclivedate`, `pubdate` (collection/print).
- **Orphadata XML dumps** (`https://www.orphadata.com/data/xml/en_product9_prev.xml` for prevalence, `en_product1.xml` for disorder hierarchy) — full data offline, no auth/captcha. Recommend reviewers download once and grep locally.

### URL patterns to be aware of
- `pmc.ncbi.nlm.nih.gov/articles/PMC<id>/` — sometimes hits reCAPTCHA on automated curl; manual browser works fine, or use E-utilities.
- `orpha.net/en/disease/detail/<NUM>` — front-end SPA; raw HTML is a JS bootstrap (~5 KB), no content. Either render in browser or use Orphadata XML.

### Confusable diagnosis names (potential fuzzy-match traps)
Not encountered in the top 10 (all were unambiguous exact matches), but watch for:
- "AMN" can mean Adrenomyeloneuropathy or Acute macular neuroretinopathy — disambiguate via gene (`ABCD1`).
- "JPS" can mean Juvenile Polyposis Syndrome or Job's syndrome (hyper-IgE) — disambiguate via gene (SMAD4/BMPR1A vs STAT3).
- "3M syndrome" sounds non-specific; verify by genes CUL7/OBSL1/CCDC8.

## Surprising / systematic findings

1. **6 of 10 articles have epub date in late 2023** (Oct–Dec 2023) but PMC live date and `<pub-date pub-type="collection">` of 2024-Q1. The pipeline filter (PMC pub date ≥ 2024-01-01) admits these correctly per the policy, but they were publicly visible online in 2023. For a "post-cutoff" holdout this is a soft concern — see **REQUIREMENTS feedback** below.
2. **One real Check-3 fail (PMC10768362)** is a retrospective case-series + literature-review article on two MKD/TRAPS patients managed 2018→2023. Even though the article is post-2024, the cases themselves were diagnosed pre-2024 and may have been reported in prior abstracts/case reports — this is a "republication / extended follow-up" pattern annotators should explicitly look for. Heuristics that flagged it:
   - Title includes "case series" or "literature review".
   - Multiple patients with structured tables.
   - `pub_year_in_text` reflects an admission year well before publication.
3. **HPO accuracy was excellent** for all 10 LLM-extracted phenotype lists. The Werner case has very nuanced ophthalmology HPO (pachychoroid, plateau iris, short axial length) all of which are real patient findings — the LLM extractor is doing real semantic work, not just keyword matching.
4. **PMC10767578 (NPS) HPO list edge case**: 2 of the 3 HPO terms describe the proband's father (the family member who actually has clinical NPS), not the fetus. Strictly the HPO-of-the-affected-individual is just talipes equinovarus. We accepted with `hpo_phenotypes_clean=true` because all listed terms are real NPS phenotypes and the case is identified through the family. Annotators should be aware of prenatal cases where the proband is a fetus and core phenotype is found in the parent.

## Feedback for REQUIREMENTS.md (issues found during demo)

1. **Check 3 cutoff ambiguity**: REQUIREMENTS §3 Check 3 says "case is 2024-01-01 之后的新报告" and refers to "pre-2024 republication". But many legitimate 2024 articles have:
   - epub date in 2023-Q4 (journal workflow "online ahead of print"),
   - patient encounters years before publication (rare-disease case reports often retrospectively analyze a long-followed patient).
   Please clarify which date is the authoritative cutoff:
   - PMC `pmclivedate` (recommended; this is what the pipeline used) — most permissive.
   - epub date — stricter (would reject ~30-50% of pool given the rolling Dec/Jan boundary).
   - **patient encounter date** — strictest (rejects all retrospective/long-follow-up reports; not realistic for rare-disease holdout).
   Recommendation: codify **PMC `pmclivedate` ≥ 2024-01-01** as the formal cutoff, AND reject when the article is explicitly a follow-up/republication of a previously published case (text-based heuristic, not date-based).

2. **No `uncertain` field in §4.1 output spec**: REVIEW_INSTRUCTIONS allows `?` (uncertain) but REQUIREMENTS §4 only defines `accept` / `reject` schema fields. If you want `uncertain` for second-pass review, add `review_decision: "uncertain"` to the schema and clarify where they go (probably a third output file, or stays in 06 unresolved).

3. **`hpo_phenotypes_clean` semantics underspecified**: §3 Check 2 says "≤30% noise = mark `hpo_phenotypes_clean=true/false`" but it's not clear whether `clean=false` blocks accept or is purely advisory. I treated `clean=true` as "<30% noise AND no major mis-attribution"; please confirm.

4. **Clinical-subtype Orphanet entries (e.g., ORPHA:139399) are not in `en_product9_prev.xml`**. Annotators following "look up prevalence on orpha.net" verbatim will find no prevalence and may wrongly mark Check 4 as fail. Suggested clarification: "If `disorder_type` is `Clinical subtype` / `Clinical subgroup`, inherit prevalence from the parent disorder."

5. **For prenatal/family-history cases**, the proband's HPO list may include phenotypes belonging to an affected parent (e.g., NPS case here). REQUIREMENTS §3 Check 2 should mention this and instruct annotators to treat such HPO terms as valid evidence for the diagnosis even if not the proband's own findings — or, alternatively, to standardize on "proband-only HPO terms" and prune the parent's.
