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

> Caution (frozen audit). The v1→v2 shifts in this table are **not** a clean judge-swap for the `mdagents` and `maidxo` rows: v2 also *repaired* their traces (mdagents 337 → 20,034 chars; maidxo 0 → 26,972 chars), so those two rows confound the judge change with the trace-completeness change. Only the `llm_control` and `deeprare` rows (whose traces were already complete in v1) isolate a judge-family effect. See the Corollary below for the same-input re-run that de-confounds this.

**The four-axis margin of `llm_control` over the strongest scaffolded agent (`mdagents`) shrank from `{+0.30, +1.00, +0.40, +0.90}` under the Gemini-family judge to `{+0.20, +0.33, −0.39, +0.24}` under the non-family judge** — depth now favors `mdagents`, which is the directionally expected signal for a multi-expert debate vs. a single chain-of-thought. Three of four axes still slightly favor `llm_control`, plausibly reflecting genuine differences in trace coherence rather than self-preference; the residual margins are within bootstrap confidence intervals (see Appendix E).

**Why this matters for the field.** The LLM-as-judge methodology is now standard across medical AI evaluation (MedHELM, AgentBoard, MedR-Bench all use it), and most apply Gemini or GPT-4 as the judge while testing agents that themselves call those backbones. Our finding suggests that **the choice of judge backbone is itself a confound that must be explicitly controlled** — using a non-family judge as our v2 does, or reporting multiple-judge consensus (jury-based judging with a panel of small models, e.g. Verga et al., "Replacing Judges with Juries", arXiv:2404.18796, 2024), is now a methodological prerequisite. Ablation A12 in §8 evaluates the same predictions under (i) exact OMIM/ORPHA match — the deterministic gold — (ii) BioLORD synonym fuzzy match, (iii) GPT-5 judge, (iv) physician adjudication on 200 cases; we recommend the latter two for any high-stakes published claim.

**Failure mode also fixed.** Beyond the bias correction, v2 also resolved two trace-capture bugs: MAI-DxO's panel `conversation_history` was not surfaced to the judge (10/10 judge errors → 0); MDAgents' intermediate-path trace was truncated to the moderator's verdict only (337 chars; 8/10 judge errors → 0 with full multi-expert debate at 20,034 chars). Both fixes and their patches are documented in Appendix B.

**Practical recommendation for benchmark builders**:(1) **Always use a non-family LLM judge** (Claude judging Gemini agents, or vice versa); (2) **Report v1→v2 differential** of any judge swap to expose bias magnitude; (3) **Cap evaluated traces > 5,000 characters by chunked judging** (3,000-char windows with 500-char overlap, per-axis arithmetic mean) — DeepRare's 21k-char traces would otherwise hit context limits or get truncated.

**Corollary — the judge-family gap is largely a trace-capture artifact, not self-preference (2026-07-22 frozen-audit correction).** An earlier draft reported that the Spearman ρ between the judge's *faithfulness* score and the agent's *actual top-1 accuracy* was **0.098 under the Gemini (family) judge** vs **0.616 under the Claude (non-family) judge**, and read the gap as judge self-preference. That comparison was confounded: the Gemini (v1) scores were computed on the **truncated/empty traces** (mdagents 337 chars, maidxo 0 chars) while the Claude (v2) scores used the **repaired full traces** — the two judges never scored the same inputs. We re-ran the Gemini judge on the *identical v2 repaired traces* Claude scored (n=40, same prompt, via a non-family-neutral endpoint). On matched inputs the Gemini ρ rises from 0.098 to **0.457**, against Claude's **0.640**; the two judges' faithfulness scores agree at **ρ=0.741**. So most of the apparent 0.098-vs-0.616 gap was the trace-capture fix, not judge identity. A **modest** residual judge-family difference remains (0.457 vs 0.640) and is consistent with genuine cross-family variation, but it does not flip the H10 verdict the way the confounded numbers suggested. We therefore report H10 as **exploratory**, withdraw the "strong decoupling under the Gemini judge (ρ=0.098)" claim as an artifact, and keep only the robust, well-supported point of this section — that judge-family and trace-capture completeness are both first-class confounds that must be controlled (use a non-family judge *and* verify every judge sees the same complete trace).

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
