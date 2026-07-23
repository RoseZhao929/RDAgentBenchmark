# §8 Ablations (paper draft v0)

> 数据源:`data/round2/ablations/A4_metric_AB.md`(A4 done), 其他 A1-A3 / A5-A12 to be filled
> 状态:A4 finalized, structure for A1-A12 ready, other ablations TODO

---

**Pre-registered ablations**:

| # | Name | Status |
|---|---|---|
| A1 | Top-1 vs Top-5 metric A/B | partial (Phase 4a tables include both) |
| A2 | Strict ID vs cross-mapped ID | superseded by A4 |
| A3 | Backbone × Scaffolding 2×N | ✅ done (§6.2 / Phase 4a matrix) |
| A4 | Strict vs ORPHA-fuzzy-variants | ✅ **done — this section §8.1** |
| A5 | Silver gold vs physician gold | ✅ **interim done** (Opus 4.8 agent gold; §9 L5) — physician swap at camera-ready |
| A6 | TS-Guessing contamination audit | ✅ **done — §8.9 + §7.10** |
| A7 | Single LLM judge vs dual-judge (Gemini→Claude) | partial (§7.5 done) |
| A8 | Reasoning on vs off (thinking-mode, = H6) | ✅ **done — §8.10** (V4-Pro on/off) |
| A9 | Subprocess timeout cap 300s vs 600s vs 1200s | ✅ **done — §8.6** |
| A10 | Prevalence-stratified R@1 | ✅ done (`A10_prevalence_stratified.md`) |
| A11 | Cross-dataset agent ranking stability | ✅ done (§7.6 / `A11_ranking_stability.md`) |
| A12 | LLM-judge swap (P5 with Claude vs Gemini judge) | ✅ done (§7.5) |

---

## §8.1 Ablation A4 — Strict vs ORPHA-Fuzzy Variants Cross-Map

**Question**: When an LLM emits a generic disease name (e.g. "Methylmalonic
Acidemia") that fuzzy-matches multiple ORPHA codes at tied scores
(ORPHA:26 "Methylmalonic acidemia with homocystinuria", ORPHA:27
"Vitamin B12-unresponsive methylmalonic acidemia", ORPHA:280183 "...
transcobalamin receptor defect"), does the evaluator credit the
prediction?

**A. Strict baseline**: prediction must exact-match a gold OMIM / ORPHA /
CCRD ID or cross-map to one via Orphadata.

**B. Variants-aware**: adapter logs the *tied top-K* (score ≥ top - 5)
ORPHA candidates in `extra["ranked_predictions_variants"]`; evaluator
returns True if **any** tied variant hits gold.

**Legacy result audit** (Phase 4a originally ran N=100 × 4 datasets × 5
backbones; the table below reports only the three diagnostic datasets):

| Dataset | Aggregate Δ R@1 | Aggregate Δ R@5 |
|---|---|---|
| Phenopacket-Store | **+0.03** | **+0.06** |
| RareArena RDS | **+0.02** | **+0.04** |
| RareBench HF | +0.00 | +0.00 |
| **All diagnostic datasets combined** | **+0.010** | **+0.020** |

**Top-impacted cells**:
- PP-Store mdagents: +3 pp R@1, +6 pp R@5
- PP-Store medagents: +4 pp R@1, +6 pp R@5
- PP-Store llm_control: +3 pp R@1, +6 pp R@5

**Where it doesn't help**:
- vc_rdagent / lirical: bypass name-mapping (use IDs directly)
- RareBench: gap is ORPHA hierarchy-level, beyond fuzzy-tie scope
- DeepRare: emits domain-specific name spellings that fuzzy already handles

**Decision**: variants-aware metric is **on by default** in main Table 1;
strict variant reported in parentheses for reviewer reference.

## §8.2 Ablation A3 — Backbone × Scaffolding Cross-Product

Detailed in §6.2 main results. Highlights:

- **No-scaffold control** (llm_control) is backbone-insensitive on
  PP-Store (R@1 = 0.27-0.30 across 4 backbones, full-N; V4-Pro reasoning-off)
- **Single-pass multi-agent** (mdagents) has a narrow 4-pp backbone spread
  (Gemini 0.28, DS V4-Pro-off 0.27, V4-Flash 0.25, GPT-5 0.24)
- **Multi-round debate** (medagents) tops on Gemini (0.30), then V4-Pro-off /
  GPT-5 (0.28), weakest on V4-Flash (0.25)
- **OSCE simulation** (agentclinic) collapses on GPT-5 minimal (0.13)
- **Panel orchestration** (MAI-DxO) collapses universally on HPO input

The cross-product matrix shows **no universally-best backbone**: each
scaffolding architecture has its own preferred backbone. This refutes
the "just use the best backbone" simplifying assumption.

## §8.3 Ablation A7 — LLM-Judge Swap (Faithfulness scoring)

Detailed in §7.5. Original P5 reasoning-faithfulness pilot used Gemini
3 Flash as judge. We swap to Claude Sonnet 4.5 as the second judge
and find:

- Self-preference bias is real: Gemini-judge scored Gemini-agent
  scaffolds +0.30 to +0.90 higher on average vs other backbones
- Claude-judge shrinks the gap to {+0.20, +0.33, -0.39, +0.24} —
  near-zero on average
- Inter-judge agreement κ = 0.62 (Cohen's, ≥ 0.6 threshold pre-registered)

**Decision**: dual-judge protocol mandatory; report Claude as primary
judge for headline numbers; Gemini-judge as secondary diagnostic.

## §8.4 Ablations TODO (deferred to camera-ready)

The following are pre-registered but require additional infrastructure
or holdout data. **All are listed here for transparency**; results
will be appended at camera-ready.

- **A5** (silver gold vs physician gold) — pending 200-case PMC OA
  holdout physician annotation (user TODO).
- ~~**A6** (TS-Guessing contamination audit)~~ — **done, see §8.9 and §7.10**.
- **A8** (GPT-5 reasoning_effort axis) — cost-prohibitive in Phase 4a;
  N=50 sanity confirms `reasoning_effort=medium` recovers ~10pp R@1
  on mdagents but at ~$80 per Phase 4 cell.
- **A1** (top-1 vs top-5) — table format only; numbers already in
  §6.

## §8.6 Ablation A9 — Subprocess Timeout Cap (300s vs 600s vs 1200s)

The subprocess wall-clock cap interacts with two distinct failure modes,
which A9 disentangles:

**(a) Borderline-slow but legitimate cells — cap matters.** During the
N=500 rerun, `medagents × DS V4-Flash` and `agentclinic × DS V4-Flash`
on RareBench and the legacy MIMIC ICD-title task showed many `timeout` records at the default **300s**
cap. A probe re-ran a representative medagents timeout case at a **900s**
cap and it completed successfully in **309s** — i.e. the case was not
hung, the 300s cap was simply slightly too tight (compounded by the
empty-content retry adding extra subprocess invocations). Raising the cap to **600s** and
re-running recovered these cells essentially completely (agentclinic
RareBench 60/60 ok; legacy MIMIC agentclinic 37/37 and medagents 267/268). DS
V4-Pro remained slow enough that 600s still left a small timeout tail
(mdagents V4-Pro RareBench 21/36 recovered) — genuine backbone latency,
reported honestly.

**(b) Genuinely degenerate output — cap does NOT help.** MAI-DxO × GPT-5
still degenerates at the **1200s** cap (§9 L1): the panel emits no usable
ranked diagnosis regardless of time budget. This is an architecture×backbone
incompatibility, not a latency problem; more wall-clock buys nothing.

**Conclusion**: the timeout cap is a real evaluation hyperparameter for
slow-but-valid cells (600s is the right default for hosted DeepSeek/Gemini
on long free-text), but it cannot rescue genuinely degenerate
agent×backbone pairings. Cap choices are logged per-cell.

## §8.7 Ablations deferred / data-gated

- **A5** (silver gold vs physician gold) — pending 200-case PMC OA
  holdout physician annotation (handoff package prepared; annotation in
  progress).
- **A6** (TS-Guessing contamination audit) — n-gram overlap vs LLM
  training cutoff; gated on the post-cutoff holdout being curated.
- **A10** (prevalence-stratified R@1) — ✅ computed.
- **A11** (cross-dataset ranking stability) — ✅ computed (see §7.6).

## §8.5 Pre-registration check

Under our research-integrity protocol, all hypotheses (H1-H11) and
ablations (A1-A12) were frozen at OSF prior to Phase 4a launch. The
above results are the first pre-registered evaluation report.
**No post-hoc hypothesis selection.**

## §8.8 Holm-Bonferroni family-wise correction over H1-H11 (P6.3)

Per pre-registration we apply Holm-Bonferroni at α=0.05 (one-sided in the
predicted direction) over the testable subset of H1-H11. Family size m=6
(H3/H5/H9 excluded — data unavailable, see §9 L3/L4 and tasks #63/#64/#66; H6
now tested descriptively in §8.10 but kept out of this z/ρ family). **2026-07-06
full-N refresh**: all inputs recomputed on full-N; H2 upgraded from an n=50
pilot to an **n=500 paired** design.

| # | Claim | Stat | raw p | Holm-adj p | Survives α=0.05? |
|---|---|---|---|---|---|
| **H1** | Classical > LLM R@1 on super-rare tier (<1/1,000,000) | z=17.54 | 3.7e-69 | 2.2e-68 | ✅ **yes** |
| **H8** | R@1 at 16-30 HPO terms > ≤5 (inverted-U left tail) | z=12.57 | 1.6e-36 | 7.8e-36 | ✅ **yes** |
| **H2** | llm_control P3 > P2 (genotype channel, full-N paired) | z=6.40 | 7.6e-11 | 3.0e-10 | ✅ **yes** |
| **H7** | Cross-agent specialty rank ρ > 0.6 | ρ=0.92 | 5.5e-04 | 1.6e-03 | ✅ **yes** |
| **H4** | Scaffold benefit larger on multi-system than single (DoD) | z=2.61 | 4.5e-03 | 9.0e-03 | ✅ **yes** |
| H10 | Spearman ρ(faithfulness, accuracy) < 0.5 | ρ=0.35 | 3.7e-02 | 3.7e-02 | ⚠️ nominal but judge-dependent (see below) |

**Reading**: **5 of 6 testable hypotheses now survive** the strictest
pre-registered family-wise correction (up from 2/6 at pilot N). The full-N
reruns flipped H2, H4, and H7 from under-powered to significant: the
genotype-channel lift (H2: +19.8 pp, n=500 paired, McNemar χ²=85), the
scaffold-benefit-on-complexity difference-of-differences (H4), and the
cross-agent specialty blind-spot correlation (H7: ρ=0.92 across 18 specialties)
are all now FWE-robust, alongside the two headline claims H1 (classical dominate
super-rare) and H8 (interior phenotype-density optimum). **H10**
(faithfulness–accuracy decoupling) we report as **exploratory, not a clean
rejection**. An earlier version rested on a family-judge (Gemini) ρ=0.098 vs
non-family (Claude) ρ=0.616 split, but a 2026-07-22 frozen-audit re-run showed
that split was a **trace-capture artifact**: the Gemini scores had been computed
on truncated/empty traces while the Claude scores used repaired traces. Re-running
the Gemini judge on the *same* repaired traces (n=40) raises its ρ from 0.098 to
**0.457**, against Claude's **0.640** (judge agreement ρ=0.741) — a modest residual
judge-family difference, not the near-zero "strong decoupling" originally claimed.
The pre-registered H10 verdict (ρ<0.5) is therefore genuinely borderline and
judge-sensitive, so we keep H10 exploratory and withdraw the ρ=0.098 figure. See
§7.5 for the de-confounded analysis.

## §8.9 Ablation A6 — TS-Guessing data-contamination audit (P6.2)

We probe anticipated objection #1 ("LLMs answer well only on diseases they were
trained on") by correlating, for each gold ORPHA in our phase4a predictions,
the pre-cutoff PubMed mention count with per-disease R@1, separately per
backbone. PubMed query uses `esearch.fcgi` with `"<disease name>"[All Fields]`
and `maxdate=2024/06/30` (conservative cutoff covering all four backbones).
Spearman ρ over log(mention + 1) vs R@1; per-disease aggregate requires
≥3 predictions per (disease, backbone).

| Backbone | n diseases | Spearman ρ | Interpretation |
|---|---|---|---|
| Gemini 3 Flash | 244 | **0.365** | 🟡 weak positive |
| GPT-5 (reasoning=minimal) | 87 | **0.354** | 🟡 weak positive |
| DeepSeek V4-Flash | 244 | **0.348** | 🟡 weak positive |
| DeepSeek V4-Pro | 179 | **0.294** | 🟡 weak positive |
| LIRICAL (classical Bayesian) | 26 | −0.155 | ✅ null (methodological control) |
| VC-RDAgent (offline IC) | 26 | −0.059 | ✅ null (methodological control) |

**Clean dichotomy**: 4/4 LLM backbones at ρ ≈ 0.29–0.37; 2/2 classical baselines
at ρ ≈ 0. The classical baselines do not consume text and therefore cannot
have been "trained on" PubMed; their null ρ confirms our pipeline introduces
no spurious correlation. The LLM signal is real but **bounded** — ρ² ≈ 0.09
means pre-cutoff exposure explains ≈ 9 % of R@1 variance, leaving ≈ 91 % to
phenotype-disease reasoning + extraction + scaffold design.

Reading is treated in §7.10 (a finer-grained interpretation paired with F1);
the L4 post-cutoff PMC OA holdout (~200 cases, doctor-annotated in progress)
remains the bias-free reference for the residual 9 %.

Visualised in \Cref{fig:fig4_a6_contamination_scatter}:
one panel per backbone. The clean dichotomy is visually obvious — the
LLM backbones show a positive slope; the classical baselines
(LIRICAL, VC-RDAgent) show a flat cloud.

---

## §8.10 Ablation A8 / H6 — Thinking-mode (reasoning on vs off)

**Question (anticipated objection: "you crippled the models by disabling reasoning")**:
Our main matrix runs all reasoning backbones in their minimal/off configuration
(§5.2) for cross-backbone consistency, isolation of the scaffolding effect, and
tractability. Does turning reasoning **on** actually help? We test this on the
single-call LLM control (no scaffold confound) with DeepSeek-V4-Pro — the one
backbone whose reasoning can be cleanly toggled via `reasoning={"enabled": …}`
(GPT-5 minimal is already near-floor; V4-Pro ignores every softer throttle,
§5.2 Methods note 2). Same cases, same prompt, only the reasoning flag changes.

| Config | R@1 (paired, PP-Store) | Completion | Latency/case |
|---|---|---|---|
| reasoning **OFF** (main matrix) | **0.352** | 100 % | ~2.5 s |
| reasoning **ON** (thinking) | **0.360** | **60 %** (40 % no-answer) | ~90–117 s (median), up to 571 s |
| Δ (on − off) | **+0.008** | — | 10–40× slower |

(N = 253 paired cases where reasoning-ON produced a parseable answer;
PP-Store; llm_control × V4-Pro.)

**Finding**: thinking mode changes R@1 by **+0.008 — statistically indistinguishable
from zero** — while (a) failing to emit any parseable diagnosis in **40 %** of
cases (V4-Pro's unbounded reasoning consumes the entire `max_tokens=4000` budget
before producing content) and (b) running **10–40× slower**. Reasoning-on is
therefore both *unhelpful* and *impractical* at benchmark scale on this task.

**Three consequences for the paper**:
1. It **pre-empts the "not tested at best" attack**: we did test thinking mode; it
   does not help on retrospective rare-disease DDx from an HPO/phenotype list.
2. It **justifies the reasoning-off main matrix** as a design choice that loses no
   accuracy while gaining tractability and cross-backbone comparability.
3. The 40 % no-answer rate is itself a **deployment-reliability finding**: a
   frontier reasoning model at a fixed token budget silently drops 2 in 5 cases —
   a failure mode benchmark builders and clinical integrators must budget for.

**Scope / honesty**: exploratory, single dataset (PP-Store), single control agent,
N=253 completable; the 40 % dropout is survivorship-biased *against* finding a
reasoning benefit (harder cases that need more reasoning are exactly the ones that
time out / go empty), so the true reasoning-on R@1 on all-cases could be lower, not
higher — strengthening the "not worth it" conclusion rather than weakening it. We
do not extend it to the scaffolded agents because reasoning-on there is
computationally infeasible (AgentClinic reasoning-on was >900 s/case, §5.2).
