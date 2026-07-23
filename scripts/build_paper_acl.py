"""Build an ACL/EMNLP-style two-column PDF from paper_sections/*.md.

Pipeline: clean markdown -> pandoc (md->latex fragment) -> wrap in the
official ACL template (acl.sty) -> compile with xelatex (xeCJK safety net
for residual Chinese annotations).  Wide markdown tables become table*
(two-column span); figures are placed inline at the end of their section.

Output: paper_build/acl/main.tex + paper_build/acl/main.pdf
Reuses clean()/MAIN_ORDER/APPENDIX_ORDER from build_paper_pdf.py.
"""
from __future__ import annotations
import re, subprocess, sys, os
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_paper_pdf import clean, MAIN_ORDER, APPENDIX_ORDER, SEC, ROOT, TITLE  # noqa

ACL = ROOT / "paper_build" / "acl"
ACL.mkdir(parents=True, exist_ok=True)
# Source of truth for figure PNGs (produced by scripts/paper_*figures.py +
# paper_schematics.py). copy_figures() mirrors the referenced subset into
# acl/figures/ so the upload package is self-contained. MUST differ from that
# destination, or the copy wipes its own source.
FIGDIR = ROOT / "data/round2/figures"
# pdflatex/bibtex resolve from PATH on this Linux host; the macOS TinyTeX path
# is kept as a fallback for local builds on the author's machine.
_MAC_TEXBIN = Path.home() / "Library/TinyTeX/bin/universal-darwin"
TEXBIN = str(_MAC_TEXBIN) if _MAC_TEXBIN.exists() else "/usr/bin"

# ---- figures, grouped by the section they belong under -----------------
# Figure layout (2026-07 six-panel revision): the main body carries exactly
# ONE architecture overview plus SIX small load-bearing result panels, each
# a distinct finding and none duplicating Table 1:
#   figM1  F1  classical vs best LLM, per layer      (6_main_results)
#   figM2  F3/F4 cost-vs-accuracy Pareto             (6_main_results)
#   figM3  H1  prevalence crossover                  (6_main_results)
#   figM4  H8  phenotype-density inverted-U          (6_main_results)
#   figM6  Holm hypothesis-test forest               (6_main_results)
#   figM5  P5  self-preference / judge-family        (7_5_self_preference)
# The old R@1 heatmap (duplicated Table 1), the best-backbone radar and the
# ranking lollipop are DROPPED; the contamination scatter and specialty
# heatmap keep only their appendix (detail) placement.
FIG_BY_SECTION = {
    # main body: benchmark design -> THE overview (traditional-benchmark contrast)
    "4_benchmark_design.md": [
        ("fig1_overview.png", "\\textbf{RareAgentBench overview.} Four heterogeneous data layers ingest into a single \\texttt{CanonicalCase} contract; 11 agent systems project out of it through subprocess-isolated adapter shims; every capability pillar is evaluated in two passes (Pass~A gold-HPO; Pass~B end-to-end), and the Pass~A$-$Pass~B delta is itself a reported metric. Protocol (H1--H11, A1--A12) pre-registered at OSF."),
    ],
    # main body: the six result panels (five here + self-preference below)
    "6_main_results.md": [
        ("figM1_llm_vs_classical.png", "\\textbf{Classical/offline baselines beat the best scaffolded LLM on HPO input (F1).} Best variant-aware R@1 per data layer, LLM agents vs.\\ classical/offline baselines (attempted denominator, common N=2000 on PP-Store/RareArena). On curated HPO (Phenopacket-Store) LIRICAL leads the best LLM by 17~pp; on free-text RareArena no classical baseline runs (no HPO input)."),
        ("figM2_cost_accuracy.png", "\\textbf{Cost vs.\\ accuracy (F3/F4).} Each marker is one agent~$\\times$~backbone cell on Phenopacket-Store (log cost-per-attempt axis, attempted denominator); dashed line is the Pareto frontier. GPT-5 minimal (diamonds) sits far right at $\\sim$25$\\times$ the cost of DeepSeek V4-Flash with no R@1 gain."),
        ("figM3_prevalence.png", "\\textbf{Prevalence crossover (H1).} Pooled R@1 by Orphanet prevalence tier. LLM agents decline toward the rarest tier while classical/offline baselines rise, inverting the ranking on super-rare disease (+28~pp for classical)."),
        ("figM4_hpo_density.png", "\\textbf{Phenotype-density inverted-U (H8).} Pooled R@1 on the HPO-input layers peaks at 16--30 HPO terms per case; both under- and over-specified inputs degrade accuracy."),
        ("figM6_hypotheses.png", "\\textbf{Pre-registered hypothesis tests.} Forest plot of $-\\log_{10}$(Holm-adjusted $p$) for the six testable hypotheses; five survive family-wise correction at $\\alpha$=0.05. H10 (faithfulness--accuracy decoupling) is reported as exploratory and judge-dependent."),
    ],
    # main body: self-preference methodology finding (sixth panel)
    "7_5_self_preference_bias.md": [
        ("figM5_selfpref.png", "\\textbf{Self-preference bias in LLM-as-judge (P5).} Swapping the judge from a same-family (Gemini) to a non-family (Claude) model on identical traces shrinks the single-LLM lead across all four axes and reverses it on depth, where the multi-expert \\texttt{mdagents} overtakes."),
    ],
    # appendix: reference detail figures (schema + coverage matrix)
    "C_appendix_experimental_setup.md": [
        ("fig_design_matrix.png", "The benchmark evaluation surface: five capability pillars (rows) evaluated across four data layers (columns). Filled = evaluated in v1; grey = deferred to v2; light = not applicable."),
        ("fig_schema.png", "The \\texttt{CanonicalCase} schema. Every dataset ingests into this single Pydantic-v2 record and every agent adapter projects out of it."),
    ],
    # appendix: hypothesis-analysis detail figures (contamination + specialty)
    "7_2_7_3_7_4_analysis.md": [
        ("fig4_a6_contamination_scatter.png", "A6 TS-Guessing contamination audit. Spearman $\\rho$ between log pre-cutoff PubMed mentions and per-disease R@1, per backbone. Every LLM backbone clusters at $\\rho\\approx0.3$ (weak positive); both classical/offline baselines sit at $\\rho\\approx0$ (null control), confirming the pipeline adds no spurious frequency correlation."),
        ("fig7_specialty_h7.png", "H7 cross-agent per-specialty R@1 (modal HPO organ-system axis). Bars span the R@1 range across LLM scaffolds; the shared weak specialties (digestive, metabolic, nervous) indicate ontology/data-level difficulty rather than agent-specific blind spots. Diamonds mark where the classical baselines invert the LLM weakness (nervous, head/neck)."),
    ],
    # appendix: cost bar chart
    "J_appendix_cost.md": [
        ("fig_costbar.png", "Cost per prediction by backbone (log axis); $>$20$\\times$ spread, classical baselines at \\$0."),
    ],
}


_SEEN_SECIDS: set = set()   # cleared at the start of each build (dedup labels)


def strip_section_prefix(md: str) -> str:
    """Drop the redundant '§N' / 'N.M' numeric prefix from headers (ACL auto-
    numbers), and attach a pandoc header id `{#sec-N-M}` so the original number
    becomes a \\label that \\Cref can resolve to the section's *current* number."""
    out = []
    for ln in md.splitlines():
        if re.match(r"^\s*\*\*Target word count\*\*", ln):
            continue
        if re.match(r"^#{1,6}\s+Draft\s*$", ln):
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if m:
            hashes, title = m.group(1), m.group(2)
            numm = re.match(r"^§?\s*(\d+(?:\.\d+)*)\.?\s+", title)
            secid = None
            if numm and numm.group(1) not in _SEEN_SECIDS:
                secid = "sec-" + numm.group(1).replace(".", "-")
                _SEEN_SECIDS.add(numm.group(1))
            title = re.sub(r"^§?\s*\d+(\.\d+)*\.?\s+", "", title)  # "§6.1 X" -> "X"
            title = re.sub(r"^§+\s*", "", title)
            title = re.sub(r"^Table\s+[A-Z]?\d+\s*[—-]+\s*", "", title)  # drop manual "Table 3 —"
            if secid:
                title = f"{title} {{#{secid}}}"   # pandoc header id -> \label{sec-...}
            ln = f"{hashes} {title}"
        out.append(ln)
    return "\n".join(out)


_VALID_SECS = None


def valid_secs():
    """Section numbers that actually have a header (so a \\Cref will resolve)."""
    global _VALID_SECS
    if _VALID_SECS is None:
        _VALID_SECS = set()
        for fn in MAIN_ORDER + APPENDIX_ORDER:
            p = SEC / fn
            if not p.exists():
                continue
            for l in clean(p.read_text()).splitlines():
                m = re.match(r"^#{1,6}\s+(?:§\s*)?(\d+(?:\.\d+)*)\s+", l)
                if m:
                    _VALID_SECS.add(m.group(1))
    return _VALID_SECS


_SEC_FALLBACK = {"5": "5-2", "7": "7-2", "9.6": "9"}  # whole-section refs -> nearest labelled subsection


def fix_section_refs(md: str) -> str:
    """Convert body '§N.M' refs to \\Cref{sec-N-M}. Whole-section refs with no
    exact header fall back to the nearest labelled subsection."""
    valid = valid_secs()

    def repl(m):
        num = m.group(1)
        if num in valid:
            return "\\Cref{sec-%s}" % num.replace(".", "-")
        if num in _SEC_FALLBACK:
            return "\\Cref{sec-%s}" % _SEC_FALLBACK[num]
        return m.group(0)
    return re.sub(r"§\s*(\d+(?:\.\d+)*)", repl, md)


def deemphasize_bold(md: str) -> str:
    """Reduce over-bolding to the reference paper's level: keep a bold run-in
    label at the start of a paragraph/bullet, strip mid-sentence emphasis. Table
    rows (lines starting with '|') are left untouched."""
    # First join newlines that fall INSIDE a bold pair (proper ** pairing), so
    # no single bold spans a line and the per-line pass below can see all of it.
    parts = md.split("**")
    if len(parts) % 2 == 1:                 # balanced ** count -> safe to pair
        for i in range(1, len(parts), 2):   # odd indices are inside bold
            parts[i] = parts[i].replace("\n", " ")
        md = "**".join(parts)
    out = []
    for l in md.splitlines():
        if l.lstrip().startswith("|") or l.lstrip().startswith(">"):
            out.append(l); continue
        lead = re.match(r"^(\s*(?:[-*]\s+)?)(\*\*.+?\*\*)", l)
        if lead:
            head = l[:lead.end()]                       # keep the lead-in bold
            rest = re.sub(r"\*\*(.+?)\*\*", r"\1", l[lead.end():])
            out.append(head + rest)
        else:
            out.append(re.sub(r"\*\*(.+?)\*\*", r"\1", l))
    return "\n".join(out)


# Per-table captions (+ \label). Matched by a space-insensitive substring of the
# markdown header row, so order within a section doesn't matter. Continuous
# numbering + \ref means the label resolves to the right "Table N" automatically.
CAPTIONS = {
    "C_appendix_experimental_setup.md": [
        ("Alias|OpenRouterID", "Backbone LLMs evaluated: dated OpenRouter aliases, pricing, context window and reasoning mode.", "tbl:backbones"),
    ],
    "6_main_results.md": [
        ("Agent|Backbone|PP-Store", "Headline Recall@1 (variant-aware) for every agent $\\times$ backbone cell across the four data layers; bracketed values are per-cell $N$. Classical/offline baselines are listed first.", "tbl:main"),
        ("Agent|Bestbackbone", "Per-agent backbone sensitivity: best vs.\\ worst backbone R@1.", "tbl:bbsens"),
    ],
    "7_5_self_preference_bias.md": [
        ("Agent|factual|relevance", "LLM-judge faithfulness scores (four axes) and the self-preference gap, by agent.", "tbl:selfpref"),
    ],
    "9_limitations.md": [
        ("Attack|Whereaddressed", "Anticipated objections and the section that pre-empts each.", "tbl:objections"),
    ],
    "7_2_7_3_7_4_analysis.md": [
        ("P2(HPO-only)", "P2$\\rightarrow$P3 genotype-aware lift, per agent.", "tbl:p3lift"),
        ("Layer|BestLLM", "Best LLM vs.\\ best classical/offline R@1, per layer (H1).", "tbl:h1layer"),
        ("Tier|LLM", "Prevalence-tier R@1: LLM vs.\\ classical (H1).", "tbl:h1tier"),
        ("Complexity|mdagents", "Multi-agent lift over the single-LLM control, by case complexity (H4).", "tbl:h4"),
        ("Backbone|ndiseases|Spearman", "Contamination correlation between pre-cutoff literature frequency and R@1, by backbone (H3/A6).", "tbl:contam"),
        ("Agent|pre-cutoffR@1", "Difficulty-matched pre- vs.\\ post-cutoff R@1 (H3).", "tbl:h3"),
        ("Pair|Spearman", "Faithfulness-vs-accuracy rank correlation (H10).", "tbl:h10"),
    ],
    "8_ablations.md": [
        ("#|Name|Status", "Pre-registered ablations A1--A12 and their status.", "tbl:ablations"),
        ("Dataset|Aggregate", "ORPHA-variant evaluation-channel effect (A9).", "tbl:a9"),
        ("#|Claim|Stat", "Holm--Bonferroni family-wise correction over H1--H11.", "tbl:holm"),
        ("Backbone|ndiseases|Spearman", "A6 TS-Guessing contamination, by backbone.", "tbl:a6"),
        ("Config|R@1", "H6 reasoning on/off ablation (paired, PP-Store).", "tbl:h6"),
    ],
    "5_1_agent_fairness_matrix.md": [
        ("Agent|NativeInput", "Agent fairness matrix: native inputs, adapter-shim strategy and backbone wiring.", "tbl:fairness"),
        ("Setting|Value|Rationale", "Fixed evaluation settings held constant across agents.", "tbl:settings"),
    ],
    "7_1_p1_p2_cascade.md": [
        ("Bin(#HPOterms)", "R@1 by HPO-count bin (P1$\\rightarrow$P2 cascade).", "tbl:cascade"),
    ],
    "A1_reproducibility_audit.md": [
        ("Agent|Replicated", "Reproduction audit against published paper claims.", "tbl:repro"),
    ],
    "B_appendix_baseline_repro.md": [
        ("Baseline|License", "Baseline reproduction: license, mode, paper vs.\\ our point estimate.", "tbl:baseline"),
    ],
    "J_appendix_cost.md": [
        ("Backbone|Cells|Cases", "Cumulative cost by backbone.", "tbl:jcostbb"),
        ("Rank|Dataset|Agent", "Most cost-efficient (agent, backbone, dataset) cells.", "tbl:jcosteff"),
        ("Dataset|Agent|Backbone|n|R@1|Totalcost", "Highest-spend cells.", "tbl:jcosttop"),
        ("Dataset|R@1", "Cheapest cell exceeding each R@1 band.", "tbl:jcostband"),
    ],
    "OSF_preregistration_draft.md": [
        ("#|Statement|Teststatistic", "Pre-registered hypotheses H1--H11.", "tbl:osfh"),
        ("#|Name|Statusatpre-reg", "Pre-registered ablations at registration time.", "tbl:osfa"),
        ("Layer|Source|Cases|DiseaseIDs", "Data layers and development/test split.", "tbl:osfdata"),
    ],
}


def fix_table_refs(md: str) -> str:
    """Convert hard-coded body references to real cross-refs. 'Table 1' always
    means the main results matrix; 'Table 3' the fairness matrix. 'Table 6' is
    RareBench's own table (external) and is left alone. Runs after headers are
    stripped, so it only touches body prose."""
    md = re.sub(r"\bTable\s+1\b", r"\\Cref{tbl:main}", md)
    md = re.sub(r"\bTable\s+3\b", r"\\Cref{tbl:fairness}", md)
    md = md.replace(r"Appendix Table \ref{tbl:backbones}", r"\Cref{tbl:backbones}")
    md = md.replace(r"Table \ref{tbl:backbones}", r"\Cref{tbl:backbones}")
    return md


def fix_figure_refs(md: str) -> str:
    """Convert hard-coded 'Figure N (`.../figNAME`)' body refs to \\Cref
    cross-refs (the filename in the ref tells us which figure)."""
    md = re.sub(
        r"\*{0,2}Figure\s+\d+[a-d]?\*{0,2}\s*\(?\s*`[^`]*?figures/(?P<name>fig[a-z0-9_]+?)"
        r"(?:\.png)?`\s*\)?:?",
        lambda m: f"\\Cref{{fig:{m.group('name')}}}", md, flags=re.S)
    # the cost-vs-accuracy scatter is now figM2 (six-panel main-body revision)
    md = md.replace("scatter (Figure 2)", "scatter (\\Cref{fig:figM2_cost_accuracy})")
    md = md.replace("Appendix J and Figure 2", "Appendix J and \\Cref{fig:figM2_cost_accuracy}")
    md = md.replace("(Figure 2)", "(\\Cref{fig:figM2_cost_accuracy})")
    return md


def add_table_captions(md: str, section_file: str) -> str:
    """Insert a pandoc table caption (`: cap {#label}`) after each table, matched
    by a space-insensitive substring of its header row."""
    specs = list(CAPTIONS.get(section_file, []))
    if not specs:
        return md
    lines = md.splitlines()
    out, i, n = [], 0, len(lines)
    while i < n:
        is_tbl = (lines[i].strip().startswith("|") and i + 1 < n
                  and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]))
        if is_tbl:
            header = lines[i].replace(" ", "")
            out.append(lines[i]); out.append(lines[i + 1]); j = i + 2
            while j < n and lines[j].strip().startswith("|"):
                out.append(lines[j]); j += 1
            hit = next((k for k, (sig, _, _) in enumerate(specs)
                        if sig.replace(" ", "") in header), None)
            if hit is not None:
                _, cap, lab = specs.pop(hit)
                out += ["", f": {cap} {{#{lab}}}", ""]
            i = j
            continue
        out.append(lines[i]); i += 1
    return "\n".join(out)


def copy_figures():
    """Copy the referenced PNGs into acl/figures/ so main.tex uses relative
    paths and the whole folder is a self-contained Overleaf upload."""
    import shutil
    dst = ACL / "figures"; dst.mkdir(exist_ok=True)
    for old in dst.glob("*.png"):     # drop stale figures so the package is tidy
        old.unlink()
    for figs in FIG_BY_SECTION.values():
        for fn, _ in figs:
            src = FIGDIR / fn
            if src.exists():
                shutil.copy2(src, dst / fn)


def figures_latex(section_file: str) -> str:
    figs = FIG_BY_SECTION.get(section_file, [])
    blocks = []
    for fn, cap in figs:
        if not (FIGDIR / fn).exists():
            continue
        stem = fn[:-4] if fn.endswith(".png") else fn
        blocks.append(
            "\\begin{figure*}[t]\n\\centering\n"
            f"\\includegraphics[width=0.82\\textwidth]{{figures/{fn}}}\n"
            f"\\caption{{{cap}}}\\label{{fig:{stem}}}\n\\end{{figure*}}\n"
        )
    return "\n".join(blocks)


def md_to_latex(md: str) -> str:
    r = subprocess.run(
        ["pandoc", "-f", "markdown+pipe_tables+table_captions", "-t", "latex",
         "--wrap=preserve", "--no-highlight"],
        input=md, capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        raise RuntimeError("pandoc failed: " + r.stderr[-800:])
    return r.stdout


def longtable_to_tablestar(tex: str) -> str:
    """Convert each pandoc longtable into a two-column-spanning table*/tabular.
    pandoc repeats the header (once for \\endfirsthead, once for \\endhead); we
    extract the header once and the data rows once to avoid a doubled header."""
    def conv(m):
        block = m.group(0)
        spec = re.search(r"\\begin\{longtable\}\[\]\{([^}]*)\}", block).group(1)
        cap, lab = "", ""
        cm = re.search(r"\\caption\{(.*?)\}(\\label\{[^}]*\})?\s*(?:\\tabularnewline|\\\\)",
                       block, re.S)
        if cm:
            cap, lab = cm.group(1), (cm.group(2) or "")
        body = re.sub(r"\\begin\{longtable\}\[\]\{[^}]*\}", "", block)
        body = re.sub(r"\\end\{longtable\}", "", body)
        # drop the DUPLICATED continuation header (everything from \endfirsthead
        # through \endhead) — this is what causes the doubled header row
        body = re.sub(r"\\endfirsthead.*?\\endhead", "", body, flags=re.S)
        # the \bottomrule pandoc emits lives in the foot (before the data) — drop
        # it there; we append a single \bottomrule after the data instead
        body = re.sub(r"\\bottomrule\s*(?:\\noalign\{\})?\s*\\endlastfoot", "", body, flags=re.S)
        # strip caption line + any leftover markers
        body = re.sub(r"\\caption\{.*?\}(?:\\label\{[^}]*\})?\s*(?:\\tabularnewline|\\\\)",
                      "", body, flags=re.S)
        body = re.sub(r"\\end(?:head|firsthead|lastfoot|foot)|\\noalign\{\}", "", body)
        body = re.sub(r"\n{2,}", "\n", body).strip()
        capline = f"\\caption{{{cap}}}{lab}\n" if cap else ""   # caption above (ACL)
        return ("\\begin{table*}[t]\n\\centering\\scriptsize\\setlength{\\tabcolsep}{3.5pt}\n"
                f"{capline}"
                f"\\begin{{tabular}}{{{spec}}}\n{body}\n\\bottomrule\n\\end{{tabular}}\n"
                "\\end{table*}")
    return re.sub(r"\\begin\{longtable\}.*?\\end\{longtable\}", conv, tex, flags=re.S)


# Map every Unicode symbol that appears in the body to an engine-agnostic LaTeX
# macro so the document compiles under pdfLaTeX (Overleaf's default) as well as
# XeLaTeX — no inputenc coverage assumptions, no compiler-selection dependency.
UNICODE_MAP = {
    "§": r"\S{}", "×": r"\ensuremath{\times}", "→": r"\ensuremath{\rightarrow}",
    "←": r"\ensuremath{\leftarrow}", "↔": r"\ensuremath{\leftrightarrow}",
    "↑": r"\ensuremath{\uparrow}", "↓": r"\ensuremath{\downarrow}",
    "−": r"\ensuremath{-}", "≈": r"\ensuremath{\approx}", "≥": r"\ensuremath{\geq}",
    "≤": r"\ensuremath{\leq}", "±": r"\ensuremath{\pm}", "∈": r"\ensuremath{\in}",
    "∪": r"\ensuremath{\cup}", "‖": r"\ensuremath{\|}", "△": r"\ensuremath{\triangle}",
    "★": r"\ensuremath{\star}", "⭐": r"\ensuremath{\star}", "✓": r"\ensuremath{\checkmark}",
    "†": r"\dag{}", "…": r"\ldots{}", "—": r"---", "–": r"--",
    "²": r"\textsuperscript{2}", "³": r"\textsuperscript{3}", "₁": r"\textsubscript{1}",
    "α": r"\ensuremath{\alpha}", "β": r"\ensuremath{\beta}", "γ": r"\ensuremath{\gamma}",
    "δ": r"\ensuremath{\delta}", "Δ": r"\ensuremath{\Delta}", "κ": r"\ensuremath{\kappa}",
    "μ": r"\ensuremath{\mu}", "ρ": r"\ensuremath{\rho}", "σ": r"\ensuremath{\sigma}",
    "τ": r"\ensuremath{\tau}", "χ": r"\ensuremath{\chi}", "θ": r"\ensuremath{\theta}",
    "é": r"\'e", "è": r"\`e", "ü": r'\"u', "ö": r'\"o', "ä": r'\"a', "ñ": r"\~n",
}


def sanitize_unicode(tex: str) -> str:
    for ch, rep in UNICODE_MAP.items():
        tex = tex.replace(ch, rep)
    return tex


def _heat_bucket(v):
    return ("heatE", "heatA", "heatB", "heatC", "heatD")[
        0 if v < 0.10 else 1 if v < 0.20 else 2 if v < 0.30 else 3 if v < 0.40 else 4]


HEAT_LEGEND = (r" Cell shading encodes R@1: \colorbox{heatE}{$<$.10}~"
               r"\colorbox{heatA}{.10--.20}~\colorbox{heatB}{.20--.30}~"
               r"\colorbox{heatC}{.30--.40}~\colorbox{heatD}{$\geq$.40}.")


def color_main_table(tex: str) -> str:
    """Heat-map the main results table (label tbl:main): shade each R@1 data cell
    by value (blue ramp) and append the colour legend to the caption — matching
    the reference paper's tab:main styling."""
    m = re.search(r"\\begin\{table\*\}(?:(?!\\end\{table\*\}).)*?\\label\{tbl:main\}"
                  r"(?:(?!\\end\{table\*\}).)*?\\end\{table\*\}", tex, re.S)
    if not m:
        return tex
    block = m.group(0)
    bm = re.search(r"(\\midrule)(.*?)(\\bottomrule)", block, re.S)
    if not bm:
        return tex
    rows = []
    for row in re.split(r"\\\\", bm.group(2)):
        if "&" not in row:
            rows.append(row); continue
        cells = row.split("&")
        for i in range(2, len(cells)):                 # skip Agent, Backbone cols
            dm = re.search(r"(\d\.\d\d)", cells[i])
            if dm and "cellcolor" not in cells[i]:
                cells[i] = " \\cellcolor{%s}%s" % (_heat_bucket(float(dm.group(1))),
                                                   cells[i].lstrip())
        rows.append("&".join(cells))
    newblock = block.replace(bm.group(0), bm.group(1) + "\\\\".join(rows) + bm.group(3))
    # append the colour legend to the caption
    newblock = re.sub(r"(\\caption\{.*?)(\}\s*\\label\{tbl:main\})",
                      lambda mm: mm.group(1) + HEAT_LEGEND + mm.group(2), newblock, flags=re.S)
    return tex.replace(block, newblock)


def promote_caption_ids(tex: str) -> str:
    r"""Older pandoc (2.17) does not consume a table's `{#tbl:x}` caption
    attribute into a \label — it escapes it to literal `\{\#tbl:x\}` text inside
    \caption{}. Convert any such trailing marker into a real \label{} placed
    right after the \caption{} group, so \Cref resolves and no `{#...}` shows in
    the PDF. Handles both table and figure ids, escaped or bare."""
    # escaped form: \caption{ ... \{\#tbl:foo\}}  ->  \caption{...}\label{tbl:foo}
    tex = re.sub(
        r"(\\caption\{)(.*?)\s*\\\{\\#(tbl|fig):([a-zA-Z0-9_]+)\\\}(\})",
        lambda m: f"{m.group(1)}{m.group(2)}{m.group(5)}\\label{{{m.group(3)}:{m.group(4)}}}",
        tex, flags=re.S)
    # bare form (newer pandoc that still leaks): {#tbl:foo}
    tex = re.sub(
        r"(\\caption\{)(.*?)\s*\{\#(tbl|fig):([a-zA-Z0-9_]+)\}(\})",
        lambda m: f"{m.group(1)}{m.group(2)}{m.group(5)}\\label{{{m.group(3)}:{m.group(4)}}}",
        tex, flags=re.S)
    return tex


def postprocess(tex: str) -> str:
    tex = sanitize_unicode(tex)
    tex = promote_caption_ids(tex)
    tex = longtable_to_tablestar(tex)
    tex = color_main_table(tex)
    # breakable code blocks (fvextra) so long lines don't overflow the column
    tex = tex.replace("\\begin{verbatim}", "\\begin{Verbatim}")
    tex = tex.replace("\\end{verbatim}", "\\end{Verbatim}")
    # pandoc figures -> full-width starred floats
    tex = tex.replace("\\begin{figure}", "\\begin{figure*}[t]")
    tex = tex.replace("\\end{figure}", "\\end{figure*}")
    # size any bare includegraphics to the (starred) text width
    tex = re.sub(r"\\includegraphics(?:\[[^\]]*\])?\{", r"\\includegraphics[width=0.82\\textwidth]{", tex)
    # tighten: pandoc's \tightlist is defined by its template; we supply it in preamble
    return tex


PREAMBLE = r"""% Compiles with the default pdfLaTeX on Overleaf (no compiler change needed).
% All non-ASCII symbols are converted to LaTeX macros at build time, so no
% fontspec / XeLaTeX / CJK fonts are required.
\documentclass[11pt]{article}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage[final]{acl}
\usepackage{times}
\usepackage{latexsym}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{array}
\usepackage{calc}
\usepackage{textcomp}
\usepackage{fvextra}
\fvset{breaklines=true,breakanywhere=true,fontsize=\scriptsize}
\usepackage[htt]{hyphenat}  % allow line breaks inside \texttt paths/code
\usepackage{multirow}
\usepackage{makecell}
\usepackage{xcolor}
\usepackage{colortbl}          % \cellcolor heat-map for the main results table
\usepackage{amsmath,amssymb}
\usepackage{caption}
\usepackage{url}
\usepackage[capitalize]{cleveref}   % \Cref{tab:main} -> "Table 1", "Section 3"
% Blue heat ramp for R@1 (5 buckets) + green ramp for the variant-lift row,
% matching the reference paper's palette.
\definecolor{heatE}{HTML}{F6F9FC}
\definecolor{heatA}{HTML}{E2EAF3}
\definecolor{heatB}{HTML}{C7D5E4}
\definecolor{heatC}{HTML}{AABCD3}
\definecolor{heatD}{HTML}{8AA4C3}
\providecommand{\tightlist}{\setlength{\itemsep}{0pt}\setlength{\parskip}{0pt}}
\providecommand{\st}[1]{#1}
\emergencystretch=3em
\sloppy
\title{__TITLE__}
\author{Anonymous ACL submission}
\begin{document}
\maketitle
\nocite{*}
"""


def main():
    _SEEN_SECIDS.clear()   # fresh label set each build
    # ---- abstract ------------------------------------------------------
    abs_md = strip_section_prefix(clean((SEC / "1_abstract.md").read_text()))
    # everything after the (now header-less) 'Abstract' heading is the body
    abs_md = re.sub(r"^#+\s*Abstract\s*$", "", abs_md, flags=re.M).strip()
    abs_md = deemphasize_bold(abs_md)
    abstract_tex = postprocess(md_to_latex(abs_md))

    # ---- modular output: each section is its own tex/<stem>.tex, main.tex
    #      only \input-s them, so any part can be commented out for debugging ----
    texdir = ACL / "tex"; texdir.mkdir(exist_ok=True)
    for old in texdir.glob("*.tex"):
        old.unlink()

    def emit(fn):
        p = SEC / fn
        if not p.exists():
            return None
        md = add_table_captions(strip_section_prefix(clean(p.read_text())), fn)
        md = fix_section_refs(fix_table_refs(fix_figure_refs(md)))
        md = deemphasize_bold(md)
        tex = postprocess(md_to_latex(md))
        figs = figures_latex(fn)
        stem = re.sub(r"\.md$", "", fn)
        (texdir / f"{stem}.tex").write_text(tex + ("\n\n" + figs if figs else "") + "\n")
        return f"\\input{{tex/{stem}}}"

    (texdir / "abstract.tex").write_text(
        "\\begin{abstract}\n" + abstract_tex + "\n\\end{abstract}\n")

    main_inputs = [x for x in (emit(fn) for fn in MAIN_ORDER if fn != "1_abstract.md") if x]
    app_inputs = [x for x in (emit(fn) for fn in APPENDIX_ORDER) if x]

    copy_figures()

    doc = (PREAMBLE.replace("__TITLE__", TITLE)
           + "% ==== abstract (comment the next line to drop it) ====\n"
           + "\\input{tex/abstract}\n\n"
           + "% ==== main body ====\n"
           + "\n".join(main_inputs) + "\n\n"
           + "% ==== references (acl.sty already sets \\bibliographystyle) ====\n"
           + "\\bibliography{references}\n\n"
           + "% ==== appendices ====\n"
           + "\\appendix\n\\section*{Appendices}\n"
           + "\n".join(app_inputs) + "\n"
           + "\\end{document}\n")

    tex_out = ACL / "main.tex"
    tex_out.write_text(doc)
    print(f"wrote {tex_out} + tex/ ({len(main_inputs) + len(app_inputs) + 1} modules)")

    # full LaTeX cycle so citations + References section resolve:
    # pdflatex -> bibtex -> pdflatex -> pdflatex
    env = dict(os.environ, PATH=TEXBIN + ":" + os.environ.get("PATH", ""))
    subprocess.run(["pdflatex", "-interaction=nonstopmode", "main.tex"], cwd=ACL, env=env, capture_output=True, text=True, errors="replace")
    subprocess.run(["bibtex", "main"], cwd=ACL, env=env, capture_output=True, text=True, errors="replace")
    for _ in range(2):
        r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "main.tex"], cwd=ACL, env=env, capture_output=True, text=True, errors="replace")

    pdf = ACL / "main.pdf"
    if not pdf.exists():
        errs = [l for l in r.stdout.splitlines() if l.startswith("!")][:10]
        print("PDF FAILED. errors:\n" + "\n".join(errs)); return
    print(f"PDF: {pdf} ({pdf.stat().st_size//1024} KB)")

    # self-contained Overleaf upload package (tex + style + bib + figures)
    import zipfile
    keep = ["main.tex", "acl.sty", "acl_natbib.bst", "references.bib"]
    zpath = ACL / "overleaf_upload.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in keep:
            if (ACL / f).exists():
                z.write(ACL / f, f)
        for tex in sorted((ACL / "tex").glob("*.tex")):
            z.write(tex, f"tex/{tex.name}")
        for png in sorted((ACL / "figures").glob("*.png")):
            z.write(png, f"figures/{png.name}")
    print(f"ZIP: {zpath} ({zpath.stat().st_size//1024} KB) — drop into Overleaf 'New Project > Upload Project'")


if __name__ == "__main__":
    main()
