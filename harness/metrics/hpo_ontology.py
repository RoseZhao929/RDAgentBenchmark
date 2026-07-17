"""HPO ontology graph for ancestor / descendant matching (Tier 3 phenotype metric).

Loads `hp.obo` once and builds a directed graph of HPO terms with `is_a` edges
parsed. Provides:
- `ancestors(hp_id) -> set[str]` — all ancestor HPO IDs (including self)
- `descendants(hp_id) -> set[str]` — all descendants (including self)
- `is_ancestor_of(a, b) -> bool`  — True iff a is an ancestor of b
- `info_content(hp_id, frequencies) -> float` — IC-weighted similarity (placeholder)

For RAG-HPO-style scoring (where 95.2% of false positives are "ancestor of true
term"), this enables giving partial credit to over-broad term predictions.

Source: https://purl.obolibrary.org/obo/hp.obo (CC-BY-4.0)
Local path: `data/hpo/hp.obo`
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Iterable

DEFAULT_OBO = "/Users/yutianzhao/Desktop/RDAgentBenchmark/data/hpo/hp.obo"

# regex for `[Term]` blocks and their fields
_ID_RE = re.compile(r"^id:\s*(HP:\d{7})", re.M)
_PARENT_RE = re.compile(r"^is_a:\s*(HP:\d{7})", re.M)
_NAME_RE = re.compile(r"^name:\s*(.+)$", re.M)
_OBSOLETE_RE = re.compile(r"^is_obsolete:\s*true", re.M | re.I)


def _parse_obo(path: str | Path = DEFAULT_OBO) -> dict:
    """Parse hp.obo into a dict {hp_id: {"name": str, "parents": [hp_ids]}}.

    Skips obsolete terms.
    """
    raw = Path(path).read_text()
    terms: dict[str, dict] = {}

    # split on blank line + [Term] header
    for block in re.split(r"\n\[Term\]\n", raw):
        if "id: HP:" not in block:
            continue
        if _OBSOLETE_RE.search(block):
            continue
        m_id = _ID_RE.search(block)
        if not m_id:
            continue
        hp_id = m_id.group(1)
        name_m = _NAME_RE.search(block)
        parents = _PARENT_RE.findall(block)
        terms[hp_id] = {"name": name_m.group(1).strip() if name_m else None,
                        "parents": parents}
    return terms


@lru_cache(maxsize=1)
def _load_graph() -> dict:
    """Load + build ancestor/descendant closures (cached per process)."""
    terms = _parse_obo()

    # build parent → set(children)
    children: dict[str, set[str]] = {hp: set() for hp in terms}
    for hp, info in terms.items():
        for p in info["parents"]:
            if p in children:
                children[p].add(hp)

    # ancestor closure via memoized DFS
    anc_cache: dict[str, set[str]] = {}

    def ancestors_of(hp: str) -> set[str]:
        if hp in anc_cache:
            return anc_cache[hp]
        out = {hp}
        for p in terms.get(hp, {}).get("parents", []):
            if p in terms:
                out |= ancestors_of(p)
        anc_cache[hp] = out
        return out

    # descendant closure
    desc_cache: dict[str, set[str]] = {}

    def descendants_of(hp: str) -> set[str]:
        if hp in desc_cache:
            return desc_cache[hp]
        out = {hp}
        for c in children.get(hp, set()):
            out |= descendants_of(c)
        desc_cache[hp] = out
        return out

    # eagerly compute for all terms — ~17k terms is fast
    for hp in terms:
        ancestors_of(hp)
        descendants_of(hp)

    return {
        "terms": terms,
        "children": children,
        "ancestors_of": anc_cache,
        "descendants_of": desc_cache,
    }


def ancestors(hp_id: str) -> set[str]:
    """All HPO IDs that are ancestors of hp_id (including hp_id itself)."""
    return _load_graph()["ancestors_of"].get(hp_id, {hp_id})


def descendants(hp_id: str) -> set[str]:
    """All HPO IDs that are descendants of hp_id (including hp_id itself)."""
    return _load_graph()["descendants_of"].get(hp_id, {hp_id})


def is_ancestor_of(a: str, b: str) -> bool:
    """True iff `a` is an ancestor of `b` (a more general than b)."""
    return a in ancestors(b)


def name_of(hp_id: str) -> str | None:
    """English label for an HPO ID."""
    return _load_graph()["terms"].get(hp_id, {}).get("name")


def match_with_ancestor_credit(
    predicted: Iterable[str], gold: Iterable[str]
) -> tuple[int, int, int]:
    """Tier 3 phenotype matching with ancestor credit.

    Returns (tp, fp, fn) where:
    - tp: a predicted term that is an ancestor-or-equal of any gold term
    - fp: a predicted term with no such match
    - fn: a gold term with no predicted ancestor-or-equal

    This gives credit for over-broad predictions (e.g. predicting
    "abnormality of brain morphology" when gold is "microcephaly").
    """
    pred = list(predicted)
    gold = list(gold)
    pred_set = set(pred)
    gold_set = set(gold)

    tp = 0
    for p in pred_set:
        if any(is_ancestor_of(p, g) for g in gold_set):
            tp += 1
    fp = len(pred_set) - tp

    matched_gold = 0
    for g in gold_set:
        if any(is_ancestor_of(p, g) for p in pred_set):
            matched_gold += 1
    fn = len(gold_set) - matched_gold

    return tp, fp, fn


__all__ = [
    "ancestors",
    "descendants",
    "is_ancestor_of",
    "name_of",
    "match_with_ancestor_credit",
]
