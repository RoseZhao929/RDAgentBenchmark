# Figures for Supplementary2027 — NONE ARE CURRENTLY REFERENCED

**Status as of 2026-07-27: `Supplementary2027.tex` contains zero figures.**
It loads `graphicx` (template boilerplate) but has no `\begin{figure}`, no
`\includegraphics`, and no `\label{fig:...}`. Its 8 floats are all tables:

| line | table | content |
|---|---|---|
| 72 | Data layers | L1–L4 source / input / gold |
| 128 | Backbone configurations | pricing + reasoning config |
| 182 | Agent fairness matrix | calls/case, adapter deviations |
| 240 | Per-baseline reproduction | n=50 pilot, ours vs paper |
| 307 | Pre-registered hypotheses | H1–H11 |
| 335 | Holm–Bonferroni correction | family-wise α=.05 |
| 376 | Cost accounting | cumulative cost by backbone |
| 461 | De-leaked MIMIC-IV note probe | mean micro-R@1 x 4 backbones |

So this folder is **not** an extraction of what the supplement uses — there was
nothing to extract.

## What is staged here instead: candidates to ADD to the supplement

These five PNGs exist in `data/round2/figures/` and back appendix material that
the supplement currently states only in prose or tables. They are the natural
figure set if we want the supplement to have figures. **None is wired into any
`.tex` yet.**

| file | would support | current status in supplement |
|---|---|---|
| `fig_costbar.png` | Appendix "Cost Accounting" | table only (line 376) |
| `fig4_a6_contamination_scatter.png` | A6 TS-Guessing contamination audit | not in the AAAI supplement at all (ACL-only, §8.9) |
| `figM4_hpo_density.png` | H8 phenotype-density inverted-U | listed in the hypothesis table, no figure |
| `fig7_specialty_h7.png` | H7 cross-agent specialty blind spots | listed in the hypothesis table, no figure |
| `figH2_genotype.png` | H2 genotype-channel lift | prose only |

Regenerate any of them with `scripts/paper_main_figures.py` (figM4/figH2) or
`scripts/paper_figures.py` (costbar, contamination, specialty); those scripts
are the source of truth.

Not staged: `figM1_v2a_layered.png`, `figM1_v2b_dual.png`,
`figM2_variant{A,B,C}.png` are alternate takes on figures already in the main
paper, and `figMAIN_2x3.png` is the older ACL-order stitch superseded by the
main paper's `subcaption` grid (see `../Figure2/README.md`).
