# §7.5 Judge-Swap Sensitivity and Coupled Family/Trace Confounds

> 数据源:`data/round2/phase1/p5_judge_scores_v1.jsonl`(Gemini Flash judge)和 `_v2.jsonl`(Claude Sonnet 4.5 judge)
> 状态:冻结审计已校正因果表述;同 trace 复评 ready

---

## Draft for paper main text

**Measurement and estimand.** We score Pillar 5 reasoning traces on four
1--5 axes (factuality, relevance, depth, and faithfulness). Version 1 used
Gemini 3 Flash Preview, which shares a model family with the evaluated
Gemini agents; version 2 used Claude Sonnet 4.5, a cross-family judge. This is
not a one-variable family-awareness ablation: Gemini-to-Claude changes both
the judge model and its family relation to the agent. Moreover, two v2 rows
also repair incomplete traces. We therefore interpret the raw slopes as
**judge-protocol sensitivity**, not a causal estimate of self-preference.

The `llm_control` and `deeprare` traces were already complete in v1, so their
rows isolate a judge-model swap on unchanged inputs. They still do **not**
separate judge identity from family relation. The `mdagents` and `maidxo`
rows additionally confound that swap with trace completeness (`mdagents`:
337 to 20,034 characters; `maidxo`: 0 to 26,972). The judge-swap figure therefore draws
`mdagents` as a dashed, descriptive contrast and omits the unusable v1
`maidxo` endpoint.

Descriptively, the four-axis margin of `llm_control` over `mdagents` changes
from `{+0.30, +1.00, +0.40, +0.90}` to
`{+0.20, +0.33, -0.39, +0.24}`, with depth reversing in favor of
`mdagents`. Because the `mdagents` trace was repaired between versions, this
reversal cannot be attributed to the judge or family relation alone.

**Same-input check.** We subsequently re-ran Gemini on the same 40 repaired
traces scored by Claude, using the same prompt. The faithfulness--accuracy
Spearman correlation is 0.457 for Gemini and 0.640 for Claude, while the two
judges' faithfulness scores agree at 0.741. Thus most of the earlier
0.098-versus-0.616 contrast came from trace capture, not a judge-family
effect. The residual difference is modest and could reflect family
preference, model-specific calibration, or both; H10 therefore remains
exploratory. Unweighted Cohen's κ=0.477 after binning the four axes into 1--2/3/4--5
(160 paired axis labels from 40 traces). Because the four axes within a trace
are not independent and there are only 10 cases per agent, this is a
sensitivity check rather than a precise effect estimate.

**Protocol implication.** A non-family judge alone is not a clean control.
Future evaluation should freeze identical complete traces, apply multiple
judges, and cross judge family with generator family. This design separates
general judge severity from an own-family interaction. For long traces, we
also use chunked judging rather than silent truncation. The v2 repair exposed
MAI-DxO's `conversation_history` and MDAgents' full intermediate debate to
the judge; both fixes are documented in Appendix B.

This correction withdraws the earlier claim that the raw v1-to-v2 change
demonstrates self-preference. Prior work makes such bias plausible
\citep{panickssery2024}, but the present experiment establishes
sensitivity to the combined judging protocol, not which component caused it.

| Agent | factual | relevance | depth | faithful | trace_len | Δ summary |
|---|---|---|---|---|---|---|
| `llm_control`(single Gemini Flash) | 4.70 → **4.30** (−0.40) | 4.50 → 4.50 | 3.60 → **3.10** (−0.50) | 4.90 → **4.50** (−0.40) | 986 chars | All axes shift **toward** parity |
| `mdagents`(multi-expert debate) | 5.00 → 4.10 | 5.00 → 4.17 | 4.00 → **3.49** | 5.00 → 4.26 | 337 → **20,034** | **Now beats `llm_control` on depth(3.49 > 3.10)** |
| `deeprare`(40+ tool, reflection) | 1.70 → 2.31 (+0.61) | 1.40 → 1.33 | 1.90 → 2.58 (+0.68) | 1.70 → 2.72 (+1.02) | 18,429 → 21,401 | All axes shift toward parity |
| `maidxo`(8-role panel) | — → 2.11 | — → 1.85 | — → 1.64 | — → 1.88 | 0 → **26,972** | v1 had 10/10 judge JSON-parse errors; v2 ok |

(N = 10 stratified Phenopacket-Store cases per agent; seed = 42; judge
prompts were identical, but judge identity/family relation changed and the
`mdagents`/`maidxo` inputs were repaired.)
