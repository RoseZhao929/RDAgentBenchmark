# MIMIC full-paper consistency audit

Status: protocol-only paper cleanup and full caption/integrity review completed
on this branch. Score-, receipt-, and leaderboard-dependent gates remain open
until replacement MIMIC model runs exist.

This file is the completion gate for any MIMIC-related paper change. A MIMIC
task is not finished when its code or result table is finished; it is finished
only after every source, generated artifact, figure, table, reference, and
release claim below has been reconciled and the PDF has been visually checked.

## Contradictions found on 2026-07-23

1. `paper_sections/6_main_results.md` and generated
   `paper_build/acl/tex/6_main_results.tex` say frozen MIMIC results are not
   recomputable, but the same Table 1 still contains old MIMIC point estimates
   and averages that include those estimates.
2. Several results paragraphs call MIMIC a “free-text layer,” although all 956
   cases have empty `free_text_vignette` and use ICD-title-derived synthetic
   text.
3. Dataset design and figure-generation code label MIMIC “Real EHR Noise,”
   without distinguishing real structured coding events from absent clinical
   notes.
4. The difficulty table calls the input a “structured note”; no note exists.
5. The cost appendix ranks systems using old MIMIC diagnosis scores even though
   the frozen main-result audit excludes MIMIC.
6. Ablation tables retain MIMIC deltas without stating that they come from the
   old ICD-title task.
7. Agent documentation disagrees on modality: MIMIC is variously described as
   free text, HPO-only, structured ICD, and a structured note.
8. Leaderboard builders and legacy plotting scripts still ingest stale
   `phase4a_summary.json` MIMIC cells.
9. The abstract and introduction list MIMIC alongside diagnostic datasets
   without stating that it is a secondary code-supervised structured-EHR task.
10. Reproducibility text points to a single 93-cell receipt while the frozen
    public release and local credentialed MIMIC evidence have different
    availability.

The branch resolves these contradictions by removing legacy MIMIC scores from
the diagnostic matrix, averages, cost analysis and public leaderboard; renaming
the task consistently; separating its reproducibility path; and rebuilding the
generated TeX, figures and PDF. Items below that require replacement model
scores remain intentionally open.

## Source-of-truth decision

After the replacement experiment:

- non-MIMIC differential-diagnosis results retain their frozen manifest;
- MIMIC receives a separate task name, receipt, table, and denominator;
- MIMIC is excluded from cross-dataset “Avg” values because its outcome and
  input construct differ;
- old ICD-title differential-diagnosis cells are archived and never silently
  mixed with the new structured-EHR experiment;
- Markdown paper sources are edited first and generated TeX is rebuilt from
  those sources, not hand-maintained as an independent truth.

## Text surfaces

- [x] `paper_sections/1_abstract.md`: describe MIMIC as secondary,
  code-supervised structured EHR; make no free-text claim.
- [x] `paper_sections/2_introduction.md`: update contribution and layer list.
- [x] `paper_sections/3_related_work.md`: preserve the distinction between
  MIMIC-RD, which uses notes, and this work's structured MIMIC cohort.
- [x] `paper_sections/4_benchmark_design.md`: replace “Real EHR Noise” with the
  final task name; specify tables, time window, exclusions, label source, and
  leakage audit.
- [x] `paper_sections/5_1_agent_fairness_matrix.md`: remove the incorrect claim
  that MIMIC is HPO-only.
- [x] `paper_sections/5_2_5_4_setup.md`: separate the diagnostic matrix from
  the MIMIC structured-EHR matrix.
- [x] `paper_sections/6_main_results.md`: old MIMIC cells are removed from
  diagnostic averages and attempted denominators are explicit; paired-arm
  results remain pending because replacement scores do not yet exist.
- [x] `paper_sections/7_2_7_3_7_4_analysis.md`: remove “structured note” and
  interpret the masking contrasts rather than old absolute R@1.
- [x] `paper_sections/8_ablations.md`: legacy MIMIC deltas are deleted; the
  replacement ablation is labelled pending.
- [x] `paper_sections/9_limitations.md`: add code-derived gold, absence of
  notes, event-timing, patient leakage, and DUA limitations; “ICU bias” alone is
  insufficient.
- [x] `paper_sections/10_conclusion.md`: ensure no free-text EHR generalization
  is attributed to MIMIC.
- [x] `paper_sections/A1_reproducibility_audit.md`: distinguish public frozen
  receipts from credentialed MIMIC regeneration.
- [x] `paper_sections/B_appendix_baseline_repro.md`: diagnostic reproduction
  excludes MIMIC and states that the replacement task requires its own
  task-versioned receipt; full scoring commands are in the dedicated protocol.
- [x] `paper_sections/J_appendix_cost.md`: regenerate from the new receipt or
  remove legacy MIMIC rows.
- [x] `paper_sections/OSF_preregistration_draft.md`: label the replacement
  analysis as amended/exploratory if it was not genuinely preregistered.

## Tables

- [x] Main Table 1 contains no stale MIMIC values or MIMIC-inclusive averages.
- [ ] A separate MIMIC table reports 24-hour structured input results.
- [ ] An appendix table reports title-selection, code-selection, and
  context-only paired results.
- [ ] Every MIMIC table states the unit (admission), N attempted, N valid,
  number of unique diseases, and whether intervals are patient-clustered.
- [ ] Error/timeout records count as incorrect in the primary denominator.
- [ ] Cost tables use the same model IDs, N, task version, and receipt hashes as
  the result table.
- [ ] Any prevalence or specialty table uses disease-macro results where
  appropriate and does not mix tasks.

## Figures and captions

- [x] `scripts/paper_schematics.py`: replace `Real EHR Noise`.
- [x] `scripts/paper_new_figures.py`: replace MIMIC labels and remove stale
  summary ingestion.
- [x] `scripts/paper_figures.py`: do not plot old MIMIC diagnosis cells.
- [x] `scripts/build_paper_pdf.py`: remove legacy MIMIC heatmap reference.
- [x] `paper_figures_tables.md`: update the design diagram and result-table
  specification.
- [x] Captions state “structured EHR” or “ICD leakage audit,” never “note” or
  “free text.”
- [x] Axes and legends do not place the MIMIC mapping task on the same numeric
  scale as differential diagnosis without an explicit task boundary.
- [x] Rebuild all figures and inspect final raster/vector output for stale
  labels embedded in images.

## Leaderboard, scripts, and receipts

- [ ] Archive or version `phase4a_summary.json` and
  `phase4a_with_ci.json`; never overwrite ambiguity in place.
- [x] `scripts/build_leaderboard.py` reads the frozen diagnostic manifest,
  excludes MIMIC and links a diagnostic-only downloadable manifest.
- [x] `scripts/phase4a_report_gen.py` cannot silently merge old and new MIMIC
  runs; it now loads only the three diagnostic datasets.
- [x] Ranking-stability, prevalence, contamination, and metric-ablation scripts
  either use the new task correctly or exclude MIMIC.
- [ ] Receipt schema includes task version, arm, input-window hours, attempted
  N, error N, mapping snapshot, cohort hash, and prompt hash.
- [x] The frozen diagnostic manifest drives the current paper table/figures,
  leaderboard and cost reporting; a future MIMIC receipt will remain separate.
- [x] Protected row-level data remains ignored and absent from this branch.

## References and claims

- [x] Verify the MIMIC-IV and MIMIC-IV-Note citations are distinct and correct.
- [x] Verify that MIMIC-RD's note-based design is not attributed to this cohort.
- [ ] Cite the ontology snapshot and ICD-to-Orphanet mapping source/version.
- [ ] Cite/report the PhysioNet credential and DUA requirements accurately.
- [x] Do not claim independent clinical gold: labels are code-derived.
- [x] Do not call the task prospective diagnosis unless the input cutoff and
  timestamp audit justify that term.
- [x] Do not claim clinical-note or HPO extraction performance.

## Final build gate

- [x] Run unit and data-integrity tests (4 MIMIC unit tests and 17 evaluator
  sanity checks pass).
- [ ] Regenerate receipts from row-level outputs.
- [x] Regenerate all Markdown-derived TeX and all figures.
- [x] Build the complete 41-page PDF and Overleaf bundle from the branch.
- [x] Search source and generated files for:
  `MIMIC`, `free-text`, `structured note`, `Real EHR`, `956`, old point
  estimates, and legacy receipt names.
- [x] Inspect every page containing a MIMIC mention, table, figure, or caption.
- [x] Check cross-references, table/figure numbering, bibliography resolution,
  page overflow, clipped legends, and stale auxiliary files.
- [x] Confirm the abstract, main table, results narrative, limitations,
  conclusion, appendix, leaderboard, and release statement all describe the
  same task and evidence version.

Only after every applicable item is checked may the MIMIC revision be called
complete.
