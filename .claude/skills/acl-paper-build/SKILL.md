---
name: acl-paper-build
description: Build a clean, camera-ready ACL/EMNLP two-column PDF from markdown draft sections. Covers the pandoc→LaTeX pipeline, pdfLaTeX/Overleaf portability, stripping draft scaffolding, Nature-grade figures, captions/cross-refs, and self-testing the compile. Use when assembling/polishing the RareAgentBench paper (paper_sections/ → paper_build/acl/).
---

# Building an ACL/EMNLP PDF from markdown drafts

Living playbook — distilled from actually shipping the RareAgentBench paper. Append new lessons as they happen.

## The pipeline
`paper_sections/*.md` → `scripts/build_paper_pdf.py:clean()` (strip scaffolding) → pandoc (md→latex fragment) → `scripts/build_paper_acl.py:postprocess()` (sanitize + table*/figure* fixes) → wrap in official `acl.sty` → **pdflatex → bibtex → pdflatex ×2** → `paper_build/acl/main.pdf`.

Two builders share `clean()`:
- `build_paper_pdf.py` → simple single-column typst preview.
- `build_paper_acl.py` → the real ACL two-column deliverable + `overleaf_upload.zip`.

Rebuild: `python3 scripts/build_paper_acl.py`. Figures: `scripts/paper_figures.py` (data plots), `scripts/paper_schematics.py` (design matrix + schema), `scripts/regen_receipts_and_figures.py --figs-only` (fig4-7). Shared style: `scripts/_figstyle.py`. TinyTeX bin: `~/Library/TinyTeX/bin/universal-darwin` (no sudo; basictex needs sudo — avoid).

## CARDINAL RULE: self-test in a clean room before handing off
The local build succeeding is NOT proof it works elsewhere. Copy ONLY the upload package to a fresh dir and run the real cycle — this catches every portability bug:
```bash
SB=/tmp/sim; rm -rf $SB; mkdir $SB
cd paper_build/acl && cp main.tex acl.sty acl_natbib.bst references.bib $SB/ && cp -r tex figures $SB/ && cd $SB
pdflatex -interaction=nonstopmode main.tex; bibtex main; pdflatex ...; pdflatex ...
# assert: "Output written on main.pdf", grep -c '^!' == 0, no "cannot be found", bbl has entries
```
When the user reports "Overleaf won't compile," reproduce it HERE first. Don't guess.

## Overleaf / pdfLaTeX portability (the #1 source of "won't compile")
- **NO `fontspec`, NO `xeCJK`, NO OS-specific fonts** (`PingFang SC` etc.). fontspec requires XeLaTeX; Overleaf defaults to pdfLaTeX → fatal, no PDF. macOS fonts don't exist on Overleaf's Linux.
- Target **pdfLaTeX** with `\usepackage[T1]{fontenc}` + `\usepackage[utf8]{inputenc}` + `\usepackage{times}`. Don't rely on a `% !TeX program` magic comment being honored.
- **Sanitize every non-ASCII glyph to a LaTeX macro** at build time (`UNICODE_MAP` + `sanitize_unicode()` in build_paper_acl.py). pdfLaTeX chokes on §×→ρ≤≈τκΔ… Use `\ensuremath{...}` for math symbols (works in text or math), text macros (`\S{}`, `\textsuperscript{2}`, `---`) for typography. After build, assert **0 bytes >127** in main.tex + tex/.
- matplotlib figures: Arial lacks ✓ (U+2713), ‖ (U+2016), etc. Draw checkmarks with `ax.plot` line segments; use ASCII `|` not `‖`. Watch out for `invert_yaxis()` flipping drawn strokes.
- subprocess running latex: pass `text=True, errors="replace"` — latex logs contain non-UTF-8 bytes that crash `text=True` decoding.

## Killing draft scaffolding (it keeps leaking — audit the CLEANED output, not the source)
`clean()` in build_paper_pdf.py is **level-aware**:
- `DROP_SECTION` — drop a whole `##`/`###` section (header + body until next header of same-or-higher level). Covers: Working Notes, Citations, What's strong, Still missing, Length check/budget, Figure tie-in, Why this, TODO, CTA, Scoring, Release statement, 验证点, 等数据.
- `DROP_HEADER_ONLY` — drop just the header line, keep body ("Draft for paper main text", "Draft").
- `_drop_meta_blockquotes()` — drop whole consecutive `>` blocks that match META_QUOTE OR contain CJK (multi-line meta notes leak if you only match the first line).
- `LENGTH_NOTE` + `drop_para` — drop multi-line author notes like `**Word count**: ...` / `**Target length**: ...` (until blank line).
- Also strip: emoji, `(paper draft v0)`, `(P6.3)` header suffixes, `**Target word count**`.

Scaffolding leaked THREE times before it was clean. Each time: dump `clean()` output for every section and grep for signatures (`target length|word count|working note|reviewer attack|plan.md|~N words|~N page|<NAME>|<USER>|XXXXX|TODO|数据源|状态|等数据`). Verify **0** in the final rendered PDF text (`pdftotext main.pdf -`), not just the source.

Also reword author jargon that isn't scaffolding but reads unprofessionally: **"reviewer attack #N" → "anticipated objection #N"**; strip internal file refs `(plan.md §6)`, `round2_plan.md §7.2`. Replace name placeholders `<NAME>`/`<benchmark name>` → the real name.

## Known compile-breakers + fixes
- **`\unskip in vertical mode` at `\end{abstract}`**: the abstract content ends in vertical mode (a leaked `## CTA`/`## Scoring checklist` whose `\end{itemize}` is the last thing). Fix = drop that scaffolding so the abstract ends with prose. Extract abstract as its own `tex/abstract.tex` = full `\begin{abstract}...\end{abstract}`.
- **`Illegal, another \bibstyle`**: `acl.sty` already issues `\bibliographystyle{acl_natbib}` (line ~195). Do NOT add your own — only `\bibliography{references}`. Use `\nocite{*}` so all entries appear without inline `\cite`.
- **bibtex "comma at end of name"**: `.bib` `author = {Zhao, and others}` is malformed → `{Zhao and others}`.
- **`\real`/`\tabcolsep` undefined**: pandoc proportional table widths need `\usepackage{calc}`. Also pass pandoc `--no-highlight` (kills `\NormalTok` etc.), add `textcomp`.
- **wide tables overflow**: pandoc emits `longtable` (single-column width). Convert to `table*` (spans both columns) + `\scriptsize` + `\setlength{\tabcolsep}{3.5pt}` (`longtable_to_tablestar()`).
- **code blocks overflow**: `verbatim` → `Verbatim` (fvextra) with `breaklines`. Long `\texttt` paths → `\usepackage[htt]{hyphenat}`. Backstop: `\emergencystretch=3em` + `\sloppy`.
- **Python `%`-format on preamble** with literal `%` comments corrupts it → use `.replace("__TITLE__", ...)`.

## ACL structure conventions (a benchmark paper MUST follow)
- Every Table and Figure needs a **number + caption + a body reference**. DONE via: `CAPTIONS` map + `add_table_captions()` injects pandoc `: cap {#tbl:key}` after each table (matched by space-insensitive header substring); `longtable_to_tablestar` preserves `\caption\label`; `fix_table_refs()`/`fix_figure_refs()` convert hard-coded "Table 1"/"Figure N (`.../figX.png`)" body text to real `\ref`; figures get `\label{fig:<stem>}`. Continuous numbering + `\ref` = numbers always correct regardless of order (main results ended up Table 2, backbone table Table 1 — fine). CAUTION: "RareBench Table 6" cites *another paper's* table — leave literal (fix_table_refs only touches Table 1/3). Enable pandoc `+table_captions`. `\ref`/`\label`/`\caption` pass through pandoc as raw latex. Drop manual "Table N —" prefixes from headings (strip_section_prefix). Assert 0 "Table ??"/"Figure ??" and 0 `data/round2/figures` path leaks in the PDF.
- Prefer **figures over tables/code** for conceptual content: the pillar×layer table → a coverage-matrix figure (`fig_design_matrix`); the `CanonicalCase` code block → a record diagram (`fig_schema`). Nature-tier venues expect diagrams, not pasted Python.
- Trim over-detailed subsections from the main body; reference them as "(details in Appendix X)". Move full hypothesis analysis + full ablations to the appendix; keep headline results (Table 1, F1-F5, self-preference, contamination, Holm summary) in main.

## Prose style (write like AAAI / Nature, not like dev notes)
The markdown drafts are full of engineer-brain tells that must be scrubbed for a real paper:
- **No internal file paths in prose.** `paper_sections/J_appendix_cost.md`, `scripts/foo.py`, `data/round2/...`, `harness/...` never belong in body text — say "Appendix J" (and make it a clickable `\ref`/`\hyperref`, since acl.sty loads hyperref). Reproducibility appendix may name a script, but main body never shows a path.
- **No meta-parentheticals.** `(5 paper claims)`, `(J_appendix_cost.md, 6 subsections — cumulative by backbone, cost-per-case ranking, …)`, `(Table A2 details)` — either fold the info point into the sentence, or move it into the target section. A parenthetical listing subsections/claims/files reads as unprofessional. Rule of thumb: if the paren contains a *list* or a *file* or a *count-of-things-elsewhere*, rewrite it out.
- **No manual "Table 3 —" / "Figure 2 —" numbering in prose or headings** — LaTeX numbers; use `\ref`.
- **Experiment details / parameter dumps go to the appendix.** Backbone alias/price tables, fixed-setting tables, per-cell cost tables are not the story — the story is findings. Keep a one-sentence pointer in the main body ("we evaluate four backbones; pricing in Appendix X") and move the table out.
- Scan the WHOLE doc each pass: `grep -nE "paper_sections/|scripts/|data/round2|harness/|docs/|\.py\b|\.jsonl?\b|\.csv\b" ` over cleaned output, and eyeball every `(` in the rendered PDF for meta-parentheticals.

## Matching a reference paper's LaTeX conventions (EMNLP healthbench)
The user's prior accepted paper (EMNLP_2026_healthBench.zip → latex/acl_latex.tex + table*.tex) is the style target. Adopted:
- **`\usepackage[capitalize]{cleveref}` + `\Cref{tab:main}`/`\Cref{sec:..}`/`\Cref{fig:..}`** — auto-adds "Table 1"/"Section 3"/"Figure 5", capitalized, clickable. Replace `Table \ref{}` → `\Cref{}` (drop the literal word). Needs `cleveref` + `grfext`/`zref` installed in TinyTeX (Overleaf has them). Labels: caption's `\label{tbl:..}` (table*), `\caption{}\label{fig:..}` (figure*).
- **Heat-map main results table** (`color_main_table()`): `\definecolor{heatE..D}{HTML}{...}` blue ramp; shade each R@1 cell `\cellcolor{heatX}` by value bucket (<.10 E … ≥.40 D); append the swatch legend to the caption (`\colorbox{heatE}{$<$.10}~…`). Cells are simple (`\textbf{0.47} {[}2000{]}`) after longtable_to_tablestar — split body on `\\`, cells on `&`, skip first 2 label columns.
- **Captions above the tabular** (ACL convention), rich + descriptive: define abbreviations inline, put the colour legend in the caption.
- Prose: `\textit{method-name}`, `\textbf{(F1)}` finding labels, `6{,}271` thousands, `$+29.8$~pp`, `vs.\ `.
- Packages they use: booktabs, colortbl, multirow, makecell, tcolorbox, tabularx, rotating, subfig, cleveref.
- **STILL TODO:** convert body `§N.M` section refs to `\Cref{sec:..}`. Tricky because the restructure (moving 7.1/7.2–7.4/8 to the appendix) made the literal "§7.1" numbers STALE — they must be re-mapped to labels by content, not just reformatted.

## Nature-grade figures (`_figstyle.py`)
Okabe-Ito colorblind palette, Arial, 300 dpi, despined, perceptually-uniform `rocket_r` heatmap cmap, luminance-aware cell-label color. Diversify types (not all bars): multi-panel heatmap, Pareto-frontier scatter, lollipop/dot-plot (not bars), curves, schematic matrices/cards. `apply_nature_style()` once per figure fn; save PNG at 300 dpi.

## Figures go in a self-contained folder
Copy PNGs into `paper_build/acl/figures/` and reference with **relative paths** `figures/x.png` (absolute `/Users/...` breaks Overleaf). Wipe stale PNGs on each build. Modular `tex/` (one `\input` per section) so a reviewer can comment any part out.

## Reproducibility honesty (project rule)
When a planned experiment can't run, dig until you know exactly why, then document precisely — don't overstate. Ex: H5/Chinese layer — the labelled PUMCH corpus is access-restricted (no public channel) AND the only public slice (`public_PUMCH-87.json`) has phenotypes but no diagnosis gold, so it's unscoreable. See §9 L3.
