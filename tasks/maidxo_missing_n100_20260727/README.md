# MAI-DxO missing-cell N=100 run

> **INVALID RUN — DO NOT SCORE.** Post-run semantic audit recovered swallowed
> HTTP 403 `Key limit exceeded` errors from the MAI-DxO subprocess. This
> workstation lacked the required LiteLLM gateway configuration and silently
> fell back to an exhausted direct OpenRouter key. All five receipt files and
> their state/report artifacts were moved to
> `logs/maidxo_missing_n100_20260727/invalid_gateway_403_attempt/`. The live
> Phase-4a paths are intentionally clear. Use the gated N=10 validation in
> `tasks/maidxo_n10_postparserfix_20260727/` before any new N=100 run.

This task fills the five completely absent non-PMC, non-MIMIC cells identified
on 2026-07-27:

| Dataset | Backbone | N | Full target |
|---|---|---:|---:|
| Phenopacket Store | GPT-5 | 100 | 2,000 |
| RareArena RDS | DeepSeek V4-Flash | 100 | 2,000 |
| RareArena RDS | GPT-5 | 100 | 2,000 |
| RareBench | DeepSeek V4-Flash | 100 | 1,122 |
| RareBench | GPT-5 | 100 | 1,122 |

All cells use the regex-fixed MAI-DxO adapter. Prediction files remain under
the gitignored `data/` tree. Logs and per-cell start/end metadata remain under
the gitignored `logs/` tree.

Run or resume:

```bash
python3 tasks/maidxo_missing_n100_20260727/supervise.py
```

The supervisor checks receipts once per minute, restarts an exited or
25-minute-stalled orchestrator, and chooses per-cell concurrency from current
memory pressure (2--4; two cells run at once, so 4--8 case subprocesses).
The task uses an atomic lock to prevent two orchestrators from running at the
same time. A cell with a `.done` marker is never launched again. On resume,
`ok`, `skipped`, and `parser_error` receipts are terminal and are never called
again. Infrastructure failures (`timeout` / `agent_error`) are retried, with a
hard ceiling of three receipts per case.

Inspect:

```bash
tail -f logs/maidxo_missing_n100_20260727/orchestrator.log
tail -f logs/maidxo_missing_n100_20260727/supervisor.log
python3 tasks/maidxo_missing_n100_20260727/summarize.py
python3 tasks/maidxo_missing_n100_20260727/final_audit.py
```

`summarize.py` reports observed wall time and receipt cost, then extrapolates
each cell to its full dataset target. Extrapolated values are planning
estimates, not incurred cost. MAI-DxO does not expose provider token usage, so
inference cost is estimated from captured text. The separate
`maidxo_simulated_clinical_cost_usd` field represents the orchestrator's
simulated physician-visit/test cost and is not API spend.

`final_audit.py` is the strict completion gate. It requires exactly 100 unique
cases per cell, terminal receipts or the documented retry ceiling, no calls
after a terminal receipt, complete parser-error evidence, non-noisy successful
predictions, no cross-case trace contamination, and all five `.done` markers.

## Run incident record

- 2026-07-27 08:08 UTC: the first launch exposed a local environment failure:
  LiteLLM inherited a SOCKS proxy but the MAI-DxO venv lacked `socksio`.
  The affected receipts were all `agent_error`, made no successful model call,
  and recorded zero cost.
- Installed `socksio==1.0.0` into `agents/maidxo/.venv`, added an import
  preflight and a guard that refuses to mark a cell done when it has zero
  successful receipts.
- The invalid completion markers were moved under
  `logs/maidxo_missing_n100_20260727/state/invalid_env_attempt/`.
- 2026-07-27 08:11 UTC: resumed in detached screen session
  `maidxo_n100_20260727`.
- 2026-07-27 08:20 UTC: receipt QA found that the adapter's concurrency
  comment did not match its implementation. Concurrent MAI-DxO subprocesses
  all used `agents/maidxo/` as their working directory, allowing Swarms agents
  with identical names to mix state across cases. Ten nominally successful
  receipts were therefore invalid (estimated receipt cost: $0.070764).
- Stopped the run, changed the adapter to create a unique temporary working
  directory for every case while importing MAI-DxO from its source directory,
  and added a launch preflight that refuses concurrent execution without that
  isolation fix.
- The contaminated receipts were removed from the live output paths and
  retained under
  `logs/maidxo_missing_n100_20260727/invalid_shared_workdir_attempt_20260727T1620/`.
  The clean run restarted from zero in detached screen session
  `maidxo_n100_20260727`.
- 2026-07-27 08:51 UTC: continuous QA found a second audit bug. When all
  extracted candidates were noise, `MaiDxOAdapter` returned `parser_error`
  before estimating token cost or retaining the raw diagnosis/panel trace.
  Those calls therefore appeared to cost $0 and lacked enough evidence to
  audit the parsing failure.
- The adapter now constructs the cost/evidence envelope before prediction
  parsing, so every model-completed terminal receipt retains estimated tokens,
  cost, raw final diagnosis, raw differential, iterations, Judge fields, and
  panel trace. A synthetic noise-output regression test verified this path.
  The 24 incomplete receipts (12 PP-Store GPT-5, 12 RareArena V4-Flash) were
  archived and rerun because their real costs could not be reconstructed.
- 2026-07-27 09:31 UTC: live receipt QA found that the upstream prefix parser
  could still label copied vignette, treatment, vital-sign, and laboratory
  fragments as successful diagnoses. The adapter's noise validator now keeps
  explicit ontology IDs, rejects these additional fragment classes, and
  rejects paragraph-length outputs. `sanitize_receipts.py` applies the same
  deterministic rule to already completed receipts while preserving raw
  output, reasoning trace, latency, and cost. It never repeats a model call:
  valid ORPHA/OMIM/CCRD candidates are retained, and an all-noise result is
  reclassified from `ok` to attempted-denominator `parser_error`.
- 2026-07-27 11:12 UTC: audit of the completed RareArena cell exposed another
  mapping defect: RapidFuzz `WRatio` gave partial-string score 90 to unrelated
  fragments (for example `neutrophils` → `ORPHA:457`, Harlequin ichthyosis).
  Every fuzzy mapping now must pass a conservative whole-string similarity
  check, and unmapped prose is not accepted as a successful benchmark
  prediction. The post-hoc sanitizer applies the same deterministic rule
  without repeating model calls; all seven affected RareArena/V4-Flash rows
  were reclassified from `ok` to `parser_error`, while preserving raw output,
  trace, latency, and estimated cost. The final audit independently checks that
  no unsafe fuzzy mapping survives.
- 2026-07-27 11:12 UTC: system memory pressure reported 43% free and there
  were no retryable, gateway, malformed, or cross-case failures, so the fifth
  cell (`RareBench × GPT-5`) was started as a third parallel cell with four
  workers. `run_parallel_rarebench_gpt5.sh` writes a temporary reservation
  marker so the original two-wave orchestrator cannot duplicate it, resumes
  existing terminal receipts, sanitizes on completion, and writes the normal
  completion marker only after 100/100 cases settle.
