# Paper Figures and Tables — Current Submission Inventory

> This file describes the figures and tables actually emitted by
> `scripts/build_paper_acl.py`. It replaces the historical pre-Phase-4 figure
> wish list. Figure numbers below are the current build order; LaTeX labels,
> rather than hard-coded numbers, should be used in prose.

## Caption rules

- State the plotted population, denominator, unit, and relevant N.
- Explain every missing bar, point, or dataset; absence must not look like zero.
- Distinguish observational associations from causal interventions.
- Name coupled variables and identify rows whose inputs changed.
- Keep MIMIC outside the frozen diagnostic matrix until the replacement
  structured-EHR experiment has row-level receipts.

## Main-text figures

1. `fig1_overview.png` — benchmark architecture. Three diagnostic layers use
   `CanonicalCase`; MIMIC is a separately reported, pending structured-EHR
   replacement protocol mapped at the adapter boundary.
2. `figM1_llm_vs_classical.png` — scope of the LLM/classical comparison.
   It shows three of five dataset resources: Phenopacket-Store and RareBench
   have paired families; RareArena is LLM-only because the classical systems
   require HPO input. PMC lacks a matched classical run and MIMIC is a
   different task.
3. `figM2_cost_accuracy.png` — Phenopacket-Store cost/accuracy cells and the
   empirical Pareto frontier. Per-cell costs vary by scaffold; the caption
   gives the receipt-weighted cross-run GPT-5/V4-Flash ratio (~24×).
4. `figM3_prevalence.png` — super-rare tail crossover. The middle tiers are
   explicitly non-monotonic; H1's supported contrast is the super-rare tail.
5. `figM4_hpo_density.png` — observational HPO-count bins. The caption states
   that this is an association, not an intervention on phenotype count.
6. `figM6_hypotheses.png` — Holm-adjusted tests. H10's single-judge p-value is
   nominally below 0.05 but is greyed and not counted as confirmed because the
   threshold verdict changes under same-trace re-judging.
7. `figM5_selfpref.png` — judge-swap sensitivity. Gemini-to-Claude changes
   judge identity and judge/agent family relation together. Solid lines keep
   traces fixed; dashed `mdagents` also includes trace repair.

## Appendix figures

8. `fig_design_matrix.png` — capability coverage. Blue means a frozen result;
   amber marks the MIMIC replacement protocol as specified but not yet scored;
   grey means deferred; light means not applicable.
9. `fig_schema.png` — diagnostic `CanonicalCase` plus the adapter-boundary
   structured-event snapshot used by the pending MIMIC design.
10. `fig4_a6_contamination_scatter.png` — literature-frequency association.
    It reports per-backbone disease N and does not claim that correlation
    proves memorisation.
11. `fig7_specialty_h7.png` — LLM midpoint with min/max scaffold whiskers.
    Classical diamonds are plotted only where comparable values were reported;
    missing diamonds are not zeros.
12. `fig_costbar.png` — receipt-weighted mean diagnostic cost per prediction:
    GPT-5 $0.00791 versus V4-Flash $0.00033 (~24×). Zero-cost classical rows
    are omitted from the log axis and named in the caption.

## Tables

Table captions are centrally defined in `scripts/build_paper_acl.py`.
Load-bearing conventions:

- Headline R@1 matrix: bracketed N is attempted N and is the R@1 denominator.
  It covers only the three diagnostic datasets; MIMIC is separate.
- Judge-score table: arrows are Gemini-to-Claude. `mdagents` and `maidxo`
  include trace repair and are not clean judge-only contrasts.
- Cost tables: values come from diagnostic receipts; legacy MIMIC title/code
  runs are excluded.
- Hypothesis table: H10 is labelled nominal and judge-dependent rather than
  counted as a confirmed family-wise conclusion.

## Regeneration

```bash
python3 scripts/paper_main_figures.py
python3 scripts/paper_schematics.py
python3 scripts/paper_new_figures.py
python3 scripts/build_paper_acl.py
```

The submission artifacts are `paper_build/acl/main.pdf` and
`paper_build/acl/overleaf_upload.zip`.
