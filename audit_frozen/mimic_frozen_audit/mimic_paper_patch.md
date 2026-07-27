# MIMIC Paper Patch — sourced ONLY from this frozen audit

Frozen commit `9babd833618936b6b29942baba130638e212921d`. Every MIMIC number below is
either UNVERIFIABLE or comes from mutually-inconsistent legacy aggregates. Default
action: do not state any MIMIC per-case metric as a confirmed result.

## Abstract (`paper_build/acl/tex/abstract.tex` line ~10)

Current: "... MIMIC-IV rare-disease slice *n*=956 ..."

- **DELETE / MODIFY.** n=956 is unverifiable from frozen evidence (cohort file absent).
  Do not list MIMIC alongside verified layers as if it carries frozen results.
- MODIFY option (if the resource must be named): "... and a self-built MIMIC-IV-3.1
  rare-disease cohort (ICD-Orphanet mapped; released as a dataset resource, not part of
  the frozen result matrix)." Do NOT assert n=956 as an evaluated N.

## Benchmark Design (`4_benchmark_design.tex` lines 28-29, 40, 52; `5_2_5_4_setup.tex` line 114)

- **KEEP (as construction description, softened):** the pipeline — MIMIC-IV-3.1,
  ICD-10 → Orphadata cross-reference, drop "NON RARE IN EUROPE", Exact-only, cap
  5/disease. This is documented in the ingest/filter scripts.
- **MODIFY:** the "956 cases" figure — mark as "target cohort ~956/239 diseases per our
  build log; cohort file not included in the frozen release" OR drop the exact number.
- **DELETE / MODIFY the "Real EHR Noise" and "free-text EHR" framing.** Frozen evidence
  (round1_worklog + pilot script) shows there are NO discharge notes; inputs are
  **synthetic vignettes generated from ICD long titles**. Replace with: "a structured
  ICD-derived rare-disease identification slice (synthetic vignettes from ICD titles; no
  free-text discharge notes in this version)."
- **KEEP:** the PhysioNet DUA note (line 80c) — accurate and important.
- The specific counts "2,173 ICD cross-refs" and "88,664 NON RARE filtered" are
  unverifiable from frozen artifacts → MODIFY to "approximately" or drop.

## Experimental Setup (`5_2_5_4_setup.tex`, OSF draft)

- **MODIFY:** remove MIMIC from the list of layers that were "evaluated at full N".
  Frozen evidence shows most MIMIC cells did NOT reach 956 attempted, and none are in
  `frozen_main_manifest.csv`.

## Results (`6_main_results.tex` MIMIC column [956]; `7_2_7_3_7_4_analysis.tex`; `J_appendix_cost.tex`)

- **DELETE MIMIC from the main results heatmap** (all `[956]` cells). Not backed by any
  frozen receipt; the two surviving aggregates disagree per-cell.
- **DELETE / DOWNGRADE** the analysis claims "mdagents best on MIMIC (0.38)", "MIMIC
  0.35/0.32", "−11 to −16 pp on MIMIC", and the §7 "0.39 DDx / 0.56 pilot" numbers —
  all unverifiable; no receipts.
- **DELETE MIMIC rows from the cost table** (`J_appendix_cost.tex`) — costs derive from
  the same absent receipts.
- If any MIMIC result is retained, it must be an **appendix pilot** explicitly labeled
  "legacy run; not reproducible from the released frozen set; cohort/receipts not
  redistributable (PhysioNet DUA)."

## One-line summary for authors

Treat MIMIC as a described-but-unreleased dataset resource, not a frozen result layer.
Strip MIMIC numbers from Abstract, main heatmap, capability radar, cost table, and the
§7 analysis until receipts + gold + cohort are restored and re-scored under the same
audit rules as the other four layers.
