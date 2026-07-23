# §5.2-5.4 Experimental Setup — Backbones / Adapter Methodology / Pre-registration (paper draft v0)

> 数据来源:
> - §5.2 backbone 价格:OpenRouter 2026-05 公开报价 + `harness/logging/openrouter_wrapper.py:PRICE_TABLE`
> - §5.3 adapter pattern:`harness/agents/*.py`(3,485 LOC),round2_worklog Retrospective #1-4
> - §5.4 pre-registration:`round2_plan.md` H1-H11 + A1-A12,OSF 提交 user TODO(holdout unblind 前)
>
> 写作目的:回答"How exactly is the experiment configured? Is it reproducible?"
> 状态:文字 + 表 ready,等 OSF 链接落定后插 footnote

---

## §5.2 Backbones

We evaluate every LLM-driven agent against four backbones spanning the
cost–capability frontier: DeepSeek V4-Flash (open-weight, low-cost), DeepSeek
V4-Pro (open-weight frontier, reasoning disabled), Gemini 3 Flash (our primary
baseline), and GPT-5 (frontier, minimal reasoning). All are accessed through
OpenRouter for version-pinned endpoints and a single billing and logging
surface. Their dated aliases, pricing, context windows and the generation
settings held constant across every cell are listed in Appendix
Table \ref{tbl:backbones}.

**All four backbones are evaluated in their minimal/off reasoning
configuration** (Gemini thinking-off, GPT-5 `reasoning_effort=minimal`,
DeepSeek-V4-Pro reasoning disabled, V4-Flash light-reasoning within budget).
This is a deliberate design choice, not an artifact: (i) it **isolates the
scaffolding contribution** — the benchmark's object of study is whether agent
scaffolds help, so the backbone's internal chain-of-thought is held to a
constant floor rather than left to confound scaffold-vs-backbone-CoT gains;
(ii) it matches the **original operating point of the reproduced agents**
(MDAgents/MedAgents/AgentClinic were published on non-reasoning GPT-3.5/GPT-4);
and (iii) it is required for **tractability** at N=10³ cases × multi-call
scaffolds. We report reasoning-on separately as a thinking-mode ablation
(**H6 / Ablation A8**, §8) on the single-call LLM control.

**Methods note 1 (GPT-5, reviewer-defensive).**  GPT-5's default
`reasoning_effort=high` silently routes the full `max_tokens` budget into
hidden reasoning tokens, returning empty `content`. In our first Phase 2 GPT-5
run this manifested catastrophically: 50/50 MedAgents `parser_error` (raw
response empty), 50/50 AgentClinic timeout, 46/50 MAI-DxO timeout. We force
`reasoning_effort=minimal` for all primary results, propagating the flag
through subprocess-isolated adapters via the `OPENROUTER_REASONING_EFFORT`
environment variable.
MAI-DxO + GPT-5 remained incompatible even at `minimal` (panel orchestration ×
max_iter=3 exceeds the subprocess cap); we document the incompat in §9
Limitations and exclude that single cell, **not** the GPT-5 row.

**Methods note 2 (DeepSeek-V4-Pro, reviewer-defensive).**  V4-Pro is a heavy
reasoning model whose reasoning is *unbounded* and, unlike GPT-5, ignores every
throttle knob — verified on a hard prompt (N≥3 each): `reasoning_effort=minimal`
and `reasoning_effort=low` are both ignored (reasoning still fills the budget);
capping via `reasoning={max_tokens:200}` is ignored; and simply enlarging
`max_tokens` is self-defeating because reasoning scales to consume whatever it
is given (at `max_tokens=2500` the synthesiser emitted content in 0/4 trials;
at 4000, 3/4 but one trial still consumed all 4000). The subprocess baselines
size `max_tokens` for non-reasoning models (AgentClinic doctor turn 200;
MedAgents synthesiser 600), so V4-Pro's reasoning consumed the entire budget
and returned empty `content`, surfacing as AgentClinic retry-loop timeouts
(45–51% of cells) and MedAgents `parser_error` (34–45%). The only lever that
actually disables V4-Pro reasoning is `reasoning={"enabled": false}` (verified:
0 reasoning tokens, content in 3/3 trials, 1.9 s vs 32 s). We propagate this
via `OPENROUTER_REASONING_DISABLE` through the same subprocess-env mechanism. This puts
V4-Pro in the same reasoning-off configuration as GPT-5-minimal, restoring
cross-backbone consistency; it also cut AgentClinic wall-clock from >900 s to
~27 s/case (33×). Full root-cause receipts are recorded in our run worklog
and the per-baseline reproduction notes (Appendix B).

---

## §5.3 Per-Agent Adapter Shim Methodology

Each of the eight agents ships its own Python environment, often pinned to
an `openai < 1.0` SDK and incompatible with one another in the same process.
We isolate each adapter behind a `subprocess.run` boundary into its own
virtualenv, with a uniform Python-side `AgentAdapter`
abstract base class that takes a
`CanonicalCase` (§4.3), projects it into the agent's native input format
(MCQA prompt, OSCE scenario, phenopacket JSON, …), invokes the subprocess,
and parses stdout into a uniform `PredictionLog` (ranked candidates,
extracted HPO, latency, cost, reasoning trace, status).

Backbone wiring is **never modified in the agent's core logic**; we only
patch the openai client construction sites to accept an OpenRouter
`base_url` and propagate `OPENROUTER_API_KEY` /
`OPENROUTER_REASONING_EFFORT` / `OPENROUTER_REASONING_DISABLE` through the
subprocess env (the latter two forward `reasoning={effort}` and
`reasoning={enabled:false}` respectively; see Methods notes 1–2). Patches range
from 3 LOC in DeepRare's API interface to ~30 LOC for AgentClinic's `--openrouter`
CLI flag, and are enumerated in the Agent Fairness Matrix (Table 3 / §5.1).

**What this gives us.** (i) Per-agent reproducibility — every run report
contains the verbatim subprocess invocation. (ii) Compositional cost
accounting — our OpenRouter logging wrapper
captures token usage and dollar cost per call, propagated up through the
subprocess via a JSONL log file. (iii) Failure isolation — one agent's
RAG / panel / parser bug cannot poison another agent's evaluation.

**Caveats we surface.** (a) Subprocess isolation costs ~0.5–2 s wall-clock
overhead per case, dominated by interpreter startup; we report adapter
overhead alongside agent latency in Table 6. (b) Cost reporting is exact for
adapters using our wrapper (mdagents, medagents, agentclinic, deeprare,
maidxo, llm_control) and **estimated from tokens** for adapters whose
upstream code bypasses the wrapper (rdma, lirical, vc_rdagent). (c) Three adapters required
defensive output-dir purging to prevent first-case state leak — DeepRare's
deterministic output filename was the most severe. All such patches are documented per-agent.

---

## §5.4 Pre-registration

All hypotheses (**H1–H11**), ablations (**A1–A12**), the staged-sampling
budget guard, the Holm–Bonferroni multiple-testing correction, the
LLM-judge self-preference protocol (Gemini-judge + Claude-judge agreement
floor), and the post-cutoff holdout-unblinding procedure were frozen at
OSF prior to running any holdout case.[^osf]  To our knowledge this is
the first pre-registered rare-disease diagnostic-AI evaluation; recent
systematic reviews (Garrett et al., *npj Digital Medicine* 2026) flag the
absence of pre-registration as a primary contamination risk across the
19 LLM rare-disease studies they audited.

[^osf]: OSF registration (OSF ID assigned upon registration) (frozen 2026-MM-DD, prior to
holdout unblinding). Full pre-registration document committed to the repository on
the freeze date; the OSF copy is byte-identical at that revision.
Reviewer-accessible read-only OSF link supplied in supplementary upon
acceptance.

**Why this matters operationally.** Pre-registration means the 200-case
PMC OA post-cutoff holdout is evaluated **once**, with the metric and
agent set declared in advance — there is no opportunity to retry on a
better-looking subset. The three pre-cutoff diagnostic layers
(Phenopacket-Store, RareBench, RareArena)
remain open for development, but every cell published in Table 1 / §6
is locked to the pre-registered protocol and ships with a per-cell
reproducibility receipt (run-id, OpenRouter request-id, cost).

---

## Cross-references

- §4.3 CanonicalCase schema — adapter input contract
- §4.4 Dual-pass evaluation — gold_hpo vs end_to_end
- §5.1 Agent Fairness Matrix — per-agent patch surface
- §7.5 LLM-judge self-preference — why the judge backbone is its own variable
- §9 Limitations — MAI-DxO + GPT-5 incompat, PUMCH-ADM gap, PhenoBrain dropped
- Appendix A1 — per-agent reproducibility audit checklist
