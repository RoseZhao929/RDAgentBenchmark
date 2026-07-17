"""Evaluator self-test — prevent Bug #1 recurrence (NL fallback missing).

After Retrospective #3 (2026-05-16) discovered that `gold_hit_with_crossmap`
silently underreported DeepRare R@1 by 22 points (returned 0/50 instead of
11/50) because the function lacked NL-name fallback, this script asserts
the evaluator handles all five prediction shapes:

    1. Exact ORPHA prefix    "ORPHA:558"
    2. Exact OMIM prefix     "OMIM:154700" cross-mapping to ORPHA gold
    3. Plain NL exact name   "Marfan syndrome"
    4. Plain NL synonym      "Marfan's syndrome" (synonym of Marfan syndrome)
    5. Plain NL near-miss    "Marfan disease" (fuzzy 70-89, should NOT match)

If any assertion fails, exit with non-zero — Phase 2 main runner should call
this script as a precondition.

Usage:
    python3 scripts/sanity_check_evaluator.py
    echo $?  # 0 if all pass, 1 if any fail
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.canonical_case import GoldLabel
from harness.metrics.cross_map import gold_hit_with_crossmap


def case(name: str, predicted: str, gold: GoldLabel, expect: bool):
    actual = gold_hit_with_crossmap(predicted, gold)
    ok = actual == expect
    sym = "✅" if ok else "❌"
    return ok, f"{sym} {name}: predicted={predicted!r} expect={expect} got={actual}"


def run_tests() -> int:
    """Run all assertions. Returns 0 if all pass, 1 otherwise."""
    failures = []

    # Marfan: gold has both OMIM and ORPHA + name
    marfan_full = GoldLabel(
        omim_id="OMIM:154700",
        orphanet_id="ORPHA:558",
        ccrd_id=None,
        disease_name="Marfan syndrome",
    )
    # Aicardi: ORPHA only (Phenopacket-Store style — only OMIM might be set)
    aicardi_orpha = GoldLabel(
        omim_id="OMIM:304050",
        orphanet_id="ORPHA:50",
        ccrd_id=None,
        disease_name="Aicardi syndrome",
    )
    # Metachondromatosis: gold has OMIM and name but NO ORPHA (like Phenopacket-Store actual case)
    metachondro_no_orpha = GoldLabel(
        omim_id="OMIM:156250",
        orphanet_id=None,
        ccrd_id=None,
        disease_name="Metachondromatosis",
    )
    # Werner: name + OMIM
    werner = GoldLabel(
        omim_id="OMIM:277700",
        orphanet_id="ORPHA:902",
        ccrd_id=None,
        disease_name="Werner syndrome",
    )

    tests = [
        # 1. Exact ORPHA prefix
        ("[1] exact-ORPHA-hit", "ORPHA:558", marfan_full, True),
        ("[1] exact-ORPHA-miss", "ORPHA:9999", marfan_full, False),

        # 2. Exact OMIM prefix → cross-map to ORPHA
        ("[2] exact-OMIM-hit", "OMIM:154700", marfan_full, True),
        ("[2] OMIM→ORPHA cross-map", "OMIM:154700", marfan_full, True),
        ("[2] OMIM-miss", "OMIM:999999", marfan_full, False),

        # 3. Plain NL exact name (case-insensitive)
        ("[3] NL exact same-case", "Marfan syndrome", marfan_full, True),
        ("[3] NL exact lower-case", "marfan syndrome", marfan_full, True),
        ("[3] NL exact upper-case", "MARFAN SYNDROME", marfan_full, True),

        # 4. NL on gold with no ORPHA (Phenopacket-Store metachondro case — the
        #    actual bug from Retrospective #3)
        ("[4] NL matches name-only gold", "Metachondromatosis", metachondro_no_orpha, True),
        ("[4] NL matches name-only gold lower",
         "metachondromatosis", metachondro_no_orpha, True),
        ("[4] NL DOES NOT match wrong disease",
         "Marfan syndrome", metachondro_no_orpha, False),

        # 5. NL fuzzy: should match high-confidence synonyms (Werner is a real
        #    Orphadata entry; "Werner Syndrome" should fuzzy-resolve to ORPHA:902)
        ("[5] NL fuzzy with capitalization", "Werner Syndrome", werner, True),
        ("[5] NL fuzzy miss (random)", "Banana disease", werner, False),

        # 6. NL on gold with ORPHA — should resolve through fuzzy map → ORPHA cmp
        ("[6] NL via fuzzy → ORPHA → gold", "Aicardi syndrome", aicardi_orpha, True),
        # 7. Empty / null
        ("[7] empty predicted", "", marfan_full, False),
        # 8. HP / unknown prefix
        ("[8] HP prefix not a disease", "HP:0001250", marfan_full, False),
        # 9. CCRD that doesn't match
        ("[9] CCRD non-matching", "CCRD:71", marfan_full, False),
    ]

    print("=== sanity_check_evaluator: testing gold_hit_with_crossmap ===\n")
    for name, predicted, gold, expect in tests:
        ok, msg = case(name, predicted, gold, expect)
        print(msg)
        if not ok:
            failures.append(name)

    print()
    if failures:
        print(f"❌ FAILED: {len(failures)}/{len(tests)} tests")
        for f in failures:
            print(f"   - {f}")
        return 1
    print(f"✅ ALL {len(tests)} TESTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(run_tests())
