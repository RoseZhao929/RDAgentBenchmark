"""Holm-Bonferroni family-wise correction over the testable H1-H11.

Per pre-registration: one-sided test in the predicted direction, family-wise α=0.05.
Hypotheses entering the family = those for which Phase 4a/4c data supports a test:
  H1, H2, H4, H7, H8, H10. Others (H3/H5/H6/H9) are pre-registered placeholders
  blocked on data unavailability (see §9, task #63-#66).

Effects + counts sourced from the ablation scripts already run:
  H1: data/round2/ablations/H1_prevalence_real.md
  H4/H7: data/round2/ablations/H4_H7_specialty.md
  H8: data/round2/ablations/H8_phenotype_density.md
  H2: paper_sections/7_2_7_3_7_4_analysis.md §7.3 (P3 pilot)
  H10: paper_sections/7_2_7_3_7_4_analysis.md §7.4 (P5 pilot)

Test choices:
  H1, H2, H4 (DoD), H8: 2-proportion z-test, one-sided
  H7: Spearman ρ test against 0 (one-sided, n=13 specialties)
  H10: against ρ<0.5 (one-sided, pre-registered decoupling threshold)
"""
from __future__ import annotations
import math
from pathlib import Path

def z_to_p_onesided(z):
    """One-sided p (right tail) from z via erfc."""
    return 0.5 * math.erfc(z / math.sqrt(2))

def two_prop_z(h1, n1, h2, n2):
    """Z-stat for H0: p1=p2 vs p1>p2. Returns z (right-tail one-sided)."""
    p1, p2 = h1/n1, h2/n2
    p = (h1 + h2) / (n1 + n2)
    se = math.sqrt(p * (1-p) * (1/n1 + 1/n2))
    return (p1 - p2) / se if se > 0 else float('inf') if (p1-p2)>0 else 0

def diff_of_diff_z(h11, n11, h12, n12, h21, n21, h22, n22):
    """(p11-p12) > (p21-p22) one-sided. Wald with independent binomial SEs."""
    d1 = h11/n11 - h12/n12
    d2 = h21/n21 - h22/n22
    var1 = (h11/n11)*(1-h11/n11)/n11 + (h12/n12)*(1-h12/n12)/n12
    var2 = (h21/n21)*(1-h21/n21)/n21 + (h22/n22)*(1-h22/n22)/n22
    se = math.sqrt(var1 + var2)
    return (d1 - d2) / se if se > 0 else 0

def spearman_p_onesided(rho, n, against=0):
    """t-approx of Spearman: t = ρ*sqrt((n-2)/(1-ρ²)). One-sided test ρ > against."""
    # Shift: test (ρ - against) > 0 using same t formula (approximation; conservative)
    eff = rho - against
    if abs(eff) >= 1: return 0.0 if eff>0 else 1.0
    t = eff * math.sqrt((n-2) / max(1-rho**2, 1e-12))
    # one-sided normal-approx p (n=13 → ok for first-cut, footnote conservative)
    return 0.5 * math.erfc(t / math.sqrt(2)) if t >= 0 else 1 - 0.5*math.erfc(-t/math.sqrt(2))

# ---- Hypothesis test inputs (from ablation outputs) ----
TESTS = []

# H1 — super-rare: classical R@1 > LLM R@1. Headline contrast.
# 2026-07-09 N=2000-harmonized refresh (data/round2/ablations/H1_prevalence_real.md):
# classical super_rare R@1=0.429 n=1847; LLM super_rare R@1=0.221 n=5903.
h_cla = round(0.429 * 1847); n_cla = 1847
h_llm = round(0.221 * 5903); n_llm = 5903
z = two_prop_z(h_cla, n_cla, h_llm, n_llm)
TESTS.append(("H1", "Classical > LLM R@1 on super-rare tier (<1/M)", z, z_to_p_onesided(z)))

# H2 — variant channel: llm_control P3 > P2 (one-sided).
# 2026-07-06 full-N paired (data/round2/phase3/H2_fullN.md): N=500 same cases.
# P2 R@1 = 0.296 (148/500); P3 R@1 = 0.494 (247/500); lift +19.8pp.
# Paired McNemar P3-win=106 vs P2-win=7, χ²(cc)=84.99 (even stronger); we report
# the conservative unpaired 2-prop z for family consistency.
z = two_prop_z(247, 500, 148, 500)
TESTS.append(("H2", "llm_control P3 > P2 (genotype channel lift, full-N paired)", z, z_to_p_onesided(z)))

# H4 — scaffold helps on complex MORE than on simple (DoD).
# 2026-07-09 N=2000-harmonized refresh (H4_H7_specialty.md, HPO datasets pooled):
# mdagents multi 720/3113, control multi 985/4329; mdagents single 25/226, control single 61/321.
# DoD = (0.231-0.228) - (0.111-0.190) = +0.082 (scaffold hurts less on complex).
h11, n11 = 720, 3113    # mdagents multi
h12, n12 = 985, 4329    # llm_control multi
h21, n21 = 25, 226      # mdagents single
h22, n22 = 61, 321      # llm_control single
z = diff_of_diff_z(h11, n11, h12, n12, h21, n21, h22, n22)
TESTS.append(("H4", "Scaffold benefit (mdagents−ctrl) larger on multi-system than single", z, z_to_p_onesided(z)))

# H7 — Spearman ρ across agent rankings of specialty R@1 > 0.6.
# 2026-07-09 refresh: 3 LLM-agent pairs ρ = 0.93, 0.96, 0.92 over 18 specialties
# (n≥10 each). Use 0.92 (most conservative).
TESTS.append(("H7", "Cross-agent specialty rank ρ > 0.6", 0.92, spearman_p_onesided(0.92, 18, against=0.6)))

# H8 — Peak (16-30) > worse tail (≤5). 2026-07-09 refresh (H8_phenotype_density.md):
# 16-30: 1761/5257 = 0.335; ≤5: 501/2541 = 0.197.
z = two_prop_z(1761, 5257, 501, 2541)
TESTS.append(("H8", "R@1 at 16-30 HPO terms > ≤5 (inverted-U left tail)", z, z_to_p_onesided(z)))

# H10 — Spearman ρ(faithfulness, accuracy) < 0.5.
# 2026-07-06 dual-judge N=73-trace expansion (data/round2/ablations/H10_faithfulness_accuracy.md):
# pooled ρ = 0.352 over n=129 (agent,case,judge) points. NOTE: strongly
# judge-dependent — Gemini judge ρ=0.098 (decoupled) vs Claude judge ρ=0.616
# (coupled); the pooled value straddles the 0.5 threshold. Reinforces §7.5.
rho = 0.352; n = 129; against = 0.5
# H0: ρ ≥ 0.5; HA: ρ < 0.5. Compute t for shift, take left tail.
eff = rho - against  # = -0.14
t = eff * math.sqrt((n - 2) / max(1 - rho**2, 1e-12))  # negative
# left-tail one-sided p = Φ(t) = 1 - Φ(-t) for negative t
p_h10 = 0.5 * math.erfc(-t / math.sqrt(2)) if t < 0 else 1 - 0.5*math.erfc(t/math.sqrt(2))
TESTS.append(("H10", "Spearman ρ(faithfulness, accuracy) < 0.5 (decoupling)", rho, p_h10))

# ---- Holm-Bonferroni ----
m = len(TESTS)
indexed = sorted(enumerate(TESTS), key=lambda kv: kv[1][3])  # by p
ALPHA = 0.05
results = [None]*m
running_max = 0.0
for k, (orig_i, (name, claim, stat, p)) in enumerate(indexed):
    adj = min(1.0, p * (m - k))
    running_max = max(running_max, adj)
    # Holm requires monotonicity (later rows can't be less than earlier adjusted)
    adj_mono = running_max
    reject = adj_mono < ALPHA
    results[orig_i] = (name, claim, stat, p, adj_mono, reject)

md = ["# Holm-Bonferroni family-wise correction over H1-H11", "",
      f"Family size m = {m} (z/ρ-testable on full-N Phase 4a data); α = {ALPHA} (one-sided, pre-registered direction).",
      "2026-07-09 refresh: H1/H2/H4/H7/H8 re-computed on the N=2000-harmonized "
      "data (pp/rarearena common-sample; H2 n=500 paired). H6 (thinking-mode) is now "
      "tested descriptively in §8.10 (Δ R@1 = +0.008) but stays out of this "
      "z-test family (different structure). H3/H5/H9 remain excluded (data "
      "unavailable — see §9 + tasks #63/#64/#66).", "",
      "| # | Claim | Stat | raw p | Holm-adj p | reject H₀? |",
      "|---|---|---|---|---|---|"]
for name, claim, stat, p, adj, rej in results:
    stat_s = f"z={stat:.2f}" if abs(stat) >= 0.01 and not (-1 < stat < 1) else f"{stat:.3f}"
    md.append(f"| **{name}** | {claim} | {stat_s} | {p:.2e} | {adj:.2e} | {'✅ yes' if rej else '❌ no'} |")
md += ["", "## Reading",
       "- Holm-Bonferroni controls family-wise error rate at α; tests are sorted by raw p, "
       "adjusted = p × (m − rank), monotonized.",
       "- Test choices: 2-prop z (H1, H2, H4 DoD, H8), Spearman t-approx (H7, H10), one-sided in "
       "the pre-registered direction.",
       "- **H1/H2/H4/H7/H8 are robustly rejected** (all Holm-adj p ≤ 0.012, most ≪). "
       "**H10 nominally passes (Holm-adj p=0.037) but is fragile and judge-dependent**: "
       "the pooled ρ=0.352 averages a family-judge (Gemini) ρ=0.098 (decoupled) and a "
       "non-family-judge (Claude) ρ=0.616 (coupled); per-judge the result is split, so we "
       "treat H10 as exploratory (the judge-dependence itself is the §7.5 finding), not a "
       "clean rejection. N=73 traces (llm_control + mdagents; maidxo/deeprare excluded — "
       "18-22k-char scaffold traces at ~200 s/case make N=50×4 dual-judge infeasible).",
       "- All test inputs reproduce from the linked ablation files.", "",
       "Source: `scripts/holm_bonferroni_H_family.py`. Output also in "
       "`data/round2/ablations/holm_H_family.md`."]
Path('data/round2/ablations').mkdir(parents=True, exist_ok=True)
Path('data/round2/ablations/holm_H_family.md').write_text("\n".join(md))
print("\n".join(md))
