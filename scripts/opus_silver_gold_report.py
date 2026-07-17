"""Build SILVER_GOLD_REPORT.md from silver_gold_opus.jsonl.

Stats reported
--------------
- N cases / parse-fail count
- Mean & median HPO phenotypes/case (Opus)
- Mean & median HPO phenotypes/case (Gemini, from 06_candidates_for_review.jsonl)
- Mean final_diagnosis length (chars)
- Total actual cost vs $20 cap
- Per-case overlap between Opus phrases and Gemini phrases (case-insensitive
  substring match in either direction — rough check only). Reports mean
  Jaccard, mean recall-of-Gemini-by-Opus, and mean precision (Opus phrases
  that the original Gemini list confirms).
- Top examples of largest disagreement (largest |Opus_n - Gemini_n|, plus
  cases where final_diagnosis differs from matched_orpha_name).

Output: data/round2/phase1/SILVER_GOLD_REPORT.md
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CANDIDATES_PATH = (
    PROJECT_ROOT / "data" / "pmc_oa_holdout" / "06_candidates_for_review.jsonl"
)
OPUS_PATH = PROJECT_ROOT / "data" / "round2" / "phase1" / "silver_gold_opus.jsonl"
REPORT_PATH = PROJECT_ROOT / "data" / "round2" / "phase1" / "SILVER_GOLD_REPORT.md"

NOMINAL_CAP_USD = 20.0


def _norm_phrase(s: str) -> str:
    """Lower, strip, collapse whitespace, drop trailing punctuation."""
    s = (s or "").lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[\.,;:]+$", "", s)
    return s


def _tokens(s: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", _norm_phrase(s)) if len(t) >= 3}


def _fuzzy_match(a: str, b: str) -> bool:
    """Loose match: substring either way, or token-jaccard >= 0.5."""
    na, nb = _norm_phrase(a), _norm_phrase(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if na in nb or nb in na:
        return True
    ta, tb = _tokens(na), _tokens(nb)
    if not ta or not tb:
        return False
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union >= 0.5


def _overlap_metrics(opus_phrases: list[str], gemini_phrases: list[str]) -> dict:
    """Compute Jaccard, recall (Gemini covered by Opus), precision (Opus
    confirmed by Gemini). Returns 0s for empty sets where appropriate.
    """
    if not opus_phrases and not gemini_phrases:
        return {"jaccard": None, "recall_gem": None, "precision_op": None}
    matched_op: set[int] = set()
    matched_gem: set[int] = set()
    for i, op in enumerate(opus_phrases):
        for j, ge in enumerate(gemini_phrases):
            if j in matched_gem:
                continue
            if _fuzzy_match(op, ge):
                matched_op.add(i)
                matched_gem.add(j)
                break
    tp = len(matched_op)
    fp = len(opus_phrases) - tp
    fn = len(gemini_phrases) - len(matched_gem)
    jacc = tp / (tp + fp + fn) if (tp + fp + fn) else None
    rec = len(matched_gem) / len(gemini_phrases) if gemini_phrases else None
    prec = tp / len(opus_phrases) if opus_phrases else None
    return {"jaccard": jacc, "recall_gem": rec, "precision_op": prec}


def main() -> int:
    if not OPUS_PATH.exists():
        print(f"[FATAL] {OPUS_PATH} missing — run opus_silver_gold_pilot.py first")
        return 2

    # Index original candidates by pmc_id for Gemini phrases.
    gem_by_pmc: dict[str, dict] = {}
    with CANDIDATES_PATH.open() as f:
        for line in f:
            r = json.loads(line)
            gem_by_pmc[str(r["pmc_id"])] = r

    rows: list[dict] = []
    with OPUS_PATH.open() as f:
        for line in f:
            r = json.loads(line)
            rows.append(r)

    n = len(rows)
    n_parse_fail = sum(1 for r in rows if r.get("_error") or r.get("silver_gold") is None)
    n_ok = n - n_parse_fail

    total_cost = sum(float(r.get("cost_usd") or 0.0) for r in rows)
    total_in = sum(int(r.get("tokens_in") or 0) for r in rows)
    total_out = sum(int(r.get("tokens_out") or 0) for r in rows)

    opus_hpo_counts: list[int] = []
    gem_hpo_counts: list[int] = []
    diag_lens: list[int] = []
    jaccards: list[float] = []
    recalls: list[float] = []
    precisions: list[float] = []

    # Track disagreement records for the "surprising cases" section.
    disagreements: list[dict] = []  # large |Opus - Gemini| count delta
    diag_disagreements: list[dict] = []  # final_diagnosis != matched_orpha_name

    for r in rows:
        sg = r.get("silver_gold")
        if not sg:
            continue
        opus_phrases = [p.get("phrase", "") for p in (sg.get("hpo_phenotypes") or []) if p.get("phrase")]
        opus_hpo_counts.append(len(opus_phrases))

        pmc_id = str(r.get("pmc_id"))
        gem = gem_by_pmc.get(pmc_id, {})
        gem_phrases = list(gem.get("hpo_phenotypes") or [])
        gem_hpo_counts.append(len(gem_phrases))

        final_dx = (sg.get("final_diagnosis") or "").strip()
        diag_lens.append(len(final_dx))

        m = _overlap_metrics(opus_phrases, gem_phrases)
        if m["jaccard"] is not None:
            jaccards.append(m["jaccard"])
        if m["recall_gem"] is not None:
            recalls.append(m["recall_gem"])
        if m["precision_op"] is not None:
            precisions.append(m["precision_op"])

        delta = abs(len(opus_phrases) - len(gem_phrases))
        disagreements.append(
            {
                "pmc_id": pmc_id,
                "orpha_name": gem.get("matched_orpha_name"),
                "opus_n": len(opus_phrases),
                "gem_n": len(gem_phrases),
                "delta": delta,
                "jaccard": m["jaccard"],
                "opus_dx": final_dx,
            }
        )

        gem_dx = (gem.get("matched_orpha_name") or "").strip().lower()
        opus_dx_l = final_dx.lower()
        if gem_dx and opus_dx_l and gem_dx not in opus_dx_l and opus_dx_l not in gem_dx:
            diag_disagreements.append(
                {
                    "pmc_id": pmc_id,
                    "gemini_dx_orpha": gem.get("matched_orpha_name"),
                    "opus_dx": final_dx,
                    "extracted_dx": gem.get("extracted_diagnosis"),
                }
            )

    def fmt_mean(xs: list[float], digits: int = 2) -> str:
        if not xs:
            return "n/a"
        return f"{statistics.mean(xs):.{digits}f}"

    def fmt_median(xs: list[float], digits: int = 1) -> str:
        if not xs:
            return "n/a"
        return f"{statistics.median(xs):.{digits}f}"

    # Sort disagreements by descending delta and pick top 10.
    disagreements_sorted = sorted(disagreements, key=lambda x: -x["delta"])
    top_delta = disagreements_sorted[:10]

    # Build report
    lines: list[str] = []
    lines.append("# Silver-Gold (Opus 4.7) — Round 2 Phase 1\n")
    lines.append(
        "Generated by `scripts/opus_silver_gold_report.py` from "
        "`silver_gold_opus.jsonl`.\n"
    )
    lines.append("## Purpose\n")
    lines.append(
        "Independent gold HPO + final-diagnosis annotations for 100 PMC OA "
        "case excerpts, produced by Claude Opus 4.7 (independent of our "
        "test backbones Gemini 3 Flash / DeepSeek v3.2 / GPT-5). Replaces "
        "the leaky-tautology setup where P1 agents extracted HPO from a "
        "vignette synthesized from the very gold labels they were asked to "
        "recover.\n"
    )

    lines.append("## Run summary\n")
    lines.append(f"- N cases attempted: **{n}**")
    lines.append(f"- Parse failures (JSON decode / refusal / API error): **{n_parse_fail}**")
    lines.append(f"- Successful silver-gold records: **{n_ok}**")
    lines.append(f"- Extractor model: `anthropic/claude-opus-4.7` (OpenRouter; backend model `claude-4.7-opus-20260416`)")
    lines.append("")
    lines.append("## Cost\n")
    lines.append(f"- Total cost (OpenRouter `usage.cost`): **${total_cost:.4f}**")
    lines.append(f"- Nominal cap: ${NOMINAL_CAP_USD:.2f}; hard runtime cap: $15.00")
    lines.append(f"- Cost / successful case: ${(total_cost / n_ok) if n_ok else 0.0:.4f}")
    lines.append(f"- Total tokens — input: {total_in:,}  output: {total_out:,}")
    lines.append("")

    lines.append("## HPO yield (per case)\n")
    lines.append("| Source | Mean | Median | Min | Max |")
    lines.append("|---|---:|---:|---:|---:|")
    if opus_hpo_counts:
        lines.append(
            f"| Opus 4.7 (this run) | {fmt_mean(opus_hpo_counts)} | "
            f"{fmt_median(opus_hpo_counts)} | {min(opus_hpo_counts)} | {max(opus_hpo_counts)} |"
        )
    if gem_hpo_counts:
        lines.append(
            f"| Gemini Flash (06_candidates) | {fmt_mean(gem_hpo_counts)} | "
            f"{fmt_median(gem_hpo_counts)} | {min(gem_hpo_counts)} | {max(gem_hpo_counts)} |"
        )
    lines.append("")
    lines.append(f"- Mean Opus-vs-Gemini phrase Jaccard (fuzzy substring / token-Jaccard >=0.5): **{fmt_mean(jaccards)}**")
    lines.append(f"- Mean recall of Gemini phrases by Opus: **{fmt_mean(recalls)}**")
    lines.append(f"- Mean precision of Opus phrases (confirmed by Gemini): **{fmt_mean(precisions)}**")
    lines.append("")

    lines.append("## Final-diagnosis text\n")
    if diag_lens:
        lines.append(
            f"- Mean length: {statistics.mean(diag_lens):.1f} chars  "
            f"(median {statistics.median(diag_lens):.1f}, min {min(diag_lens)}, max {max(diag_lens)})"
        )
    lines.append(
        f"- Cases where Opus final_diagnosis substring-disjoint from the "
        f"matched Orphanet name in `06_candidates`: **{len(diag_disagreements)}** / {n_ok}"
    )
    lines.append("")

    if diag_disagreements:
        lines.append("### Diagnosis disagreements (sample, up to 10)\n")
        lines.append("| pmc_id | Orphanet match | Opus final_diagnosis | Original extracted_dx |")
        lines.append("|---|---|---|---|")
        for d in diag_disagreements[:10]:
            lines.append(
                f"| {d['pmc_id']} | {d['gemini_dx_orpha']} | {d['opus_dx']} | "
                f"{d.get('extracted_dx')} |"
            )
        lines.append("")

    lines.append("## Cases with largest HPO-count delta vs Gemini (top 10)\n")
    lines.append("| pmc_id | Orphanet | Opus n | Gemini n | |delta| | Jaccard | Opus dx |")
    lines.append("|---|---|---:|---:|---:|---:|---|")
    for d in top_delta:
        jacc = f"{d['jaccard']:.2f}" if d.get("jaccard") is not None else "n/a"
        lines.append(
            f"| {d['pmc_id']} | {d['orpha_name']} | {d['opus_n']} | "
            f"{d['gem_n']} | {d['delta']} | {jacc} | {d['opus_dx']} |"
        )
    lines.append("")

    lines.append("## Interpretation\n")
    if jaccards:
        mean_jacc = statistics.mean(jaccards)
        mean_op = statistics.mean(opus_hpo_counts) if opus_hpo_counts else 0
        mean_gem = statistics.mean(gem_hpo_counts) if gem_hpo_counts else 0
        delta_pct = (mean_op - mean_gem) / mean_gem * 100 if mean_gem else 0
        lines.append(
            f"- Opus extracts on average **{mean_op:.1f}** HPO phrases per case "
            f"vs Gemini Flash's **{mean_gem:.1f}** ({delta_pct:+.1f}%)."
        )
        lines.append(
            f"- Mean phrase Jaccard ~{mean_jacc:.2f} (fuzzy) — well under 1.0, "
            "confirming that Opus and Gemini Flash are NOT redundant: a P1 "
            "agent that uses one as input and the other as gold will face "
            "genuine extraction signal, not leaky tautology."
        )
    lines.append(
        "- Use `silver_gold_opus.jsonl` as the **gold** in P1 free-text "
        "extraction evaluation. Test agents will run on `case_excerpt` "
        "(input) and be scored against the Opus `hpo_phenotypes` (gold)."
    )
    lines.append("")

    REPORT_PATH.write_text("\n".join(lines))
    print(f"[done] wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
