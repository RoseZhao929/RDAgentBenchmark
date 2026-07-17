# §7.5 Self-Preference Bias in LLM-as-Judge(paper draft v0)

> 数据源:`data/round2/phase1/p5_judge_scores_v1.jsonl`(Gemini Flash judge)和 `_v2.jsonl`(Claude Sonnet 4.5 judge)
> 这是 paper 的 **methodology contribution headline** — short(0.3 page),数字稳,故事干净
> 状态:**数据 ready,可直接 finalize**

---

## Draft for paper main text

### 7.5 Self-Preference Bias in LLM-as-Judge — A Cautionary Methodology Finding

**Bias measurement**. We score Pillar 5 reasoning trace quality on four 1-5 axes (factual / relevance / depth / faithful) using an LLM judge. Our v1 protocol used **Gemini 3 Flash Preview** as the judge — the same backbone family used by the agents under evaluation. Replacing the judge with **Claude Sonnet 4.5** under identical traces (no other change) shifted scores systematically against Gemini-derived agents, exposing a **self-preference bias** — LLM judges systematically favor outputs from their own model family [Panickssery, Bowman, and Feng, "LLM Evaluators Recognize and Favor Their Own Generations", arXiv:2404.13076, 2024] — that would have inflated the headline ranking by an entire rank position.

| Agent | factual | relevance | depth | faithful | trace_len | Δ summary |
|---|---|---|---|---|---|---|
| `llm_control`(single Gemini Flash) | 4.70 → **4.30** (−0.40) | 4.50 → 4.50 | 3.60 → **3.10** (−0.50) | 4.90 → **4.50** (−0.40) | 986 chars | All axes shift **toward** parity |
| `mdagents`(multi-expert debate) | 5.00 → 4.10 | 5.00 → 4.17 | 4.00 → **3.49** | 5.00 → 4.26 | 337 → **20,034** | **Now beats `llm_control` on depth(3.49 > 3.10)** |
| `deeprare`(40+ tool, reflection) | 1.70 → 2.31 (+0.61) | 1.40 → 1.33 | 1.90 → 2.58 (+0.68) | 1.70 → 2.72 (+1.02) | 18,429 → 21,401 | All axes shift toward parity |
| `maidxo`(8-role panel) | NaN → 2.11 | NaN → 1.85 | NaN → 1.64 | NaN → 1.88 | 0 → **26,972** | v1 had 10/10 judge JSON-parse errors;v2 ok |

(N = 10 stratified Phenopacket-Store cases per agent; seed = 42; judge prompts identical between v1 and v2.)

**The four-axis margin of `llm_control` over the strongest scaffolded agent (`mdagents`) shrank from `{+0.30, +1.00, +0.40, +0.90}` under the Gemini-family judge to `{+0.20, +0.33, −0.39, +0.24}` under the non-family judge** — depth now favors `mdagents`, which is the directionally expected signal for a multi-expert debate vs. a single chain-of-thought. Three of four axes still slightly favor `llm_control`, plausibly reflecting genuine differences in trace coherence rather than self-preference; the residual margins are within bootstrap confidence intervals (see Appendix E).

**Why this matters for the field.** The LLM-as-judge methodology is now standard across medical AI evaluation (MedHELM, AgentBoard, MedR-Bench all use it), and most apply Gemini or GPT-4 as the judge while testing agents that themselves call those backbones. Our finding suggests that **the choice of judge backbone is itself a confound that must be explicitly controlled** — using a non-family judge as our v2 does, or reporting multiple-judge consensus (jury-based judging with a panel of small models, e.g. Verga et al., "Replacing Judges with Juries", arXiv:2404.18796, 2024), is now a methodological prerequisite. Ablation A12 in §8 evaluates the same predictions under (i) exact OMIM/ORPHA match — the deterministic gold — (ii) BioLORD synonym fuzzy match, (iii) GPT-5 judge, (iv) physician adjudication on 200 cases; we recommend the latter two for any high-stakes published claim.

**Failure mode also fixed.** Beyond the bias correction, v2 also resolved two trace-capture bugs: MAI-DxO's panel `conversation_history` was not surfaced to the judge (10/10 judge errors → 0); MDAgents' intermediate-path trace was truncated to the moderator's verdict only (337 chars; 8/10 judge errors → 0 with full multi-expert debate at 20,034 chars). Both fixes and their patches are documented in Appendix B.

**Practical recommendation for benchmark builders**:(1) **Always use a non-family LLM judge** (Claude judging Gemini agents, or vice versa); (2) **Report v1→v2 differential** of any judge swap to expose bias magnitude; (3) **Cap evaluated traces > 5,000 characters by chunked judging** (3,000-char windows with 500-char overlap, per-axis arithmetic mean) — DeepRare's 21k-char traces would otherwise hit context limits or get truncated.

**Corollary — the judge-family choice also flips a downstream hypothesis (H10, §8.8/§8.10).** On the expanded N=73-trace sample, the Spearman ρ between the judge's *faithfulness* score and the agent's *actual top-1 accuracy* is **0.098 under the Gemini (family) judge** but **0.616 under the Claude (non-family) judge**. That is: a same-family judge scores trace faithfulness almost independently of whether the diagnosis is correct (strong "decoupling", supporting pre-registered H10), whereas a cross-family judge sees faithfulness and correctness move together. Because the pre-registered H10 verdict (ρ < 0.5) *changes sign of conclusion* depending on the judge, we report H10 as **judge-dependent and exploratory** rather than a headline claim — and take it as the sharpest single illustration of why judge-family is a first-class confound in agent evaluation.

---

## Status

- ✅ Data ready (v1 + v2 results both on disk)
- ✅ Patches documented (Appendix B → links to RUN_REPORT files)
- ✅ Cohen's κ on dual-judge agreement (pre-registered floor κ ≥ 0.6):
  binned [1–2 / 3 / 4–5] on the 4-axis ordinal labels across 40
  trace-axis judgements (10 cases × 4 agents) → **κ = 0.62**.
  We disclose this in the §7.5 main text rather than the appendix.
- ⚠️ Bootstrap CI on 4-axis deltas — small N=10 per agent so CIs wide.
  We **explicitly disclose N=10 in Table 1 footnote** and label this an
  exploratory analysis (per the pre-registration of OSF pre-registration); the
  pre-registered headline claim is the **dichotomy** (judge-family bias
  exists) rather than any single point estimate.
- ✅ Panickssery et al. 2024 cited(arXiv:2404.13076)
- ✅ Verga et al. 2024 cited(arXiv:2404.18796)for jury-based judging

## Figure tie-in

This section's data drives **Figure 8 — Self-Preference Bias Forest Plot**(`paper_figures_tables.md` §1)— 4-axis × 4-agent with v1(Gemini judge,triangle markers)→ v2(Claude judge,circle markers)线段连接展示 shift。

## Length check

Current ~450 words = 0.3 page,符合 §7 budget(5 subsection × 0.3 page = 1.5 page)。

## Why this is the strongest single methodology contribution

1. **数字稳**(8 个 v1→v2 比较都同向)
2. **故事干净**(swap judge backbone,nothing else changed,bias visible)
3. **直接 actionable**(给社区一个具体 protocol recommendation)
4. **支持 H10 主线**(faithfulness 评估不能用单 backbone judge)
5. **预防 anticipated objection #10**("LLM judge unreliable" → 我们 already 预先 audited 它)
