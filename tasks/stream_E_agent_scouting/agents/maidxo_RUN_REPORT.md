# MAI-DxO (Community Port) Run Report

**Date:** 2026-05-11
**Repo path:** `/Users/yutianzhao/Desktop/RDAgentBenchmark/agents/maidxo/`
**Status:** PASS (full 8-agent panel runs end-to-end via OpenRouter; all 5 variants instantiate)

---

## Install

- **Host:** macOS 25.2.0, Apple Silicon
- **Python:** 3.13.7 (system `python3`), venv at `agents/maidxo/.venv/`
  - Repo `pyproject.toml` requires `^3.10`; 3.13 worked once we patched one `swarms` API drift (see Patches).
- **Commands:**
  ```bash
  cd agents/maidxo/
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -U pip
  pip install -r requirements.txt
  ```
- **`requirements.txt`** (unchanged): `loguru`, `swarms`, `pydantic`.
- **Install duration:** ~90 s. Pulled in `swarms 12.0.0`, `litellm 1.76.1`, `openai 2.36.0`, `pydantic 2.13.4`, etc.

## Patches

| File | Change | Reason |
|---|---|---|
| `mai_dx/main.py:323-326` | Wrapped `Conversation(...)` call in try/except, retrying without `save_enabled=False` if `TypeError` is raised. | `swarms>=12` removed the `save_enabled` kwarg from `Conversation.__init__`. Without this patch, the orchestrator crashes during `__init__`. Forward-compat: still works against older swarms versions. |

No other edits were needed. No dependency pin overrides.

## Backbone config

- Project canary model wired via **LiteLLM model-name routing**:
  ```python
  model_name = "openrouter/google/gemini-3-flash-preview"
  ```
- LiteLLM auto-reads `OPENROUTER_API_KEY` from environment when the model string starts with `openrouter/`. No `OPENAI_API_BASE` override needed.
- `.env` loaded by reading `/Users/yutianzhao/Desktop/RDAgentBenchmark/.env` line-by-line into `os.environ` (smoke-test scripts only).
- Throttling: set `request_delay=0.0` for smoke tests (default is 8.0 s between LLM calls).

## Smoke test

Two smoke tests were authored and executed inside the venv:

### 1. `smoke_test.py` — `instant` variant (single LLM call path)

- **Entry point:** `MaiDxOrchestrator.create_variant("instant", model_name=..., max_iterations=1, request_delay=0.0).run(initial, full, gt)`
- **Input:** 7-year-old DMD vignette + biopsy revealing exon 45-50 deletion in *DMD*, GT = "Duchenne muscular dystrophy"
- **Wall time:** ~9 s
- **Result:** `final_diagnosis='No diagnosis formulated'`, `accuracy_score=1.0`, `iterations=1`, `total_cost=$300`
- **Interpretation:** `instant` mode short-circuits `_run_panel_deliberation` (main.py:1283-1292) and returns `case_state.get_leading_diagnosis()` *immediately* — but on iteration 1 the leading diagnosis is empty because Dr. Hypothesis never runs. Only the **Judge** LLM call lands. This still validates: orchestrator boot, env loading, swarms-12 patch, LiteLLM → OpenRouter wiring, Judge agent invocation, response parsing. `instant` mode in this implementation is effectively a no-op on first iteration; either bug or by-design ("instant" = "skip deliberation"). Documenting it as a quirk to mention to harness wrapper.

### 2. `smoke_test_full.py` — `no_budget` variant with `max_iterations=1` (full 8-agent panel)

- **Entry point:** `MaiDxOrchestrator.create_variant("no_budget", model_name=..., max_iterations=1, request_delay=0.0).run(initial, full, gt)`
- **Input:** same DMD vignette
- **Wall time:** **74 s** for a single deliberation round + Judge
- **LLM calls made (observed in log):** Dr. Hypothesis, Dr. Test-Chooser, Dr. Challenger, Dr. Stewardship, Dr. Checklist, Consensus Coordinator, Gatekeeper (responded with MLPA result showing exon 45-50 deletion in *DMD*), and Judge — **all 8 personas invoked** via OpenRouter+Gemini 3 Flash Preview.
- **Result:** Panel ordered the MLPA test, Gatekeeper returned the deletion result, but `max_iterations=1` cut off before the panel could form the final diagnosis. Final: `"Diagnosis not reached within maximum iterations."`, score=1, cost=$450 (one $300 physician visit + one $150 MLPA test).
- **Status:** **PASS** — the multi-agent pipeline works end-to-end. To get a real diagnosis you need `max_iterations >= 2`; this is consistent with the paper's design (round 1 = test ordering, round 2+ = diagnose).

### Variant instantiation matrix

A separate inline check confirmed all 5 `create_variant(...)` modes instantiate cleanly with the OpenRouter backbone:

| Variant | Instantiates? | `mode` | `max_iter` | `enable_budget_tracking` |
|---|---|---|---|---|
| `instant` | YES | `instant` | 1 | False |
| `question_only` | YES | `question_only` | 1 | False |
| `budgeted` (`budget=1000`) | YES | `budgeted` | 1 | True |
| `no_budget` | YES | `no_budget` | 1 | False |
| `ensemble` | YES | `no_budget` | 1 | False (multi-run wrapper, single config) |

Only `instant` and `no_budget` (≥1 iter) were actually run end-to-end with LLM calls under this 90 min budget; the other three share the same `run()` codepath and differ only in mode-gating booleans inside `_run_panel_deliberation` and `_validate_and_correct_action`. **Conclusion: all 5 modes are wired and callable; full E2E for `question_only` / `budgeted` / `ensemble` is left for the benchmark integration sprint.**

## Status: PASS

## Blockers

None for further integration. The `swarms` Conversation patch is a one-line forward-compat shim that has been applied in-tree.

Soft observations to track:

- `instant` mode returns "No diagnosis formulated" on iteration 1 because it skips the Hypothesis agent. If we want a real `instant` baseline, the harness should either (a) raise iterations to 2+ via a wrapper, (b) patch `_run_panel_deliberation` so `instant` runs the Hypothesis agent first, then short-circuits to consensus, or (c) treat this mode as a degenerate baseline and accept that it scores zero. Option (b) is the right paper-faithful behavior; one-liner in `main.py:1283`.
- Default `request_delay=8.0` will balloon wall time on 60k cases; set to 0 in benchmark wrapper and rely on OpenRouter TPM ceiling.
- `total_cost` is *simulated test cost*, not LLM token cost. Token cost must be tracked separately via the LiteLLM callback hook.

## Notes for benchmark integration

### MAI-DxO 5-mode interface — are all callable?

**Yes.** `MaiDxOrchestrator.create_variant(name, **kwargs)` accepts all five strings (`instant`, `question_only`, `budgeted`, `no_budget`, `ensemble`) and constructs a working orchestrator instance. `budgeted` takes a `budget=...` kwarg that is correctly mapped to `initial_budget` (factory does the pop, see `main.py:2037-2040`). `ensemble` builds a single orchestrator in `no_budget` mode under the hood; the actual multi-run aggregation lives in `MaiDxOrchestrator.run_ensemble()` (a separate method at `main.py:1832`, not exercised in this smoke test but a one-line wrapper away). Recommended harness signature is the one in `maidxo_REPORT.md` § "Adapter notes" — no changes needed.

### Files produced

- `agents/maidxo/.venv/` — Python 3.13 venv, ~700 MB.
- `agents/maidxo/smoke_test.py` — `instant` smoke test.
- `agents/maidxo/smoke_test_full.py` — `no_budget` full-panel smoke test.
- `agents/maidxo/mai_dx/main.py` — patched (Conversation kwarg shim) at line 323.

### Next steps for the integration sprint

1. Move the swarms patch into a small `monkey_patch.py` so it can be applied at import time without editing vendor code (cleaner for reproducibility).
2. Add a LiteLLM cost callback to track token cost alongside MAI-DxO's simulated `total_cost`.
3. Wrap `create_variant` in our harness `run_maidxo(case, mode, budget=None, backbone="openrouter/google/gemini-3-flash-preview", max_iter=10)` — the signature in `maidxo_REPORT.md` is correct.
4. Run a 2-iteration `no_budget` end-to-end to confirm the diagnosis path produces non-empty output (deferred from this round due to time budget; based on logs the next iteration would have called Hypothesis again with the new MLPA evidence and converged on DMD).

## Adapter Shim

**File:** `harness/agents/maidxo.py` (class `MaiDxOAdapter`, `NAME = "maidxo"`).

### Design choices

- **Subprocess-isolated** invocation. The adapter `subprocess.run`s
  `agents/maidxo/.venv/bin/python -c <inline runner>` and pipes a JSON config
  on stdin / parses a `__MAIDXO_RESULT__`-delimited JSON payload on stdout.
  Rationale: `swarms >= 12` + `litellm` carry a heavy dep graph (and the swarms
  Conversation patch lives in-tree at `mai_dx/main.py:323`); keeping it in the
  agent venv avoids polluting the harness venv and respects the existing
  smoke-test wiring.
- **Mode dispatch** via `agent_extra["mode"]` ∈ `{instant, question_only,
  budgeted, no_budget, ensemble}` → forwarded directly to
  `MaiDxOrchestrator.create_variant(mode, ...)`. `budgeted` accepts
  `agent_extra["budget_usd"]` (mapped to `initial_budget`).
- **Defaults**: `mode="no_budget"`, `max_iterations=3` (≥2 needed for a real
  diagnosis per the smoke test), `request_delay=0.0` (harness owns throttling).
- **Pillar support**: P2 only. P3/P4/P5 return `status="skipped"`.
- **Input projection**: when `case.free_text_vignette` is absent, we
  deterministically render a vignette from demographics + HPO labels (present
  / negated separated). `initial_case_info == full_case_details` since
  Pillar 2 has no Gatekeeper-only info to hide.
- **Output projection**: prefer `case_state.differential_diagnosis` (Dr.
  Hypothesis ranking) when populated; otherwise fall back to the single
  Judge-scored `final_diagnosis`. `judge_score` / `judge_reasoning` /
  `simulated_cost_usd` flow into `log.extra`. Token cost remains $0
  (LiteLLM usage callback deferred — see Soft observations above).
- **Variant id stripping**: backbone id stays as `openrouter/google/...` so
  LiteLLM auto-routes via `OPENROUTER_API_KEY`. Bare ids get an
  `openrouter/` prefix.

### Verification

Ran `python -m harness.agents.maidxo` with the first phenopacket
(`PMID_15266616_100`, Jacobsen syndrome, 11q_terminal_deletion split) in
`instant` mode (fast — confirms wiring without the 80 s full-panel cost):

```
status: ok
ranked_predictions[:5]: ['No diagnosis formulated']
latency_ms: 12418
extra: {'maidxo_mode': 'instant', 'max_iterations': 1, 'iterations_used': 1,
        'judge_score': 1.0, 'simulated_cost_usd': 300, ...}
```

The `'No diagnosis formulated'` is the documented `instant` quirk (Dr.
Hypothesis is skipped; only Judge runs) — see § Soft observations. The
wiring (env, LiteLLM-via-OpenRouter, Judge parsing) is otherwise green.
For benchmark scoring, configure the adapter with
`agent_extra={"mode": "no_budget", "max_iterations": 3}`; full-panel wall
time is ~80–150 s/case (extrapolated from the 74 s @ max_iter=1 smoke).

---

## Bug Fix 2026-05-15 (Phase-0 retro)

**Bug D1** (round2_plan.md § 复盘 ①): Mini Phase 0 ran maidxo with
`agent_extra={"mode":"no_budget","max_iter":1}` — note the **wrong key**
`max_iter` (typo, was silently ignored, default `max_iterations=3` actually
ran). Per-case wall time was ~240 s with R@1=0.00 on the 50-case sample.
Root cause:
1. Pilot script passed the wrong key (`max_iter`); fixed in
   `scripts/mini_round2_pilot.py`.
2. When the panel converges to a single named diagnosis or "Unable to
   establish...", `differential_diagnosis` is empty and
   `ranked_predictions` becomes a 1-element list with a long prose name —
   ORPHA/OMIM cross-map can't hit it → R@1=0.00.

**Fixes applied** in `harness/agents/maidxo.py`:
- `_clean_for_fuzzy(name)`: strip parenthetical clarifiers + "with/and/or"
  qualifiers before mapping.
- New fuzzy-ORPHA fallback: when `len(ranked) <= 1` and the head isn't an
  unhelpful sentinel ("Unable to establish ..."), call
  `harness.pmc_oa.orphanet.map_diagnosis()` and prepend the best ORPHA + top
  fuzzy candidate IDs to `ranked_predictions`. Original disease name kept
  at rank-1 so the auditor can trace.
- `log.extra["maidxo_fuzzy_fallback"]` records the input head, best
  matched ORPHA, and `match_type` for downstream audit.

**Bug D2**: `cost.cost_usd=0` despite valid token counts.
- Added cost-from-tokens estimation: tokenize the entire
  `conversation_history` (prompt floor) + `final_diagnosis` +
  `accuracy_reasoning` (completion floor), then
  `fill_cost_from_tokens(log.cost, self.backbone_id)` converts to USD via
  the price table.
- This is a floor (the conversation history contains a subset of the panel
  exchanges that LiteLLM saw); a proper LiteLLM usage callback would do
  better but is deferred.

Verified by re-run on the same 50-case sample — see `data/round2/phase0/REPORT_v2.md`.
