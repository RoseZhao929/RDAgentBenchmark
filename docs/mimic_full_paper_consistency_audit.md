# MIMIC full-paper consistency audit

Status: paper-wide legacy-claim cleanup completed on this branch; reopen when
replacement model receipts are added.

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

- [ ] `paper_sections/1_abstract.md`: describe MIMIC as secondary,
  code-supervised structured EHR; make no free-text claim.
- [ ] `paper_sections/2_introduction.md`: update contribution and layer list.
- [ ] `paper_sections/3_related_work.md`: preserve the distinction between
  MIMIC-RD, which uses notes, and this work's structured MIMIC cohort.
- [ ] `paper_sections/4_benchmark_design.md`: replace “Real EHR Noise” with the
  final task name; specify tables, time window, exclusions, label source, and
  leakage audit.
- [ ] `paper_sections/5_1_agent_fairness_matrix.md`: remove the incorrect claim
  that MIMIC is HPO-only.
- [ ] `paper_sections/5_2_5_4_setup.md`: separate the diagnostic matrix from
  the MIMIC structured-EHR matrix.
- [ ] `paper_sections/6_main_results.md`: replace old MIMIC cells; remove MIMIC
  from diagnostic averages; report attempted denominators and paired arms.
- [ ] `paper_sections/7_2_7_3_7_4_analysis.md`: remove “structured note” and
  interpret the masking contrasts rather than old absolute R@1.
- [ ] `paper_sections/8_ablations.md`: replace or delete legacy MIMIC deltas.
- [ ] `paper_sections/9_limitations.md`: add code-derived gold, absence of
  notes, event-timing, patient leakage, and DUA limitations; “ICU bias” alone is
  insufficient.
- [ ] `paper_sections/10_conclusion.md`: ensure no free-text EHR generalization
  is attributed to MIMIC.
- [ ] `paper_sections/A1_reproducibility_audit.md`: distinguish public frozen
  receipts from credentialed MIMIC regeneration.
- [ ] `paper_sections/B_appendix_baseline_repro.md`: give the new task command
  and remove claims that old cells reproduce the new task.
- [ ] `paper_sections/J_appendix_cost.md`: regenerate from the new receipt or
  remove legacy MIMIC rows.
- [ ] `paper_sections/OSF_preregistration_draft.md`: label the replacement
  analysis as amended/exploratory if it was not genuinely preregistered.

## Tables

- [ ] Main Table 1 contains no stale MIMIC values or MIMIC-inclusive averages.
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

- [ ] `scripts/paper_schematics.py`: replace `Real EHR Noise`.
- [ ] `scripts/paper_new_figures.py`: replace MIMIC labels and remove stale
  summary ingestion.
- [ ] `scripts/paper_figures.py`: do not plot old MIMIC diagnosis cells.
- [ ] `scripts/build_paper_pdf.py`: remove legacy MIMIC heatmap reference.
- [ ] `paper_figures_tables.md`: update the design diagram and result-table
  specification.
- [ ] Captions state “structured EHR” or “ICD leakage audit,” never “note” or
  “free text.”
- [ ] Axes and legends do not place the MIMIC mapping task on the same numeric
  scale as differential diagnosis without an explicit task boundary.
- [ ] Rebuild all figures and inspect final raster/vector output for stale
  labels embedded in images.

## Leaderboard, scripts, and receipts

- [ ] Archive or version `phase4a_summary.json` and
  `phase4a_with_ci.json`; never overwrite ambiguity in place.
- [ ] `scripts/build_leaderboard.py` labels MIMIC as a distinct task and reads
  the new receipt only.
- [ ] `scripts/phase4a_report_gen.py` cannot silently merge old and new MIMIC
  runs.
- [ ] Ranking-stability, prevalence, contamination, and metric-ablation scripts
  either use the new task correctly or exclude MIMIC.
- [ ] Receipt schema includes task version, arm, input-window hours, attempted
  N, error N, mapping snapshot, cohort hash, and prompt hash.
- [ ] One manifest drives Markdown tables, TeX, figures, leaderboard, and cost
  analysis.
- [ ] Protected row-level data remains ignored and absent from Git history.

## References and claims

- [ ] Verify the MIMIC-IV and MIMIC-IV-Note citations are distinct and correct.
- [ ] Verify that MIMIC-RD's note-based design is not attributed to this cohort.
- [ ] Cite the ontology snapshot and ICD-to-Orphanet mapping source/version.
- [ ] Cite/report the PhysioNet credential and DUA requirements accurately.
- [ ] Do not claim independent clinical gold: labels are code-derived.
- [ ] Do not call the task prospective diagnosis unless the input cutoff and
  timestamp audit justify that term.
- [ ] Do not claim clinical-note or HPO extraction performance.

## Final build gate

- [ ] Run unit and data-integrity tests.
- [ ] Regenerate receipts from row-level outputs.
- [ ] Regenerate all Markdown-derived TeX and all figures.
- [ ] Build the complete PDF from a clean checkout plus permitted local data.
- [ ] Search source and generated files for:
  `MIMIC`, `free-text`, `structured note`, `Real EHR`, `956`, old point
  estimates, and legacy receipt names.
- [ ] Inspect every page containing a MIMIC mention, table, figure, or caption.
- [ ] Check cross-references, table/figure numbering, bibliography resolution,
  page overflow, clipped legends, and stale auxiliary files.
- [ ] Confirm the abstract, main table, results narrative, limitations,
  conclusion, appendix, leaderboard, and release statement all describe the
  same task and evidence version.

Only after every applicable item is checked may the MIMIC revision be called
complete.
