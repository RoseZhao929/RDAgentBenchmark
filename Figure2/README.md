# Figures used in AnonymousSubmission2027 (AAAI 2027 submission)

Copied verbatim from `paper_aaai27/Figures/` on 2026-07-27. Order = order of
appearance in the compiled PDF.

| file | fig # | section | content |
|---|---|---|---|
| `fig_design_matrix.png` | Fig 2 | §4 Four-Layer Data Stack | 5 capability pillars x 4 data layers coverage grid |
| `fig_schema.png` | Fig 3 | §4 Canonical Case Representation | CanonicalCase record diagram |
| six PNGs below | Fig 4 (a)–(f) | §6–§7, full-width `figure*` | six `subfigure` panels in a 3x2 grid |

Fig 1 is still the LaTeX-drawn `\fbox` placeholder in §2 ("Planned Figure 1:
From fragmented evaluation to RareAgentBench") — no PNG.

## Figure 4: six `subfigure` panels

The former Figs 4–9 are now sub-panels of one `figure*`, via
`\usepackage{subcaption}`. **Each panel is still its own original PNG** at
`\includegraphics[height=1.55in]` — no pre-stitched bitmap, so every panel keeps
its native resolution and can be regenerated independently.

| panel | source png | was | content |
|---|---|---|---|
| (a) | `figM1_llm_vs_classical.png` | Fig 4 | best LLM vs best classical, R@1 + R@5 gain |
| (b) | `figF2_scaffolding.png` | Fig 5 | scaffold delta vs no-scaffold control, PP-Store + de-leaked MIMIC |
| (c) | `figM2_cost_accuracy.png` | Fig 6 | cost per attempt vs R@1, Pareto frontier |
| (d) | `figM3_prevalence.png` | Fig 7 | R@1 by Orphanet prevalence tier |
| (e) | `figM6_hypotheses.png` | Fig 8 | Holm-adjusted H1–H11 outcomes |
| (f) | `figM5_selfpref.png` | Fig 9 | LLM-judge self-preference (SF vs CF) |

Each panel carries a short `\caption` (rendered as "(a) Classical/offline vs.
best LLM" etc.) plus a `\label{sfig:...}`; the six in-text references use
`Figure~\ref{fig:main6}\subref{sfig:...}`, so panel letters follow the
subfigure order automatically instead of being hard-coded.

The generators in `scripts/paper_main_figures.py` are untouched and remain the
source of truth for all six PNGs.

## Not used by the paper (left in `paper_aaai27/Figures/`)

- `figure1.pdf`, `figure2.pdf` — AAAI template's own bad-cropping demo images
  (dice / garbled text). Referenced only by the untouched `CameraReady2027.tex`
  boilerplate, never by the submission.
- `fig1_heatmaps.png`, `fig2_cost_accuracy.png`, `fig3_ranking.png` — earlier
  draft figures, no `\includegraphics` references any of them.
- `fig_design_matrix.png.preDeleak.bak` — pre-de-leaking backup (said n=956).
