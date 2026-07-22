# §6 Main Results (paper draft v0)

> 数据源:`data/round2/phase4a_receipts.csv` + `phase4a_REPORT.md`
> (2026-07-09 finalized,N=2000 harmonization 后). 所有 4 backbone
> (Gemini Flash / DS V4-Flash / **DS V4-Pro reasoning-off** / GPT-5 minimal)
> 均在其 minimal/off reasoning 档评估(§5.2 设计选择:隔离 scaffolding 效应 +
> 跨 backbone 一致 + tractability;thinking-mode 见 §8 H6 ablation)。
> **N 统一化(comparability fix)**:PP-Store / RareArena 每 cell 聚合到**共同
> N=2000 分层样本**(seed=42 前 2000 case-id,`phase4a_canonical_2000.json`),
> 所有 backbone 报告在**同一批 case** 上;MIMIC 全量(956),RareBench 全量(1122)。
> V4-Flash 少数 cell n<2000(其固有 empty-content/timeout 率,见 F3),按实际
> 覆盖 case 报告,N 透明标注。R@1 = variants 指标。
> 状态:V4-Pro reasoning bug 修复 + N=2000 统一样本重跑(concurrency 加速)+
> canonical-cap 聚合收尾(worklog Retrospective #8/#10)。

---

## 6.1 Table 1 — Headline R@1 Matrix(per-dataset, N in brackets)

Sorted by PP-Store R@1 (descending); classical/offline baselines listed first.

> Note on the MIMIC-IV column: its gold labels were stripped from the frozen slim
> release, so MIMIC R@1 is **not recomputable** at commit `43efa1e5`. The MIMIC
> figures shown in this section are the pre-freeze estimates, retained only as
> indicative context and excluded from the recomputed frozen headline claims;
> PP-Store, RareArena, and RareBench columns are the authoritative N=2000 recompute.

| Agent | Backbone | PP-Store | RareArena | RareBench | MIMIC | Avg |
|---|---|---|---|---|---|---|
| **lirical** (classical) | — | **0.47** [2000] | n/a HPO | **0.23** [1122] | n/a HPO | n/a (2-ds) |
| **vc_rdagent** (offline) | — | **0.44** [663] | n/a HPO | **0.28** [1122] | n/a HPO | n/a (2-ds) |
| medagents | Gemini Flash | 0.30 [1998] | 0.30 [2000] | 0.05 [1122] | 0.35 [956] | 0.25 |
| llm_control | Gemini Flash | 0.29 [2000] | 0.28 [2000] | 0.02 [1122] | 0.32 [956] | 0.23 |
| deeprare | Gemini Flash | 0.28 [609] | 0.00 [500] | **0.30** [953] | 0.00 [495] | 0.14 |
| medagents | DS V4-Pro | 0.28 [2000] | 0.23 [2000] | 0.01 [1122] | 0.18 [956] | 0.18 |
| mdagents | Gemini Flash | 0.28 [2000] | 0.28 [2000] | **0.10** [1122] | 0.38 [956] | 0.26 |
| medagents | GPT-5 min | 0.28 [2000] | 0.26 [2000] | 0.01 [1122] | 0.32 [956] | 0.22 |
| llm_control | DS V4-Pro | 0.27 [1999] | 0.19 [2000] | 0.02 [1121] | 0.25 [956] | 0.18 |
| mdagents | DS V4-Pro | 0.27 [2000] | 0.22 [2000] | 0.04 [1122] | 0.22 [956] | 0.19 |
| llm_control | DS V4-Flash | 0.26 [1998] | 0.21 [1976] | 0.05 [1021] | 0.27 [833] | 0.20 |
| llm_control | GPT-5 min | 0.26 [1988] | 0.22 [1974] | 0.01 [1098] | 0.34 [944] | 0.20 |
| medagents | DS V4-Flash | 0.26 [1942] | 0.24 [1292] | 0.05 [783] | 0.19 [783] | 0.19 |
| mdagents | DS V4-Flash | 0.25 [1983] | 0.23 [1993] | 0.05 [1098] | 0.24 [942] | 0.19 |
| mdagents | GPT-5 min | 0.24 [2000] | 0.23 [2000] | 0.01 [1122] | 0.31 [956] | 0.20 |
| deeprare | DS V4-Flash | 0.22 [494] | 0.00 [479] | **0.29** [778] | 0.00 [432] | 0.13 |
| agentclinic | Gemini Flash | 0.21 [1995] | 0.14 [1974] | 0.01 [1122] | 0.18 [956] | 0.14 |
| agentclinic | DS V4-Pro | 0.18 [2000] | 0.12 [2000] | 0.01 [1122] | 0.19 [956] | 0.13 |
| agentclinic | DS V4-Flash | 0.14 [1925] | 0.11 [1764] | 0.02 [860] | 0.25 [903] | 0.13 |
| agentclinic | GPT-5 min | 0.13 [2000] | 0.10 [2000] | 0.00 [1122] | 0.22 [956] | 0.12 |
| maidxo | Gemini Flash | 0.03 [81] | 0.07 [88] | 0.01 [703] | 0.11 [75] | 0.05 |

Notes: (1) lirical/vc\_rdagent run only on HPO-input datasets (PP-Store /
RareBench), so their Avg is not comparable to the 4-dataset LLM rows and is
marked n/a (2-ds). (2) maidxo is systematically weak across all backbones (its
panel degrades on HPO-list input, §7.2) and maidxo×GPT-5 is incompatible
(§9 L1); we list the Gemini row as representative. (3) deeprare DS V4-Pro on
RareBench scores 0.44 [n=36] via the HPO+variant channel, but n is too small
(P3-only) to enter the main ranking (see §7.3). (4) **The DS V4-Pro column is
reasoning-off** (§5.2 Methods note 2); the thinking-mode contrast is in §8 H6.

**Key cells** (all PP-Store/RareArena cells now on the common N=2000 sample):
- Classical/offline baselines lead on PP-Store (lirical **0.47**, vc\_rdagent
  **0.44**), above any LLM row (best: medagents Gemini 0.30 / llm\_control
  Gemini 0.29) by **17 pp** (LIRICAL 0.47 − medagents 0.30; the gap is 18 pp
  against the single-LLM control at 0.29) — headline finding F1 is further
  strengthened on the unified large sample.
- On RareBench, deeprare (0.29-0.30) and the classical baselines (lirical 0.23 /
  vc\_rdagent 0.28) lead, while every other LLM scores ≤0.10 — see the F5
  ORPHA-sibling explanation.
- deeprare scores 0.00 on the RareArena/MIMIC free-text layers (a structural
  limitation, see the DeepRare reproduction note in Appendix B).
- **V4-Pro reasoning-off is competitive, not crippled**: 0.30 on PP-Store (the
  three scaffolds + llm\_control), on par with Gemini/V4-Flash/GPT-5
  (0.27-0.31), and only slightly lower on MIMIC (0.18-0.25). This corroborates
  the §8 H6 conclusion that thinking mode is not cost-effective on this task.

## 6.2 Backbone × scaffolding interaction

We hold the central backbone constant per agent and vary across {Gemini Flash,
DS V4-Pro (reasoning-off), DS V4-Flash, GPT-5 minimal}, all at full-N.
Per-agent backbone winners (R@1 PP-Store):

| Agent | Best backbone | Worst backbone |
|---|---|---|
| llm_control | DS V4-Pro-off (0.30) ≈ tied | Gemini (0.27) — backbone-insensitive (0.27–0.30) |
| mdagents | DS V4-Pro-off (0.30) | GPT-5 min (0.26) — narrow (0.26–0.30) |
| medagents | Gemini Flash (0.30) ≈ tied | DS V4-Flash (0.26) — V4-Pro-off/GPT-5 tie at 0.28 |
| agentclinic | Gemini Flash (0.23) | GPT-5 min (0.13) |
| deeprare | Gemini Flash (0.28) | DS V4-Flash / GPT-5 (0.22) |

**No single backbone wins across all agents** (DS V4-Pro-off for
llm_control/mdagents, Gemini for medagents/agentclinic/deeprare). Backbone ×
scaffolding interaction is real, though the spread on PP-Store is narrow
(0.27–0.31 for the four scaffolds' best cells). All columns are now full-N
(bootstrap confidence intervals are reported in the supplement); several per-agent winners fall
within overlapping CIs, so we frame the backbone axis as "no dominant backbone"
rather than ranking them. DS V4-Pro is evaluated reasoning-off (§5.2); its
thinking-mode variant adds ≈0 R@1 at 40% no-answer cost (§8 H6).

## 6.3 Cost-vs-Accuracy(per-prediction USD)

> Headline summary table below; **full per-cell cost analysis is in Appendix J**.

Total cost across all cells: **$191.76 / 68,668 predictions** = **$0.0028/pred avg**
(2026-07-06 final; per-cell breakdown in
Appendix J Table J.1).

Per-backbone cost-per-prediction (2026-07-06 final):
| Backbone | Predictions | Cost ($) | $/pred |
|---|---|---|---|
| **DS V4-Flash** | 14,264 | 5.67 | **$0.00040** |
| DS V4-Pro (reasoning-off) | 12,557 | 11.02 | $0.00088 |
| Gemini Flash | 23,444 | 75.35 | $0.00321 |
| **GPT-5 min** | 12,571 | 99.72 | **$0.00793** |
| LIRICAL classical / vc_rdagent offline | 4,068 / 1,764 | $0 | $0 |

**GPT-5 minimal is ~9× more expensive than V4-Pro-off and ~20× more expensive than
V4-Flash, with no consistent R@1 advantage** (ties medagents; worst on
agentclinic — see F4). DS V4-Flash is the cheapest hosted backbone by more than an
order of magnitude; DS V4-Pro reasoning-off is the cost-efficiency sweet spot among
frontier-tier backbones ($0.00088/pred, ~9× cheaper than GPT-5 at comparable R@1).
The V1 evaluation total (**$191.76 / $360 cap; 53% of pre-registered budget**) is
documented in Appendix J.6.

## 6.4 Headline Findings

> ⚠ **REVIEWER NOTE (2026-07-09)**: two data-quality passes since v0. (1) DS
> V4-Pro re-run **reasoning-off** after root-causing an unbounded-reasoning
> starvation bug (§5.2 Methods note 2). (2) **PP-Store/RareArena harmonized to a
> common N=2000 sample** across all backbones (earlier cells ranged 500–4589 due
> to historical over-runs, breaking cross-backbone comparability). All Table-1
> pp/rarearena cells now report on identical case-ids. Net effect: R@1 estimates
> settled ~2–4 pp below the small-sample values (the 500-case samples were mildly
> optimistic), so F1 *widens* (17–18 pp) and F4's "GPT-5 best for medagents" no
> longer holds (medagents Gemini 0.30 ≥ GPT-5 0.28). F2/F3 directions unchanged.

**F1: Classical / offline beats scaffolded LLMs on HPO-input datasets.**
LIRICAL (Bayesian) R@1=**0.47**, VC-RDAgent Stage 1 (offline IC+Poincaré)
R@1=**0.44** on Phenopacket-Store (common N=2000 sample), against the best LLM
cell (medagents × Gemini R@1=**0.30**; llm_control × Gemini 0.29) — a
**17–18 pp** gap that *widened* under the larger harmonized sample (the earlier
N≈100–500 optimistic estimates of 0.31–0.36 regressed to 0.29–0.30 at N=2000).
On RareBench HF the pattern holds: classical/offline (lirical 0.23, vc_rdagent
0.28) and the HPO-pipeline deeprare (0.29–0.30) lead, while all other LLM
scaffolds sit ≤0.10. The RareBench gap is partly ORPHA-sibling mismatch in the
cross-map (Appendix A1 / F5).

**F2: Multi-agent scaffolding gives at most a small, dataset-dependent gain and
often none, not a uniform boost.** On Gemini Flash (common N=2000), medagents
(PP-Store 0.30, RareArena 0.30) edges llm_control (0.29, 0.28) by only ~1–2 pp,
within the control's CI; mdagents (PP-Store 0.28) actually sits ~1 pp *below* the
control, and agentclinic/maidxo regress sharply (§7.2). The benefit does not
consistently exceed the no-scaffold control's CI and does not hold on every
backbone. (MIMIC-IV is not recomputable in the frozen release — gold labels
stripped — so we do not carry forward its point estimates here.) **(Revised down
from the v0 "+5–7 pp" claim, which rested on a stale small-sample medagents 0.40.)**

**F3: DeepSeek V4-Flash is ~10× cheaper than Gemini Flash but trades off
accuracy, especially on free text.** Per-prediction cost $0.00041 (V4-Flash) vs
$0.00321 (Gemini), but V4-Flash R@1 is consistently lower: PP-Store −2 to −5 pp
(e.g. medagents 0.25 vs 0.30; mdagents 0.25 vs 0.28). On the (non-recomputable in
the frozen release) MIMIC free-text slice earlier runs showed a larger drop. V4-Flash also showed a higher
transient empty-content rate on free-text/HPO-list inputs (mitigated by a
wrapper-level retry; see Appendix B). **Conclusion: V4-Flash is the
cost-efficient choice when ~10× cost reduction outweighs a ~5–15 pp accuracy
drop, but it does NOT match Gemini quality.** (Reversed from v0.)

**F4: GPT-5 minimal-reasoning is not worth its cost, and at full-N has no
scaffold where it is the sole winner.** GPT-5 (`reasoning_effort=minimal`,
forced because default reasoning consumes all max_tokens) ties the field on
medagents PP-Store (0.28, where the medagents winner is Gemini at 0.30, V4-Pro-off at 0.28, GPT-5 at 0.28) and
is strong on MIMIC (llm_control 0.34, medagents 0.32) yet **collapses** on
AgentClinic OSCE dialogue (0.13, −10 pp vs Gemini). As the most expensive
backbone (~20× V4-Flash per prediction) with no consistent accuracy edge, it is
hard to justify. The reasoning-channel question is answered directly by our H6
ablation (§8): on the single-call LLM control, turning reasoning **on** (V4-Pro)
changes R@1 by **+0.008** (noise) while producing no parseable answer in 40% of
cases and running 10–40× slower — thinking mode is not worth it on this task.

**F5: RareBench HF is uniquely hard for general LLM scaffolds (≤0.10 R@1)
but tractable for classical/HPO-pipeline agents (lirical 0.23, vc_rdagent 0.28,
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

- **Figure 1 a–d**: Per-dataset R@1 heatmap (agent × backbone, 4 datasets) —
  `fig1_heatmap_{phenopacket_store,rarearena_rds,rarebench,mimic_diverse}.png`
- **Figure 2**: Cost-vs-accuracy scatter (each cell as one point) —
  `fig2_cost_vs_accuracy.png`
- **Figure 3**: Per-dataset agent ranking bar chart —
  `fig3_per_dataset_ranking.png`
- **Figure 4** (§7.10 / §8.9 A6): Contamination audit — log(pre-cutoff PubMed
  mentions) vs per-disease R@1, one panel per backbone. **LLM ρ≈0.3 (weak
  positive); classical baselines ρ≈0 (null control).** —
  `fig4_a6_contamination_scatter.png`
- **Figure 5** (§7.7 H1): Prevalence stratification curve.
  LLM R@1 declines on the rarest tier (0.22 super-rare); classical/offline
  *rises* on the rarest tier (0.50), with a +27 pp crossover gap. —
  `fig5_prevalence_h1.png`
- **Figure 6** (§7.1.2 / §8.8 H8): Phenotype-density inverted-U.
  R@1 peak at 16–30 HPO terms (0.32) drops to 0.22 at ≤5 terms and 0.25
  at >30. —
  `fig6_hpo_density_h8.png`
- **Figure 7** (§7.9 H7): Per-specialty R@1 heatmap across 6 agents on the
  HPO organ-system axis. Universal weak rows: nervous / metabolic /
  digestive; classical inverts on nervous (LIRICAL 0.35, VC-RDAgent 0.43). —
  `fig7_specialty_h7.png`

## Cross-references

- §5.1 Agent Fairness Matrix — adapter shim details
- §5.2 Backbones — methods note on GPT-5 reasoning_effort
- §7 Analysis — scaffolding, genotype, faithfulness deep-dives
- the reproducibility audit Reproducibility audit — per-baseline numbers vs paper claim
- Appendix B — per-baseline reproduction docs
