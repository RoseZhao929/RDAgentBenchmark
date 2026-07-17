# LLM Control Reproduction Documentation

## Source

- Repo: **internal** — single-file adapter `harness/agents/llm_control.py`
- This is NOT an external baseline — it's our own zero-scaffold control
  ("naked LLM call") to quantify what raw frontier LLMs achieve without
  any agent infrastructure.
- License: this project's Apache 2.0

## Paper-claimed results

n/a — internal baseline; numbers are our own.

## How we reproduce

- **Pillar 1**: structured output prompt asking for HPO phrases + IDs
- **Pillar 2**: structured output prompt asking for top-5 rare disease
  candidates with ORPHA / OMIM IDs
- **Pillar 3**: same as P2 + structured variants block appended to
  prompt (`gene_symbol`, `hgvs_c`, `acmg`, `zygosity`)
- **Pillar 5**: judge prompt with rubric (faithfulness scoring)
- **Backbone**: configurable via `--backbone openrouter/<model>`
- **Sample**: 50 case for pilot, scales to N=full for main eval

## Endpoint patches

n/a — this is our code, we built it for OpenRouter from day 1.

## Behavior-changing patches

n/a.

## Reasoning configuration (2026-07-03)

The LLM control runs each backbone in its minimal/off reasoning config (§5.2):
GPT-5 `reasoning_effort=minimal`, DeepSeek-V4-Pro `reasoning={"enabled": false}`
(via `reasoning_disabled_for_backbone`; V4-Pro ignores `effort=minimal`),
Gemini/V4-Flash default. For the **H6 thinking-mode ablation** the runner flag
`--reasoning_on` sets `agent_extra={"force_reasoning_on": True}`, which keeps
reasoning ON for V4-Pro; those runs live in
`data/round2/phase4a_h6_reasoning_on/` and never merge into the main matrix.
Verified: reasoning-off ~2.5 s/case, reasoning-on ~24 s/case (10×), both emit
valid content.

## Adapter wrapper

- File: `harness/agents/llm_control.py`
- Single LLM call per pillar, structured-output schema
- Pillar 1: extract HPO phrases + IDs
- Pillar 2/3: rank top-5 candidates
- Pillar 5: faithfulness judge with rubric

## Observed results vs internal expectation

| Pillar | Backbone | n_ok | R@1 | R@5 / F1 |
|---|---|---|---|---|
| P1 phrase-extraction | Gemini Flash | 50/50 | n/a | F1 ≈ 0.4 (vs Opus 4.7 silver gold) |
| P2 HPO-only DDx | Gemini Flash | 50/50 | **0.26** | 0.38 |
| P2 HPO-only DDx | DeepSeek V3.2 | 50/50 | ~0.30 | — |
| P2 HPO-only DDx | GPT-5 (minimal) | 50/50 | ~0.20 | — |
| **P3 HPO + variants** | Gemini Flash | 50/50 | **0.46** | 0.58 |

P3 vs P2 on same agent = +20pp lift from structured variants. Confirms
H2 (variant channel adds signal) for any LLM that ingests structured
genotype.

## Known incompatibilities

### DeepSeek V4-Flash / V4-Pro empty-content on RareBench/MIMIC (2026-05-28)

`content_len=0` parser_errors clustered on RareBench/MIMIC (V4-Flash rarebench
~38, mimic ~40; V4-Pro rarebench ~30). Same transient-empty root cause as
medagents (see `medagents.md`): the backbone returns an HTTP-200 response with
`content=""`. **Fix (wrapper-only):** `_chat_with_retry` now treats an empty
extracted content as transient and retries (reusing `max_retries=2`, 3 total
attempts), same as a network error. Non-empty-but-unparseable responses
(`content_len=1017` etc.) are NOT retried — genuine format issues stay
`parser_error`. Network errors (SSLError / ChunkedEncodingError) were already
retried; re-running recovers those too.

## Run receipts

- Phase 0 V3: `data/round2/phase0/predictions_v3.jsonl`
- Phase 2 (3 backbone): `data/round2/phase2/`
- Phase 3.2 P3: `data/round2/phase3/p3_genotype.jsonl`
- P1 silver gold: `data/round2/phase3/p1_silvergold.jsonl`

## Last-updated

- 2026-05-19 — Initial doc; full pilot complete
