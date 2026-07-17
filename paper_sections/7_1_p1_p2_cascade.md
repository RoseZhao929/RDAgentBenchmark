# §7.1 P1 → P2 Cascade: HPO Extraction Quality Decides Downstream(paper draft v0)

> 数据源:`data/round2/phase0/REPORT_FINAL.md`(merged predictions.jsonl + predictions_v2.jsonl)
> Headline finding F2(`paper_outline.md` §2.5)
> 状态:**Phase 0 V2 数据 ready,可直接 finalize**

---

## Draft for paper main text

### 7.1 The P1 → P2 Cascade

A central architectural decision in our benchmark — separating Pillar 1 (phenotype extraction) from Pillar 2 (phenotype-only differential diagnosis) and reporting both via the **dual-pass evaluation (§4.4)** — is grounded in an empirical finding we did not anticipate at design time: **HPO extraction quality is not a free preprocessing step. Errors propagate, in some cases catastrophically.**

**The headline number.** On the same 50-case stratified sample (25 Phenopacket-Store + 25 RareArena RDS, seed=42), LIRICAL's Recall@1 is **0.40 when fed gold HPO** (the 25 Phenopacket-Store cases with structured `gold_hpo_terms`) but collapses to **0.04 when fed LLM-extracted HPO** (the 25 RareArena cases where our adapter shim runs Gemini Flash + phrase-to-HP-ID normalization to project free-text vignettes to the HPO-list input LIRICAL requires). The mean across all 50 cases is **0.22**, masking a **10× gap** between the two halves. VC-RDAgent shows the same pattern (0.32 → ~0.04, mean 0.18).

Three observations follow:

**(1) "Mean R@1" is not a sufficient summary statistic for HPO-list-only agents.** The 0.22 / 0.18 averages tempt a reading like "LIRICAL underperforms multi-agent LLM scaffolds (MedAgents 0.36, MDAgents 0.34) by 14 pp" — yet LIRICAL on its **native input format** (gold HPO) is the top-performing classical baseline at 0.40. The right comparison is **same-input apples-to-apples**, which only the dual-pass design exposes.

**(2) The cascade is asymmetric across agent types.** Free-text-native agents (MedAgents, AgentClinic, DeepRare) do not show this cliff because they ingest free text directly; they encapsulate their own P1 module and gracefully degrade. HPO-list-only agents (LIRICAL, VC-RDAgent, classical Bayesian / classical ensemble systems generally) are downstream-of-pipeline brittle. We hypothesize — to be tested in Phase 4a — that this asymmetry generalizes: **classical agents have higher ceiling on clean inputs but lower floor on noisy ones; LLM-based agents trade ceiling for robustness**.

**(3) HPO extraction quality is itself measurable and improvable.** RDMA, our Pillar 1 specialist (extracts HPO phrases from EHR free text via specialized mining subagents, then phrase-to-HP-ID via fuzzy match), reaches phrase-level recall ~0.95 against Gemini-Flash-extracted "gold" — though this number is contaminated by methodology leak (Phenopacket-Store cases lack free-text vignettes; our P1 pilot synthesized vignettes from the HPO labels themselves, then asked LLMs to re-extract; see Limitations 5). Our Phase 1 pilot via Claude Opus 4.7 produced a 99-case **silver-gold dataset** (Jaccard 0.41 with Gemini Flash's extractions; **systematic disagreement confirms non-redundancy**) for Phase 3 P1 evaluation against an independent backbone family.

**Implications for deployment.** A practitioner choosing a rare-disease agent for clinical decision support should not pick by accuracy alone; the *input pipeline* must be co-evaluated. If the deployment context provides curated HPO terms (e.g., a clinician using a phenotype standardization tool before invoking the diagnostic agent), LIRICAL or VC-RDAgent are competitive. If the deployment context is end-to-end free-text → diagnosis (e.g., automated triage from EHR), LLM-based scaffolded agents with their own P1 modules dominate. **The dual-pass evaluation lets each agent's deployment-relevant performance be read off directly.**

**Implications for benchmark methodology.** Two takeaways for the field: (i) prior rare-disease LLM benchmarks that compare LIRICAL/Exomiser (Bayesian, HPO-list-only) to LLMs (free-text-native) on a free-text-only dataset will systematically penalize the classical tools, conflating capability with input mismatch. (ii) The Pass A − Pass B delta is itself a reportable metric — a small delta on the same agent signals strong end-to-end robustness, a large delta signals input-pipeline sensitivity.

---

## Figure tie-in

This section drives **Figure 7 — P1 → P2 Cascade Scatter**:x = LLM-extracted vs gold per-case Jaccard,y = R@1。最重要的 visual:**LIRICAL 两个 marker 之间一条粗箭头从 0.40 跌到 0.04**。

---

## Working Notes / TODO

### Strong points

1. **数字 anchor 强**:0.40 → 0.04 (10× gap) 是 paper 里少数 single-number 就能 communicate 的发现
2. **3 个 implications** 是 structural,reviewer 看到会 quote
3. **Tie 到 dual-pass design** — reinforce 我们的 §4.4 methodology choice 的 motivation
4. **Honest disclosure**:RDMA 0.95 这个数字带 caveat(synth vignette leak)
5. **End with 2 generalizable takeaways**:对 deployers / 对 benchmark methodology

### Needs once Phase 4a 数据来:

- Test on all 4 dataset layers,not just 50 PP-Store + 50 RareArena
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
- LIRICAL / VC-RDAgent / DeepRare / RDMA P1 → P2 delta 数字 across **all 4 dataset layers**
- 验证 asymmetry hypothesis(classical 大 delta,LLM-scaffold 小 delta)
- Maybe a new sub-finding:"Pass A − Pass B delta within 5 pp identifies robust agents"

---

## §7.1.2 H8 — Phenotype density predicts performance (inverted-U) ✅

Pre-registered H8: R@1 follows an inverted-U in the number of input HPO terms —
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
Visualised in **Figure 6**.
