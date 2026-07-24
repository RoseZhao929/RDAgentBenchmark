# §6 Main Results (paper draft v0)

> 数据源:`data/round2/phase4a_receipts.csv` + `phase4a_REPORT.md`
> (2026-07-09 finalized,N=2000 harmonization 后). 所有 4 backbone
> (Gemini Flash / DS V4-Flash / **DS V4-Pro reasoning-off** / GPT-5 minimal)
> 均在其 minimal/off reasoning 档评估(§5.2 设计选择:隔离 scaffolding 效应 +
> 跨 backbone 一致 + tractability;thinking-mode 见 §8 H6 ablation)。
> **N 统一化(comparability fix)**:PP-Store / RareArena 每 cell 聚合到**共同
> N=2000 分层样本**(seed=42 前 2000 case-id,`phase4a_canonical_2000.json`),
> 所有 backbone 报告在**同一批 case** 上;RareBench 全量(1122)。
> 主 llm_control/mdagents/medagents cells 使用共同 case-id cap;个别 adapter
> 未达到计划 attempted N,表中透明标注。R@1 = variants 指标,attempted 分母。
> 状态:V4-Pro reasoning bug 修复 + N=2000 统一样本重跑(concurrency 加速)+
> canonical-cap 聚合收尾(worklog Retrospective #8/#10)。

---

## 6.1 Table 1 — Headline R@1 Matrix(per-dataset, N in brackets)

Sorted by PP-Store R@1 (descending); classical/offline baselines listed first.

MIMIC-IV is not a column in this diagnostic matrix: its current input and
code-derived outcome define a different structured-EHR task (§4.2), reported
separately after the replacement protocol is scored and audited.

| Agent | Backbone | PP-Store | RareArena | RareBench | Avg |
|---|---|---|---|---|---|
| **lirical** (classical) | — | **0.47** [2000] | n/a HPO | **0.24** [1122] | n/a (2-ds) |
| **vc_rdagent** (offline) | — | **0.44** [663] | n/a HPO | **0.28** [1122] | n/a (2-ds) |
| medagents | Gemini Flash | 0.30 [2000] | 0.30 [2000] | 0.05 [1122] | 0.22 |
| llm_control | Gemini Flash | 0.29 [2000] | 0.28 [2000] | 0.02 [1122] | 0.20 |
| deeprare | Gemini Flash | 0.28 [610] | 0.00 [500] | **0.30** [954] | 0.19 |
| medagents | DS V4-Pro | 0.28 [2000] | 0.23 [2000] | 0.01 [1122] | 0.17 |
| mdagents | Gemini Flash | 0.28 [2000] | 0.28 [2000] | **0.10** [1122] | 0.22 |
| medagents | GPT-5 min | 0.28 [2000] | 0.26 [2000] | 0.01 [1122] | 0.18 |
| llm_control | DS V4-Pro | 0.27 [2000] | 0.19 [2000] | 0.02 [1122] | 0.16 |
| mdagents | DS V4-Pro | 0.27 [2000] | 0.22 [2000] | 0.04 [1122] | 0.17 |
| llm_control | DS V4-Flash | 0.26 [2000] | 0.21 [2000] | 0.05 [1122] | 0.17 |
| llm_control | GPT-5 min | 0.25 [2000] | 0.22 [2000] | 0.01 [1122] | 0.16 |
| medagents | DS V4-Flash | 0.25 [2000] | 0.16 [2000] | 0.03 [1122] | 0.15 |
| mdagents | DS V4-Flash | 0.25 [2000] | 0.23 [2000] | 0.05 [1122] | 0.17 |
| mdagents | GPT-5 min | 0.24 [2000] | 0.22 [2000] | 0.01 [1122] | 0.16 |
| deeprare | DS V4-Flash | 0.22 [500] | 0.00 [500] | **0.29** [785] | 0.17 |
| agentclinic | Gemini Flash | 0.21 [2000] | 0.13 [2000] | 0.01 [1122] | 0.12 |
| agentclinic | DS V4-Pro | 0.19 [2000] | 0.12 [2000] | 0.01 [1122] | 0.10 |
| agentclinic | DS V4-Flash | 0.13 [1955] | 0.10 [1981] | 0.02 [920] | 0.08 |
| agentclinic | GPT-5 min | 0.13 [2000] | 0.11 [2000] | 0.00 [1122] | 0.08 |
| maidxo | Gemini Flash | 0.02 [100] | 0.06 [100] | 0.00 [831] | 0.03 |

Notes: Bracketed N is **attempted N**, matching the R@1 denominator; completion
counts and failure types remain in the released receipts. (1) lirical/vc\_rdagent run only on HPO-input datasets (PP-Store /
RareBench), so their Avg is not comparable to the 3-dataset LLM rows and is
marked n/a (2-ds). (2) maidxo is systematically weak across all backbones (its
panel degrades on HPO-list input, §7.2) and maidxo×GPT-5 is incompatible
(§9 L1); we list the Gemini row as representative. (3) deeprare DS V4-Pro on
RareBench scores 0.22 [n=74], but n is too small
(P3-only) to enter the main ranking (see §7.3). (4) **The DS V4-Pro column is
reasoning-off** (§5.2 Methods note 2); the thinking-mode contrast is in §8 H6.

**Key cells** (the primary llm_control/mdagents/medagents PP-Store and
RareArena cells use the common N=2000 cap; smaller adapter-specific N are shown):

- Classical/offline baselines lead on PP-Store (lirical **0.47**, vc\_rdagent
  **0.44**), above any LLM row (best: medagents Gemini 0.30 / llm\_control
  Gemini 0.29) by **17 pp** (LIRICAL 0.47 − medagents 0.30; the gap is 18 pp
  against the single-LLM control at 0.29) — headline finding F1 is further
  strengthened on the unified large sample.
- On RareBench, deeprare (0.29-0.30) and the classical baselines (lirical 0.24 /
  vc\_rdagent 0.28) lead, while every other LLM scores ≤0.10 — see the F5
  ORPHA-sibling explanation.
- deeprare scores 0.00 on RareArena free text (a structural limitation; see
  the DeepRare reproduction note in Appendix B).
- **V4-Pro reasoning-off is not uniformly crippled**: it reaches 0.28 on
  medagents PP-Store, close to Gemini at 0.30, although other V4-Pro cells span
  0.19--0.27 and Gemini is the PP-Store winner for every listed agent. This is
  compatible with the separate §8 H6 result that enabling thinking mode on the
  single-call control was not cost-effective.

## 6.2 Backbone × scaffolding interaction

We hold the central backbone constant per agent and vary across {Gemini Flash,
DS V4-Pro (reasoning-off), DS V4-Flash, GPT-5 minimal}. The four primary
general-agent cells use the full attempted N; DeepRare's per-backbone N is
smaller and printed in the source receipts.
Per-agent backbone winners (R@1 PP-Store):

| Agent | Best backbone | Worst backbone |
|---|---|---|
| llm_control | Gemini Flash (0.29) | GPT-5 min (0.25) |
| mdagents | Gemini Flash (0.28) | GPT-5 min (0.24) |
| medagents | Gemini Flash (0.30) | DS V4-Flash (0.25) |
| agentclinic | Gemini Flash (0.21) | GPT-5 min / DS V4-Flash (0.13) |
| deeprare | Gemini Flash (0.28; n=610) | DS V4-Pro (0.20; n=111) |

**Gemini Flash is the observed PP-Store winner for every listed agent** in the
frozen manifest, although its advantage over V4-Pro/GPT-5 is only 2--5 pp for
the three main scaffolds and the single-call control. This is descriptive
backbone sensitivity, not a clean backbone main effect: DeepRare cells have
smaller and unequal N, and scaffold call patterns alter cost and failure rates.
DS V4-Pro is evaluated reasoning-off (§5.2); its separate thinking-mode
ablation adds ≈0 R@1 at 40% no-answer cost (§8 H6).

## 6.3 Cost-vs-Accuracy(per-prediction USD)

Cost per prediction spans more than an order of magnitude across backbones:
DS V4-Flash is the cheapest hosted backbone (receipt-weighted mean
$0.00033/pred), DS V4-Pro reasoning-off averages $0.00097/pred,
and **GPT-5 minimal is ~24× more expensive than V4-Flash with no consistent R@1
advantage** (it is near V4-Pro on medagents and among the weakest on
agentclinic — see F4). The
cost-vs-accuracy trade-off across every agent × backbone cell is shown in the
cost-vs-accuracy figure, and the full per-backbone and per-cell cost breakdown
(diagnostic total $270.74, 75% of the planned $360 cap) is in Appendix J.

## 6.4 Headline Findings

> ⚠ **REVIEWER NOTE (2026-07-09)**: two data-quality passes since v0. (1) DS
> V4-Pro re-run **reasoning-off** after root-causing an unbounded-reasoning
> starvation bug (§5.2 Methods note 2). (2) **PP-Store/RareArena harmonized to a
> common N=2000 case-id cap** across all backbones for the primary
> llm_control/mdagents/medagents cells (earlier cells ranged 500–4589 due to
> historical over-runs, breaking cross-backbone comparability). Adapter-specific
> DeepRare/MAI-DxO cells remain smaller and are labelled. Net effect: R@1 estimates
> settled ~2–4 pp below the small-sample values (the 500-case samples were mildly
> optimistic), so F1 *widens* (17–18 pp) and F4's "GPT-5 best for medagents" no
> longer holds (medagents Gemini 0.30 ≥ GPT-5 0.28). F2/F3 directions unchanged.

**F1: Classical / offline leads decisively on Phenopacket-Store and at the
super-rare prevalence tail.**
LIRICAL (Bayesian) R@1=**0.47**, VC-RDAgent Stage 1 (offline IC+Poincaré)
R@1=**0.44** on Phenopacket-Store (common N=2000 sample), against the best LLM
cell (medagents × Gemini R@1=**0.30**; llm_control × Gemini 0.29) — a
**17–18 pp** gap that *widened* under the larger harmonized sample (the earlier
N≈100–500 optimistic estimates of 0.31–0.36 regressed to 0.29–0.30 at N=2000).
RareBench does **not** reproduce a blanket classical advantage: DeepRare
(0.29--0.30) slightly exceeds the best classical/offline result
(VC-RDAgent 0.28), while all other LLM scaffolds sit ≤0.10. The robust
cross-family result is therefore dataset- and prevalence-specific: the
Phenopacket-Store gap above and H1's +28 pp classical advantage on the
super-rare tier, not a claim that classical wins every HPO-input dataset.

**F2: Multi-agent scaffolding gives at most a small, dataset-dependent gain and
often none, not a uniform boost.** On Gemini Flash (common N=2000), medagents
(PP-Store 0.30, RareArena 0.30) edges llm_control (0.29, 0.28) by only ~1–2 pp,
within the control's CI; mdagents (PP-Store 0.28) actually sits ~1 pp *below* the
control, and agentclinic/maidxo regress sharply (§7.2). The benefit does not
consistently exceed the no-scaffold control's CI and does not hold on every
backbone. **(Revised down
from the v0 "+5–7 pp" claim, which rested on a stale small-sample medagents 0.40.)**

**F3: DeepSeek V4-Flash is ~10× cheaper than Gemini Flash but usually trades
off accuracy.** Receipt-weighted mean cost is $0.00033 (V4-Flash) vs
$0.00344 (Gemini). On PP-Store, V4-Flash is 3--8 pp lower across the
comparable agents; on RareArena the gap ranges 4--14 pp. RareBench is mixed,
including cells where V4-Flash ties or exceeds Gemini, so the quality claim is
not universal. V4-Flash also showed a higher
transient empty-content rate on free-text/HPO-list inputs (mitigated by a
wrapper-level retry; see Appendix B). **Conclusion: V4-Flash is the
cost-efficient choice when ~10× cost reduction outweighs the observed accuracy
drop, but it does NOT match Gemini quality.** (Reversed from v0.)

**F4: GPT-5 minimal-reasoning is not worth its cost, and at full-N has no
scaffold where it is the sole winner.** GPT-5 (`reasoning_effort=minimal`,
forced because default reasoning consumes all max_tokens) reaches 0.28 on
medagents PP-Store (below Gemini at 0.30 and tied with V4-Pro-off) and
falls on AgentClinic OSCE dialogue (0.13 versus Gemini 0.21, about −9 pp). As the most expensive
backbone (~24× V4-Flash per prediction) with no consistent accuracy edge, it is
hard to justify. The reasoning-channel question is answered directly by our H6
ablation (§8): on the single-call LLM control, turning reasoning **on** (V4-Pro)
changes R@1 by **+0.008** (noise) while producing no parseable answer in 40% of
cases and running 10–40× slower — thinking mode is not worth it on this task.

**F5: RareBench HF is uniquely hard for general LLM scaffolds (≤0.10 R@1)
but tractable for classical/HPO-pipeline agents (lirical 0.24, vc_rdagent 0.28,
deeprare 0.29–0.30).** Root causes: (a) RareBench gold labels use ORPHA codes
with sibling-disambiguation challenges across Orphanet's hierarchy
(`Methylmalonic acidemia with homocystinuria` ORPHA:26 vs `Vitamin B12-
unresponsive methylmalonic acidemia` ORPHA:27 share concept but not OMIM
cross-ref); (b) classical/HPO agents use OMIM directly + Orphanet name fuzzy
match, bypassing this mismatch. **A real evaluator-vs-data interaction, not a
pure model failure.** Adapter-side fuzzy variants logging recovers +1–8 pp but
doesn't close the gap.

---

## Figures (rendered to `data/round2/figures/`)

> Notation note: §6 uses **F1–F5** for Findings (text). The figures below
> use **Figure N**. The two namespaces do not overlap.

- Per-dataset R@1 analyses use only the three diagnostic datasets.
- `figM1_llm_vs_classical.png`: scoped LLM/classical comparison.
- `figM2_cost_accuracy.png`: cost-vs-accuracy scatter (each cell as one point).
- `fig4_a6_contamination_scatter.png` (§7.10 / §8.9 A6): literature-frequency
  audit — log(pre-cutoff PubMed
  mentions) vs per-disease R@1, one panel per backbone. **LLM ρ≈0.3 (weak
  positive); classical baselines ρ≈0 (null control).** —
  `fig4_a6_contamination_scatter.png`
- `figM3_prevalence.png` (§7.7 H1): prevalence stratification curve.
  LLM R@1 declines on the rarest tier (0.22 super-rare); classical/offline
  *rises* on the rarest tier (0.50), with a +27 pp crossover gap. —
  `fig5_prevalence_h1.png`
- `figM4_hpo_density.png` (§7.1.2 / §8.8 H8): phenotype-density association.
  R@1 peak at 16–30 HPO terms (0.32) drops to 0.22 at ≤5 terms and 0.25
  at >30. —
  `fig6_hpo_density_h8.png`
- `fig7_specialty_h7.png` (§7.9 H7): per-specialty R@1 ranges across agents on the
  HPO organ-system axis. Universal weak rows: nervous / metabolic /
  digestive; classical inverts on nervous (LIRICAL 0.35, VC-RDAgent 0.43). —
  `fig7_specialty_h7.png`

## Cross-references

- §5.1 Agent Fairness Matrix — adapter shim details
- §5.2 Backbones — methods note on GPT-5 reasoning_effort
- §7 Analysis — scaffolding, genotype, faithfulness deep-dives
- the reproducibility audit Reproducibility audit — per-baseline numbers vs paper claim
- Appendix B — per-baseline reproduction docs
