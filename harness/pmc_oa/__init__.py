"""PMC Open Access cutoff-after holdout pipeline (Stream D).

End-to-end:
1. `search.search_candidates(...)` — E-utils esearch for PMC case reports
   matching rare-disease MeSH terms, published after a cutoff date.
2. `fetch.fetch_xml(...)` — E-utils efetch each candidate's full JATS XML.
3. `extract.llm_extract(...)` — LLM extraction (Gemini 3 Flash via OpenRouter)
   of diagnosis / HPO / demographics / pub_date sanity check.
4. `orphanet.map_to_orphanet(...)` — string-match extracted diagnosis to
   Orphanet IDs via the disease index.
5. (Manual) — human-in-the-loop verification of ~200 final cases.

Output: a JSONL file of canonical_case-ready records in
`data/pmc_oa_holdout/candidates.jsonl`, ready for Step 5 review.
"""

from harness.pmc_oa.search import search_candidates
from harness.pmc_oa.fetch import fetch_xml

__all__ = ["search_candidates", "fetch_xml"]
