"""Shared utilities for agent adapter shims.

- `.env` loader (no python-dotenv dep)
- HPO -> human-readable phrase rendering
- `case_to_question(case)` -> the free-text DDx prompt all three adapters use
- `parse_ranked_top5(text)` -> regex parser for "1. Name" style lists
- `map_names_to_ids(names)` -> use harness.pmc_oa.orphanet to map names to ORPHA/OMIM IDs
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Tuple

from harness.canonical_case import CanonicalCase, HpoTerm
from harness.logging.openrouter_wrapper import get_price
from harness.logging.schema import CostBreakdown
from harness.pmc_oa.orphanet import map_diagnosis, parse_orphadata

PROJECT_ROOT = Path("/Users/yutianzhao/Desktop/RDAgentBenchmark")
ENV_PATH = PROJECT_ROOT / ".env"


# 2026-05-19 — Unified reasoning-effort propagation for subprocess adapters.
# GPT-5 default `reasoning_effort` (high/medium) burns the entire `max_tokens`
# budget on hidden chain-of-thought, leaving `content=null` / timeout. Each
# subprocess agent runs in its own venv with its own LLM client (openai SDK
# 0.27 / 0.28 / 1.x or LiteLLM via swarms) and does NOT go through our
# `openrouter_wrapper.openrouter_chat`. Convention: the harness adapter shim
# sets `OPENROUTER_REASONING_EFFORT=minimal` in the subprocess env when the
# backbone is a reasoning model (GPT-5, OpenAI o-series); the vendor code
# reads that env var at the LLM call site and forwards it via the SDK's
# `extra_body={"reasoning": {"effort": ...}}` (openai) or `reasoning_effort=`
# (LiteLLM) parameter. See `round2_worklog.md` § Retrospective Checkpoint #4.
def reasoning_effort_for_backbone(backbone_id: str) -> Optional[str]:
    """Return the reasoning_effort value to propagate to a subprocess agent.

    For reasoning models that default to a non-minimal effort and therefore
    burn the entire `max_tokens` budget on hidden thinking, we force
    `minimal`. For everything else (Gemini, DeepSeek non-thinking, etc.),
    return None — let the model use its provider default.
    """
    if not backbone_id:
        return None
    bb = backbone_id.lower()
    # GPT-5 family + OpenAI o-series (o1, o3, o4-mini, etc.) are the known
    # reasoning models on OpenRouter that need this override.
    if "gpt-5" in bb or "openai/o" in bb or bb.startswith("o1") or bb.startswith("o3"):
        return "minimal"
    # 2026-05-20 NOTE: GLM-5 is also a reasoning model but does NOT respect
    # reasoning_effort=minimal (verified: still emits 483 reasoning_tokens).
    # GLM-5 needs max_tokens bumped to ~3000+ instead. We don't currently
    # have a clean adapter-side mechanism for that, so GLM-5 is not yet
    # integrated as a paper-grade backbone. Future work.
    return None


# 2026-07-03 — DeepSeek-V4-Pro root-cause fix (round2_worklog Retrospective #8).
# V4-Pro is a heavy reasoning model that emits *unbounded* hidden reasoning
# tokens and, unlike GPT-5, does NOT honor ANY reasoning throttle — verified on
# a hard synthesiser prompt (N=3 each):
#   reasoning={effort:minimal|low}  → still burns the full budget, content empty
#   reasoning={max_tokens:200}      → ignored, burns 1773-2000, 2/3 empty
#   max_tokens=2500 (no throttle)   → reasoning eats all 2500, 4/4 empty
#   max_tokens=4000                 → 3/4 ok but 1/4 still eats all 4000
#   reasoning={enabled:false}       → rt=0, 3/3 content, 1.9s  ← THE FIX
# The subprocess baselines size max_tokens for non-reasoning models
# (agentclinic doctor turn = 200; medagents synthesiser = 600). V4-Pro's
# reasoning consumes that entire budget so `content` returns None/empty, which
# the vendored code then retries 30x (agentclinic → timeout) or fails to parse
# (medagents → "No ranked lines"). Because the reasoning is unbounded, bumping
# max_tokens is a losing game — the only clean lever is to *disable* reasoning
# via reasoning={"enabled": false}. This is the same "reasoning-off / fast"
# configuration we run GPT-5 under (effort=minimal), applied consistently for
# cross-backbone fairness + tractability. We propagate the directive via
# OPENROUTER_REASONING_DISABLE=1; the vendored SDK call sites then send
# reasoning={"enabled": false} (taking precedence over any effort value).
# A secondary OPENROUTER_MAX_TOKENS_FLOOR is kept as belt-and-suspenders (with
# reasoning off, rt=0 so the small local max_tokens already suffices; the floor
# only matters if a future model partially reasons). Documented in
# docs/baseline_repro/{agentclinic,medagents,mdagents}.md and §5.2 of the paper.
_MAX_TOKENS_FLOOR = 2500


def reasoning_disabled_for_backbone(backbone_id: str) -> bool:
    """Return True for heavy reasoning backbones that ignore reasoning_effort
    and must have reasoning fully disabled (reasoning={"enabled": false}) to
    emit content within the subprocess baselines' small max_tokens budgets.

    Currently DeepSeek-V4-Pro (and, prospectively, GLM-5). GPT-5/o-series are
    handled via reasoning_effort_for_backbone (they honor effort=minimal);
    Gemini and V4-Flash emit few/no reasoning tokens and need neither.
    """
    if not backbone_id:
        return False
    bb = backbone_id.lower()
    return "deepseek-v4-pro" in bb or "glm-5" in bb


def max_tokens_floor_for_backbone(backbone_id: str) -> Optional[int]:
    """Secondary safety floor for max_tokens on heavy reasoners. With reasoning
    disabled (see reasoning_disabled_for_backbone) this is largely vestigial,
    but it guards a future model that only partially honors the disable flag.
    """
    if not backbone_id:
        return None
    bb = backbone_id.lower()
    if "deepseek-v4-pro" in bb or "glm-5" in bb:
        return _MAX_TOKENS_FLOOR
    return None


def load_dotenv(path: Path = ENV_PATH) -> dict[str, str]:
    """Minimal .env loader -> mutates os.environ for the current process.

    Returns the parsed dict. Lines starting with '#' or empty are skipped.
    Values are NOT shell-expanded; trailing comments on a line are stripped.
    """
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        # strip trailing comment (after a space-#)
        val = val.strip()
        # don't strip '#' inside the value (api keys may contain it? unlikely
        # — but be safe and only strip when '#' is preceded by whitespace)
        if " #" in val:
            val = val.split(" #", 1)[0].rstrip()
        # strip optional surrounding quotes
        if (val.startswith('"') and val.endswith('"')) or (
            val.startswith("'") and val.endswith("'")
        ):
            val = val[1:-1]
        out[key] = val
        # don't clobber if already set (allow shell-level overrides)
        os.environ.setdefault(key, val)
    return out


def hpo_terms_to_text(terms: List[HpoTerm]) -> str:
    """Render a list of HpoTerm into a human-readable phenotype string.

    Falls back to bare IDs when label is missing. Marks negated terms.
    """
    if not terms:
        return "(no phenotype terms provided)"
    parts: List[str] = []
    for t in terms:
        label = t.label or t.id
        if t.negated:
            parts.append(f"NOT {label} ({t.id})")
        else:
            parts.append(f"{label} ({t.id})")
    return "; ".join(parts)


def case_to_question(case: CanonicalCase, eval_mode: str = "gold_hpo") -> str:
    """Convert a CanonicalCase into a free-text DDx prompt.

    Used by all 3 adapters (mdagents, medagents, agentclinic). Returns a
    self-contained question string that asks for a top-5 ranked DDx list in
    the canonical '1. Name' line format.
    """
    parts: List[str] = []

    if case.demographics and (
        case.demographics.age_at_onset_years is not None
        or case.demographics.sex
        or case.demographics.ancestry
    ):
        demo_bits = []
        if case.demographics.age_at_onset_years is not None:
            demo_bits.append(f"age at onset {case.demographics.age_at_onset_years} y")
        if case.demographics.sex:
            demo_bits.append(case.demographics.sex)
        if case.demographics.ancestry:
            demo_bits.append(case.demographics.ancestry)
        if demo_bits:
            parts.append("Demographics: " + ", ".join(demo_bits) + ".")

    # Prefer free text if provided (rare for HPO-only datasets like RareBench)
    if eval_mode == "end_to_end" and case.free_text_vignette:
        parts.append("Clinical vignette: " + case.free_text_vignette.strip())
    elif case.gold_hpo_terms:
        parts.append(
            "Clinical phenotypes (HPO): "
            + hpo_terms_to_text(case.gold_hpo_terms)
            + "."
        )
    elif case.synthetic_vignette:
        parts.append("Clinical vignette: " + case.synthetic_vignette.strip())
    elif case.free_text_vignette:
        parts.append("Clinical vignette: " + case.free_text_vignette.strip())

    parts.append(
        "Task: What rare disease best explains these findings? "
        "List the top 5 ranked candidate diagnoses, most likely first. "
        "Use the exact format '1. <Disease Name>' (one per line), "
        "followed by a single short rationale sentence. "
        "Use canonical disease names that appear in Orphanet / OMIM "
        "(no acronyms unless universally standard, e.g., 'CADASIL')."
    )
    return "\n\n".join(parts)


# ---------- output parsing ----------

# Match lines like "1. Disease Name" or "1) Disease Name" or "**1. Disease Name**"
_RANK_LINE_RE = re.compile(
    r"^\s*(?:\*\*|__)?\s*(\d+)[\.\)]\s*(?:\*\*|__)?\s*(.+?)\s*(?:\*\*|__)?\s*$"
)


_DDX_HEADER_RE = re.compile(
    r"(differential\s+diagnos|candidate\s+diagnos|ranked\s+(?:list|diagnos)|top[-\s]?\d+|"
    r"most\s+likely\s+diagnos|final\s+(?:ranking|differential)|"
    r"\branked\b.*\bdiagnos|here\s+(?:are\s+)?the\s+(?:top|ranked))",
    re.IGNORECASE,
)

_NON_DISEASE_PREFIX = (
    "laboratory evidence", "evidence of", "negative for", "positive for",
    "the patient", "this patient", "both ", "either ", "while ", "however",
    "additionally", "furthermore", "in addition", "moreover", "given the",
    "based on", "considering", "the combination", "the presence",
    "the absence", "the triad", "progressive ", "severe ", "lab work",
    "labs show", "biopsy ", "imaging ",
)


def _looks_like_disease_name(name: str) -> bool:
    """Heuristic to reject prose / clinical-feature strings captured as 'disease'."""
    n = (name or "").strip()
    if not n:
        return False
    n_lower = n.lower()
    # 1+ disease names rarely exceed 10 words (e.g. "Hereditary multiple
    # osteochondromas with cerebral atrophy" = 7).
    if len(n.split()) > 12:
        return False
    # Reject obvious prose openings.
    if any(n_lower.startswith(p) for p in _NON_DISEASE_PREFIX):
        return False
    # Reject items with embedded full-stop / semicolon (likely two sentences)
    if "." in n[:-1] or ";" in n:
        return False
    return True


def parse_ranked_top5(text: str, k: int = 5) -> List[str]:
    """Extract a top-K ranked list of disease names from free-text output.

    Strategy (revised 2026-05-19):
    1. Prefer a numbered list that immediately follows a 'differential
       diagnosis' / 'candidate' / 'top-5' / 'ranked' section header.
    2. Fall back to the LAST consecutive numbered block (LLM typically
       wraps with a final ranking).
    3. Drop entries that look like prose / clinical features rather than
       disease names (length > 12 words, prose openings, embedded periods).

    This fixes a vicious bug where mdagents on DeepSeek interpreted a
    clinical-feature triad ('1. Poikiloderma 2. Neurological regression
    3. Laboratory evidence of ...') as a top-3 differential.
    """
    if not text:
        return []
    seen: dict[int, str] = {}
    # Pre-pass: convert inline '1. X 2. Y ...' into one-rank-per-line for the
    # main regex by splitting at ' (?=\d+[\.\)])'. Only triggered when the
    # text contains <= 1 newline AND contains a numbered marker pattern.
    if text.count("\n") <= 1 and re.search(r"\b\d+[\.\)]", text):
        text = re.sub(r"\s+(?=\d+[\.\)]\s)", "\n", text)
    # Cut off trailing rationale sections (case-insensitive) that often appear
    # in the same line as the last ranked item (e.g. "5. X Rationale: ...").
    text = re.sub(
        r"\s+(Rationale|Reasoning|Justification|Note|Explanation|Summary)\s*:?",
        "\n",
        text,
        flags=re.IGNORECASE,
    )

    # Strategy (2026-05-19 v2 fix):
    #   1) try parsing the full text first.
    #   2) if it returns < 3 disease names (suggesting we may have absorbed
    #      a feature-triad or evidence list), retry with the LAST DDx-header
    #      section. The header-aware path stays useful for DeepSeek-style
    #      "feature triad then differential" outputs, while medagents-style
    #      `1. Disease\n2. Disease\n... Rationale: ...` outputs parse cleanly
    #      via the full-text path even when "most likely diagnosis" appears
    #      mid-rationale.
    def _scan(scope_text: str) -> dict[int, str]:
        out: dict[int, str] = {}
        for ln in scope_text.splitlines():
            m = _RANK_LINE_RE.match(ln)
            if not m:
                continue
            try:
                rk = int(m.group(1))
            except ValueError:
                continue
            if not (1 <= rk <= 20):
                continue
            raw = m.group(2)
            raw = re.sub(r"(\*\*|__|`)", "", raw)
            for sep in [" — ", " – ", " - ", ":"]:
                if sep in raw:
                    raw = raw.split(sep, 1)[0]
                    break
            raw = re.sub(r"\s*\([^)]*\)\s*$", "", raw).strip()
            raw = raw.rstrip(":.;,").strip()
            if _looks_like_disease_name(raw) and rk not in out:
                out[rk] = raw
        return out

    seen = _scan(text)
    # Fallback: if first-pass found very few, try header-aware retry
    if len(seen) < 3:
        header_pos = -1
        for m in _DDX_HEADER_RE.finditer(text):
            header_pos = m.start()
        if header_pos >= 0:
            seen_alt = _scan(text[header_pos:])
            if len(seen_alt) > len(seen):
                seen = seen_alt
    if not seen:
        return []
    ordered = [seen[r] for r in sorted(seen) if seen[r]]
    return ordered[:k]


# ---------- orphanet mapping (lazy-cached) ----------


@lru_cache(maxsize=1)
def _orpha_tables():
    return parse_orphadata()


def map_names_to_ids(names: List[str]) -> List[str]:
    """Map disease name strings to canonical disease IDs.

    Returns one ID per input name (in same order). Prefers ORPHA, falls back
    to the first cross-referenced OMIM, falls back to the literal name when
    no match. Drops nothing — caller expects parallel lists.
    """
    if not names:
        return []
    tables = _orpha_tables()
    out: List[str] = []
    for nm in names:
        mapped = map_diagnosis(nm, tables)
        if mapped.get("orpha_id"):
            out.append(mapped["orpha_id"])
        elif mapped.get("omim_ids"):
            out.append(mapped["omim_ids"][0])
        else:
            # Keep the original name so downstream can audit unmatched cases.
            out.append(nm)
    return out


def map_names_to_ids_with_variants(names: List[str], tie_score_floor: float = 88.0):
    """Map disease names to (best_id, list_of_tied_id_variants).

    Returns two parallel lists of the same length as `names`:
      - best_ids:  primary canonical ID per name (same as map_names_to_ids).
      - variants:  list[list[str]] where variants[i] is **all** ORPHA IDs whose
                   fuzzy score against names[i] is within `tie_score_floor` of
                   the top score, plus the literal `names[i]` itself. Always
                   includes best_ids[i] at index 0.

    This is the 2026-05-19 fix for the RareBench fuzzy-tie problem: when a
    generic disease name like "Methylmalonic Acidemia" fuzzy-matches multiple
    ORPHA subtypes at score 90 (ORPHA:26, ORPHA:27, ORPHA:280183), the
    evaluator should accept ANY of the tied IDs as a hit.
    """
    if not names:
        return [], []
    tables = _orpha_tables()
    best_ids: List[str] = []
    variants: List[List[str]] = []
    for nm in names:
        mapped = map_diagnosis(nm, tables, return_top_k=5)
        best_id = (
            mapped.get("orpha_id")
            or (mapped["omim_ids"][0] if mapped.get("omim_ids") else nm)
        )
        best_ids.append(best_id)
        # Collect tied ORPHA candidates (score within tie_score_floor of top)
        cands = mapped.get("top_candidates", []) or []
        if not cands:
            variants.append([best_id, nm] if nm != best_id else [best_id])
            continue
        top_score = max((c.get("score", 0.0) for c in cands), default=0.0)
        floor = max(tie_score_floor, top_score - 5.0)  # within 5 pts of top OR ≥ floor
        tied = [c["orpha_id"] for c in cands if c.get("score", 0.0) >= floor and c.get("orpha_id")]
        # Always include best_id and the literal name (latter useful for NL eval path)
        if best_id not in tied:
            tied.insert(0, best_id)
        if nm not in tied:
            tied.append(nm)
        variants.append(tied)
    return best_ids, variants


# ---------- crude token estimation ----------

# When the LLM gateway doesn't return usage stats, we fall back to a rough
# character-based heuristic so the PredictionLog.cost block is non-zero.
def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


# ---------- cost auto-fill (FIX D2) ----------


def compute_cost_usd(
    backbone_id: str, prompt_tokens: int, completion_tokens: int
) -> float:
    """Look up per-1M-token prices for `backbone_id` and return USD cost.

    Uses `harness.logging.openrouter_wrapper.get_price` which already handles
    the `openrouter/<provider>/<model>` prefix-stripping.

    Returns 0.0 when the model is unknown (caller can audit by checking that
    prompt_tokens > 0 but cost_usd == 0 in the JSONL).
    """
    p_in, p_out = get_price(backbone_id)
    return (prompt_tokens * p_in + completion_tokens * p_out) / 1_000_000


def fill_cost_from_tokens(
    cost: "CostBreakdown",
    backbone_id: str,
    *,
    overwrite: bool = True,
) -> "CostBreakdown":
    """Mutate `cost.cost_usd` in-place based on its existing token counts
    and `backbone_id`. Sets `provider="openrouter"` if not already set.

    Args:
        cost: a `CostBreakdown` (typically taken from `log.cost`).
        backbone_id: e.g. ``"openrouter/google/gemini-3-flash-preview"``.
        overwrite: if True (default), always recompute; if False, only fill
            when current ``cost_usd == 0``.

    Returns the same `cost` object for chaining.
    """
    if not overwrite and cost.cost_usd > 0:
        return cost
    cost.cost_usd = compute_cost_usd(
        backbone_id, cost.prompt_tokens, cost.completion_tokens
    )
    if not cost.provider:
        cost.provider = "openrouter"
    return cost


__all__ = [
    "load_dotenv",
    "case_to_question",
    "hpo_terms_to_text",
    "parse_ranked_top5",
    "map_names_to_ids",
    "map_names_to_ids_with_variants",
    "estimate_tokens",
    "compute_cost_usd",
    "fill_cost_from_tokens",
    "PROJECT_ROOT",
]
