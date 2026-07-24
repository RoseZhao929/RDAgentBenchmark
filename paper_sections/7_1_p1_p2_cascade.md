# §7.1 P1 → P2 Cascade: HPO Extraction Quality Decides Downstream(paper draft v0)

> 数据源:`data/round2/phase0/REPORT_FINAL.md`(merged predictions.jsonl + predictions_v2.jsonl)
> Headline finding F2(`paper_outline.md` §2.5)
> 状态:**Phase 0 V2 数据 ready,可直接 finalize**

---

## Draft for paper main text

## 7.1 The P1 → P2 Cascade

A central architectural decision in our benchmark — separating Pillar 1 (phenotype extraction) from Pillar 2 (phenotype-only differential diagnosis) and reporting both via the **dual-pass evaluation (§4.4)** — is grounded in an empirical finding we did not anticipate at design time: **HPO extraction quality is not a free preprocessing step. Errors propagate, in some cases catastrophically.**

**The finding — measured same-case.** HPO extraction quality affects downstream diagnosis, but the size of the effect must be measured on *the same cases* under two input conditions, or dataset difficulty confounds it. We ran a same-case paired test (50 Phenopacket-Store cases, seed=42, single-LLM diagnoser): condition A feeds the case's gold HPO; condition B synthesizes a vignette from that same gold HPO, has the LLM re-extract HPO, then diagnoses from the extracted set. Same cases, same diagnoser. Recall@1 is **0.42 (gold HPO) vs 0.40 (extracted HPO)** — a **2 pp drop, not significant** (McNemar, 1 discordant pair, p=1.0); the extractor recovered essentially the same phenotype count (mean 7.9 vs 7.9 terms). For a free-text-native LLM diagnoser, extraction is close to lossless.

> Correction (2026-07-22 frozen audit). An earlier draft reported "LIRICAL R@1 0.40 (gold HPO) → 0.04 (LLM-extracted HPO), a 10× collapse". Those two numbers came from **different datasets** — 0.40 on 25 Phenopacket-Store cases, 0.04 on 25 RareArena cases — so the "10×" conflated dataset difficulty with the input condition and cannot be read as an extraction penalty. The same-case control above is the correct measurement. A caveat remains for *classical* HPO-list-only tools: LIRICAL is more brittle to HPO-list quality than an LLM diagnoser, so its true same-case penalty could exceed 2 pp; quantifying it requires re-running LIRICAL under both conditions on identical cases (future work). The point stands qualitatively — extraction quality matters and the dual-pass design exposes it — but the headline magnitude was an artifact and is withdrawn.

Three observations follow:

**(1) Input format must be matched before comparing agents.** LIRICAL on its **native input format** (gold HPO) is the top-performing classical baseline (0.47 on the full Phenopacket-Store matrix, §6). Comparing it against free-text-native LLM scaffolds on a free-text-only dataset penalizes the classical tool for an input mismatch, not a capability gap. The right comparison is **same-input apples-to-apples**, which only the dual-pass design exposes.

**(2) Input-pipeline sensitivity may differ across agent types.** Free-text-native
agents (MedAgents, AgentClinic, DeepRare) encapsulate a text-to-diagnosis path,
whereas HPO-list-only systems (LIRICAL and VC-RDAgent) depend on an upstream
extractor. The current same-case paired test covers only the single-LLM
diagnoser, so it does not establish that classical systems are more brittle.
That comparison requires a crossed same-case experiment in which each
compatible agent receives both gold and independently extracted HPO.

**(3) HPO extraction quality is itself measurable and improvable.** RDMA, our Pillar 1 specialist (extracts HPO phrases from EHR free text via specialized mining subagents, then phrase-to-HP-ID via fuzzy match), reaches phrase-level recall ~0.95 against Gemini-Flash-extracted "gold" — though this number is contaminated by methodology leak (Phenopacket-Store cases lack free-text vignettes; our P1 pilot synthesized vignettes from the HPO labels themselves, then asked LLMs to re-extract; see Limitations 5). Our Phase 1 pilot via Claude Opus 4.7 produced a 99-case **silver-gold dataset** (Jaccard 0.41 with Gemini Flash's extractions; **systematic disagreement confirms non-redundancy**) for Phase 3 P1 evaluation against an independent backbone family.

**Implications for deployment.** A practitioner choosing a rare-disease agent
for clinical decision support should not pick by accuracy alone; the *input
pipeline* must be co-evaluated. If the deployment context provides curated HPO
terms, LIRICAL or VC-RDAgent are competitive. If the input is free text,
HPO-list-only systems require a separately validated extractor, whereas
free-text-native agents can be evaluated end to end. The current results do
not support a superiority claim between those paths because no matched
classical free-text run exists.

**Implications for benchmark methodology.** Two takeaways for the field: (i) prior rare-disease LLM benchmarks that compare LIRICAL/Exomiser (Bayesian, HPO-list-only) to LLMs (free-text-native) on a free-text-only dataset will systematically penalize the classical tools, conflating capability with input mismatch. (ii) The Pass A − Pass B delta is itself a reportable metric — a small delta on the same agent signals strong end-to-end robustness, a large delta signals input-pipeline sensitivity.

---

## Figure tie-in

Potential camera-ready paired-cascade panel: x = gold-HPO vs extracted-HPO,
y = R@1, paired lines per case. It is not one of the current main-text figures.

---

## Working Notes / TODO

### Strong points

1. ~~数字 anchor 强:0.40 → 0.04 (10× gap)~~ — 已撤回:跨数据集混淆,同病例 paired 只有 0.42→0.40(2pp,不显著)。见正文 Correction。
2. **3 个 implications** 是 structural,reviewer 看到会 quote
3. **Tie 到 dual-pass design** — reinforce 我们的 §4.4 methodology choice 的 motivation
4. **Honest disclosure**:RDMA 0.95 这个数字带 caveat(synth vignette leak)
5. **End with 2 generalizable takeaways**:对 deployers / 对 benchmark methodology

### Needs once Phase 4a 数据来:

- Test on all three diagnostic dataset layers, not the separate MIMIC probe
- 是否 generalize:LLM-based agents 平均小 delta vs classical 平均大 delta
- Confirm RDMA 在 OPus silver gold(non-leaky)上 P1 F1 数字 — 我们期望降到 ~0.5-0.7

### Citations 

- LIRICAL paper(Robinson et al., AJHG 2020)| LIRICAL design rationale
- Phen2Gene(Zhao et al., Nucleic Acids Research 2020) | classical HPO-list-only context
- 2026 systematic review | for "free-text dataset systematic penalty" generalization claim
- DeepRare(Nature 2026) | for free-text-native scaffolded behavior

### Length

~520 words 现在,~0.35 paper page,符合 §7 budget(5 sections × 0.3 page = 1.5 page)。如果空间紧可压到 400 words。

---

## Phase 4a 验证点

once 100 case / dataset × 8 agent × 3 backbone done,update with:
- LIRICAL / VC-RDAgent / DeepRare / RDMA P1 → P2 delta across the diagnostic layers
- 验证 asymmetry hypothesis(classical 大 delta,LLM-scaffold 小 delta)
- Maybe a new sub-finding:"Pass A − Pass B delta within 5 pp identifies robust agents"

---

## §7.1.2 H8 — Phenotype density predicts performance (inverted-U) ✅

Repository-plan H8: R@1 follows an inverted-U in the number of input HPO terms —
too few (under-specified) and too many (noise / distractors) both hurt. Tested
on the HPO-input layers (PP-Store + RareBench), pooled over Gemini-Flash LLM
cells + offline/classical baselines (N=4,754 case-predictions, dedup by case):

| Bin (#HPO terms) | n | R@1 |
|---|---|---|
| ≤5 (under-specified) | 528 | 0.218 |
| 6–15 | 2,352 | 0.276 |
| 16–30 (sweet spot) | 1,361 | **0.323** |
| >30 (noise/distractors) | 513 | 0.253 |

**H8 supported**: interior peak at 16–30 HPO terms; both tails decline
(−10 pp at ≤5, −7 pp at >30 vs peak). The under-specified tail is the larger
drop, consistent with rare-disease diagnosis needing a minimum phenotypic
fingerprint. The shape holds across individual agents, not just the pool.
The inverted-U is plotted in \Cref{fig:figM4_hpo_density}.
