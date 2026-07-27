"""HPO phrase → canonical HP:xxxxxxx normalization.

Minimal Phase-1 implementation per round2_plan.md §3.

The extractors (LLMControlAdapter.extract_phenotypes, RDMAAdapter.extract_phenotypes,
DeepRare's hpo_extractor) return free-text phrases (e.g., "progressive proximal
muscle weakness"). To compute Pillar-1 P/R/F1 against `case.gold_hpo_terms`
(structured HP:\\d{7}), we need a phrase → HP-ID step.

Strategy:
1. Build an index of `{normalized_phrase: hp_id}` from `data/hpo/hp.obo` using
   the term `name` field plus all `synonym:` lines (EXACT / NARROW / RELATED).
2. For each input phrase: try exact (case-insensitive, punctuation-stripped)
   first; fall back to rapidfuzz token_set_ratio against the index keys with
   a configurable threshold (default 90 — same as plan.md §3.3.).
3. Return at most one HP-ID per phrase (or None if no match passes threshold).

This is **not** a state-of-the-art ontology mapper — RAG-HPO / SciSpacy would
do better — but it's sufficient for an MVP P1 metric without external deps.

API:
    normalize_phrase(phrase, threshold=90) -> Optional[str]
    normalize_phrases(phrases, threshold=90) -> List[Optional[str]]
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from rapidfuzz import fuzz, process

    _HAS_RAPIDFUZZ = True
except ImportError:  # pragma: no cover
    _HAS_RAPIDFUZZ = False


# Repo-relative default with env override (portable across machines; the
# hardcoded Mac path was a non-portable landmine, same class as orphanet.py's
# DEFAULT_ORPHA_XML). Override with HP_OBO_PATH.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OBO = os.environ.get(
    "HP_OBO_PATH", str(_PROJECT_ROOT / "data" / "hpo" / "hp.obo")
)

_PUNCT_RE = re.compile(r"[^\w\s-]")
_WS_RE = re.compile(r"\s+")


def _normalize_key(s: str) -> str:
    """Lowercase, strip punctuation except hyphen, collapse whitespace."""
    s = s.lower().strip()
    s = _PUNCT_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


def _parse_obo_phrase_index(path: str = DEFAULT_OBO) -> Dict[str, str]:
    """Parse hp.obo into {normalized phrase: hp_id}.

    Uses term `name` plus all `synonym: "..." ...` lines (EXACT/NARROW/RELATED).
    Skips obsolete terms. If two terms share a synonym key, first one wins
    (deterministic by file order — close enough for v1).
    """
    raw = Path(path).read_text()
    out: Dict[str, str] = {}
    id_re = re.compile(r"^id:\s*(HP:\d{7})", re.M)
    name_re = re.compile(r"^name:\s*(.+)$", re.M)
    syn_re = re.compile(r'^synonym:\s*"([^"]+)"', re.M)
    obs_re = re.compile(r"^is_obsolete:\s*true", re.M | re.I)

    for block in re.split(r"\n\[Term\]\n", raw):
        if "id: HP:" not in block:
            continue
        if obs_re.search(block):
            continue
        mid = id_re.search(block)
        if not mid:
            continue
        hp_id = mid.group(1)
        mname = name_re.search(block)
        if mname:
            key = _normalize_key(mname.group(1))
            if key and key not in out:
                out[key] = hp_id
        for m in syn_re.finditer(block):
            key = _normalize_key(m.group(1))
            if key and key not in out:
                out[key] = hp_id
    return out


@lru_cache(maxsize=1)
def _phrase_index() -> Tuple[Dict[str, str], List[str]]:
    """Cached: (phrase_dict, sorted phrase keys list for rapidfuzz)."""
    d = _parse_obo_phrase_index()
    return d, list(d.keys())


def normalize_phrase(phrase: str, threshold: int = 90) -> Optional[str]:
    """Map one free-text phenotypic phrase to a canonical HP:xxxxxxx, or None.

    Args:
        phrase: e.g., "progressive proximal muscle weakness"
        threshold: rapidfuzz token_set_ratio threshold (0-100). Default 90.

    Returns:
        HP:xxxxxxx string, or None if no match passes threshold.
    """
    if not phrase or not phrase.strip():
        return None
    key = _normalize_key(phrase)
    if not key:
        return None
    index, keys = _phrase_index()
    # 1. exact lookup
    if key in index:
        return index[key]
    # 2. fuzzy
    if not _HAS_RAPIDFUZZ:
        return None
    match = process.extractOne(
        key, keys, scorer=fuzz.token_set_ratio, score_cutoff=threshold
    )
    if match is None:
        return None
    matched_key, _score, _idx = match
    return index.get(matched_key)


def normalize_phrases(
    phrases: List[str], threshold: int = 90
) -> List[Optional[str]]:
    """Vectorized normalize_phrase. Returns parallel list (None for misses)."""
    return [normalize_phrase(p, threshold=threshold) for p in phrases]


__all__ = ["normalize_phrase", "normalize_phrases"]
