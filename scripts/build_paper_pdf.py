"""Assemble paper_sections/*.md into one clean master markdown + build a PDF
(pandoc + typst). Strips internal draft/meta notes so the PDF reads as a paper.

Output: paper_build/paper.md  +  paper_build/paper.pdf
"""
from __future__ import annotations
import re, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEC = ROOT / "paper_sections"
BUILD = ROOT / "paper_build"; BUILD.mkdir(exist_ok=True)

TITLE = "RareAgentBench: A Multi-Pillar, Contamination-Controlled Benchmark of LLM Agents for Rare-Disease Diagnosis"

# MAIN BODY — the core narrative (target ~15-18 pp)
MAIN_ORDER = [
    "1_abstract.md",
    "2_introduction.md",
    "3_related_work.md",
    "4_benchmark_design.md",
    "5_2_5_4_setup.md",
    "6_main_results.md",
    "7_5_self_preference_bias.md",
    "9_limitations.md",
    "10_conclusion.md",
]
# APPENDICES — detailed analysis + reproducibility moved out of the main body
APPENDIX_ORDER = [
    "C_appendix_experimental_setup.md",  # backbone table + held-constant settings
    "7_2_7_3_7_4_analysis.md",   # full hypothesis analysis (H1/H3/H4/H7/H8, A6)
    "8_ablations.md",            # full ablation detail + Holm table
    "5_1_agent_fairness_matrix.md",
    "7_1_p1_p2_cascade.md",
    "A1_reproducibility_audit.md",
    "B_appendix_baseline_repro.md",
    "J_appendix_cost.md",
    "OSF_preregistration_draft.md",
]

# Header TEXT (after the ##) whose ENTIRE section — header plus body, down to
# the next header of the same-or-higher level — is internal author scaffolding.
DROP_SECTION = re.compile(
    r"(working\s+notes|citation|what'?s?\s+strong|strengths?\s+of\s+this\s+draft"
    r"|what.*missing|still\s+missing|length\s+check|length\s+budget|^length\b"
    r"|figure\s+tie-?in|why\s+this\b|todo|\bcta\b|scoring(\s+checklist)?"
    r"|release\s+statement|figures?\s*\(rendered|^cross-references\s*$"
    r"|验证点|验证点?|写作检查|状态检查|等数据|phase\s*4a\s*验证)",
    re.I)

# Wrapper headers that are scaffolding but whose BODY is the real paper text —
# drop only the header line, keep everything under it.
DROP_HEADER_ONLY = re.compile(r"^(draft\s+for\s+paper\s+main\s+text|draft)\s*$", re.I)

# blockquote meta-note lines (author scaffolding at top of sections)
META_QUOTE = re.compile(r"^\s*>\s*(写作目的|数据源|数据来源|目标长度|目标|状态|依赖|写作|注意|TODO|plan\.md|round2_plan"
                        r"|reviewer attack|写作检查|— plan|锁的|方案\.md|Methodology).*", re.I)

# author length / word-count note lines (start of a droppable note paragraph)
LENGTH_NOTE = re.compile(
    r"^\s*\*{0,2}(Target\s+length|Target\s+word\s+count|Word\s+count|Length\s+budget)\b", re.I)

EMOJI = re.compile(r"[✅⚠️⛔🟡🔴🟢❌➡️🔵]")
HRULE = re.compile(r"^\s*([-*_])\1{2,}\s*$")          # thematic break --- *** ___
DRAFT_TAG = re.compile(r"\s*\((paper )?draft v?\d+\)", re.I)


CJK = re.compile(r"[一-鿿]")


def _drop_meta_blockquotes(lines):
    """Remove whole consecutive blockquote (>) blocks that are author meta-notes
    (match META_QUOTE anywhere, or contain CJK). Genuine English quotes survive."""
    out, i, n = [], 0, len(lines)
    while i < n:
        if re.match(r"^\s*>", lines[i]):
            j = i
            while j < n and re.match(r"^\s*>", lines[j]):
                j += 1
            block = lines[i:j]
            scaffold = any(META_QUOTE.match(b) or CJK.search(b) for b in block)
            if not scaffold:
                out.extend(block)
            i = j
        else:
            out.append(lines[i]); i += 1
    return out


def clean(md: str) -> str:
    """Strip all author scaffolding so the output reads as finished paper prose."""
    lines = _drop_meta_blockquotes(md.splitlines())
    out = []
    skip_level = None   # while set, drop lines until a header of level <= skip_level
    drop_para = False   # while set, drop an author note-paragraph until a blank line
    for ln in lines:
        hm = re.match(r"^(#{1,6})\s+(.*?)\s*$", ln)
        level = len(hm.group(1)) if hm else None
        htext = hm.group(2) if hm else ""

        # inside a dropped scaffolding section?
        if skip_level is not None:
            if level is not None and level <= skip_level:
                skip_level = None            # this header closes the block; reprocess it below
            else:
                continue

        # inside a dropped note-paragraph (e.g. "**Word count**: ... trim ... if needed.")
        if drop_para:
            if not ln.strip():
                drop_para = False
            continue
        if LENGTH_NOTE.match(ln):
            drop_para = True
            continue

        if hm and DROP_SECTION.search(htext):
            skip_level = level               # drop this whole section
            continue
        if hm and DROP_HEADER_ONLY.match(htext):
            continue                          # drop wrapper header, keep body

        if META_QUOTE.match(ln):
            continue
        if HRULE.match(ln):
            continue
        # lone checkbox / status-emoji bullet lines
        if re.match(r"^\s*[-*]\s*" + EMOJI.pattern, ln):
            continue
        # reviewer-note / TODO note lines (any position)
        if re.match(r"^\s*>?\s*⚠\s*\*\*REVIEWER NOTE", ln) or re.match(r"^\s*>?\s*\*?\*?TODO", ln, re.I):
            continue
        if ln.lstrip().startswith(">") and "TODO" in ln:
            continue

        # clean header text: strip draft tags, internal (P6.3) refs, emoji
        if hm:
            t = DRAFT_TAG.sub("", htext)
            t = re.sub(r"\s*\(P\d[\d.]*\)\s*$", "", t)
            t = EMOJI.sub("", t).strip()
            ln = f"{hm.group(1)} {t}"
        else:
            ln = EMOJI.sub("", ln).rstrip()

        out.append(ln)
    txt = "\n".join(out)
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    return txt.strip()


def main():
    parts = [
        f"% {TITLE}",
        "% Anonymous submission",
        "",
    ]
    body = []
    for fn in MAIN_ORDER:
        p = SEC / fn
        if not p.exists():
            continue
        body.append(clean(p.read_text()))

    # ---- Appendices divider + appendix sections ----
    body.append("# Appendices")
    for fn in APPENDIX_ORDER:
        p = SEC / fn
        if not p.exists():
            continue
        body.append(clean(p.read_text()))

    # Figures appendix (embed the generated PNGs with captions)
    FIGDIR = ROOT / "data/round2/figures"
    FIGS = [
        ("fig1_heatmap_phenopacket_store.png", "Figure 1a. R@1 heatmap — Phenopacket-Store (agent × backbone)."),
        ("fig1_heatmap_rarearena_rds.png", "Figure 1b. R@1 heatmap — RareArena RDS."),
        ("fig1_heatmap_rarebench.png", "Figure 1d. R@1 heatmap — RareBench HF."),
        ("fig2_cost_vs_accuracy.png", "Figure 2. Cost vs accuracy (per-prediction USD)."),
        ("fig3_per_dataset_ranking.png", "Figure 3. Per-dataset agent ranking."),
        ("fig4_a6_contamination_scatter.png", "Figure 4. A6 TS-Guessing contamination scatter (LLM vs classical)."),
        ("fig5_prevalence_h1.png", "Figure 5. H1 prevalence-stratified R@1."),
        ("fig6_hpo_density_h8.png", "Figure 6. H8 phenotype-density inverted-U."),
        ("fig7_specialty_h7.png", "Figure 7. H7 cross-agent specialty blind spots."),
    ]
    fig_md = ["# Appendix: Figures", ""]
    for fn, cap in FIGS:
        p = FIGDIR / fn
        if p.exists():
            fig_md.append(f"![{cap}]({p})\n")
            fig_md.append(f"*{cap}*\n")
    body.append("\n".join(fig_md))

    master = "\n".join(parts) + "\n\n" + "\n\n\\newpage\n\n".join(body) + "\n"
    md_out = BUILD / "paper.md"
    md_out.write_text(master)
    print(f"wrote {md_out} ({len(master.split())} words)")

    pdf_out = BUILD / "paper.pdf"
    cmd = ["pandoc", str(md_out), "-o", str(pdf_out),
           "--pdf-engine=typst", "--toc", "--toc-depth=2",
           "-V", "papersize=a4", "-V", "fontsize=10pt"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode == 0:
        print(f"PDF: {pdf_out} ({pdf_out.stat().st_size//1024} KB)")
    else:
        print("PDF FAILED:\n", r.stderr[-1500:])


if __name__ == "__main__":
    main()
