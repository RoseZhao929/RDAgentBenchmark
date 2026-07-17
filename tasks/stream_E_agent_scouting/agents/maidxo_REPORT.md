# MAI-DxO (Community Port) Scouting Report

## Repo

- **URL**: https://github.com/The-Swarm-Corporation/Open-MAI-Dx-Orchestrator
- **Stars**: 58 (as of 2026-05-11; matches "53⭐" hint in plan)
- **License**: MIT
- **Last pushed**: 2025-10-13 (commit `2914af1`, July 2025 merge from harshalmore31)
- **Language**: Python (single-file implementation, ~2.5k LOC in `mai_dx/main.py`)
- **Paper citation**: Nori et al., "Sequential Diagnosis with Language Models", arXiv:2506.22405 (Microsoft Research)
- **Community vs Official**: This is the **community port** (by The Swarm Corporation / kyegomez). Microsoft has **not released the official MAI-DxO code or API**. This implementation is built on top of the `swarms` multi-agent framework and explicitly states "An open-source implementation of Microsoft Research's paper". Our paper Method section must declare: *"We use the community port of MAI-DxO (Open-MAI-Dx-Orchestrator); the official Microsoft implementation has not been released as of submission date."*
- **Cloned to**: `/Users/yutianzhao/Desktop/RDAgentBenchmark/agents/maidxo/`

## Install Complexity

**Low (~1/5).** Single repo, single package, 3 runtime dependencies.

- `requirements.txt`: just `loguru`, `swarms`, `pydantic` (with `dotenv` implicitly required)
- `pyproject.toml`: requires Python ^3.10, no torch/transformers/GPU
- Installable via `pip install mai-dx` (PyPI) **or** `pip install -r requirements.txt`
- No Dockerfile (would need to author one)
- All heavy lifting delegated to `swarms.Agent` which uses `litellm` under the hood → no local model downloads

## Backbone Configuration

- **Default**: `"gemini/gemini-2.5-flash"` (in `__init__.py` convenience helpers); the `MaiDxOrchestrator.__init__` default is `"gpt-4o-mini"` (per `mai_dx/main.py:288`)
- **Swap**: single string argument `model_name=...` on constructor. Uses LiteLLM model-name conventions:
  - OpenAI: `"gpt-4o"`, `"gpt-4o-mini"`, `"gpt-5"`
  - Google: `"gemini/gemini-2.5-flash"`, `"gemini/gemini-2.5-pro"`
  - Anthropic: `"claude-3-5-sonnet-20241022"`
  - Open: `"meta-llama/llama-3.1-8b-instruct"`
- **OpenAI-compatible**: yes — via LiteLLM (Swarms internals). Should accept DeepSeek V3.2 and any vLLM/proxy by setting `OPENAI_API_BASE`-style env vars. **Not explicitly tested with DeepSeek in this repo**; we will need to verify model name string in harness smoke test.
- **API keys**: read via `.env` (`OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`). All 8 agents share **the same backbone** (one `model_name` controls everything) — no per-role backbone configuration.

## I/O Schema

Constructor:

```python
MaiDxOrchestrator(
    model_name: str = "gpt-4o-mini",
    max_iterations: int = 10,
    initial_budget: int = 10000,
    mode: str = "no_budget",            # "instant"|"question_only"|"budgeted"|"no_budget"|"ensemble"
    physician_visit_cost: int = 300,
    enable_budget_tracking: bool = False,
    request_delay: float = 8.0,
)
```

Run signature:

```python
result = orch.run(
    initial_case_info: str,         # short vignette shown initially
    full_case_details: str,         # FULL case file, used by Gatekeeper as oracle
    ground_truth_diagnosis: str,    # for Judge scoring
)
```

`DiagnosisResult` (dataclass):

```python
final_diagnosis: str
ground_truth: str
accuracy_score: float          # 0-5 Likert from Judge agent
accuracy_reasoning: str
total_cost: int                # USD, accumulated test_cost_db hits
iterations: int
conversation_history: str
```

**Adaptation note**: The Gatekeeper design assumes the full case file is available and acts as an oracle that drip-feeds findings. For our datasets (Phenopacket-Store, RareArena, MIMIC-IV slice), the "full case" is the entire phenotype/note bundle and ground truth is the diagnosis — schema fits, but the "sequential test ordering" semantics map awkwardly to phenotype-only inputs (no tests to order). The `instant` and `question_only` modes are safer for HPO-only inputs.

## Architecture-Specific

### 8 Agent Roles (`AgentRole` enum, `main.py:84-94`)

1. **Dr. Hypothesis** — maintains probability-ranked differential (function-call tool: `update_differential_diagnosis`)
2. **Dr. Test-Chooser** — selects up to 3 tests/round
3. **Dr. Challenger** — devil's advocate, bias detection
4. **Dr. Stewardship** — cost containment
5. **Dr. Checklist** — quality control
6. **Consensus Coordinator** — function-call tool: `make_consensus_decision` → returns `{action_type ∈ {ask, test, diagnose}, content, reasoning}`
7. **Gatekeeper** — clinical info oracle (has the `full_case_details`)
8. **Judge** — final 5-point Likert scoring against ground truth

All initialized in `_init_agents()` (`main.py:425-538`) as `swarms.Agent` instances sharing `self.model_name`.

### 5 Operational Modes (`create_variant` factory, `main.py:1987-2040`)

```python
variant_configs = {
    "instant":       {mode, max_iterations=1, enable_budget_tracking=False},
    "question_only": {mode, max_iterations=10, enable_budget_tracking=False},
    "budgeted":      {mode, max_iterations=10, enable_budget_tracking=True,
                      initial_budget=kwargs.get("budget", 5000)},  # cost cap here
    "no_budget":     {mode, max_iterations=10, enable_budget_tracking=False},
    "ensemble":      {mode="no_budget", multiple runs with consensus},
}
```

Usage for ablation A2 / budget sweep A11:

```python
orch = MaiDxOrchestrator.create_variant("budgeted", budget=BUDGET_USD,
                                          model_name=..., max_iterations=10)
# BUDGET_USD can be swept: 500, 1000, 2000, 3000, 5000, 10000
```

Mode is enforced in `_run_panel_deliberation` (line 1238) and `_validate_and_correct_action` (line 1482) — e.g. `mode == "question_only"` blocks `action_type == "test"` (line 1486); `mode == "budgeted"` blocks tests when `remaining_budget <= 0` (line 1492).

### Cost Database

Hard-coded dict `self.test_cost_db` (`main.py:331-359`) with 25+ tests (CBC=$50, MRI=$1500, biopsy=$800, …). User-customizable:

```python
orch.test_cost_db.update({"custom_test": 450})
```

Initial physician-visit cost is `$300` (added at run start). All budget math is in USD integers.

## LLM Call Sites

Every agent is a `swarms.Agent` with `max_loops=1`. The main call points are:

- `_safe_agent_run` (line 2046): wraps `agent.run(prompt)` with throttling (`request_delay`, default 8 s) and retry — this is the **single chokepoint** for all LLM traffic.
- `_run_panel_deliberation` (line 1238): orchestrates Hypothesis → Test-Chooser → Challenger → Stewardship → Checklist → Consensus in sequence (5-7 LLM calls per turn depending on mode).
- `_interact_with_gatekeeper` (line 1520): 1 call per turn after Consensus decides.
- `_judge_diagnosis` (line 1547): 1 call at the end.

**Per-case LLM call estimate (no_budget, 10 iterations)**: ~70-90 LLM calls. Per-case token cost can be 200k+ — **this matters for our 60k case scale**; budgeted mode caps iterations naturally.

**Throttling**: `request_delay=8.0` default sleeps 8 s between calls — set to `0` for benchmark throughput, but watch TPM limits.

**Function-calling**: only Hypothesis + Consensus use OpenAI-style tools; rest are free-text. **Compatibility risk**: DeepSeek V3.2 and some non-OpenAI backbones may not support OpenAI function-calling reliably through LiteLLM. We may need to verify or fall back to JSON parsing (there are robust JSON parsers at line 956, 1085, 2106, 2152 already — fallback path exists).

## Risk: **MEDIUM**

Reasons:

1. **Community port, not official Microsoft code** — behavior may diverge from the arXiv paper numbers. Already flagged in our paper Method. The implementation is faithful in structure (8 roles, 5 modes, Gatekeeper-oracle pattern) but prompt wording and the test-cost DB are reinvented from the paper text, not lifted from any official source. Cannot exactly reproduce paper's NEJM CPC numbers.
2. **Single-author repo with limited maintenance** — pushed 2025-10-13, 58 stars, last meaningful commit July 2025 from a pull request. Issues likely under-triaged.
3. **Heavy dependency on `swarms` framework** (≥800 stars, evolving fast) — minor-version breakage risk. Pinning `swarms==X.Y.Z` recommended.
4. **No tests in repo** — `python -m mai_dx.main` runs the demo but there is no `tests/` directory.
5. **Function-calling backbone coupling** — DeepSeek V3.2 / open-weight models may need verification.

Reasons it is **not high risk**:

- Single Python file is auditable in one sitting.
- All 4 modes we need (`instant`/`question_only`/`budgeted`/`no_budget`) are exposed via `create_variant`, no hacking needed for ablation A2.
- Budget is a single integer kwarg — cost-cap sweep (A11) is a 1-liner in a loop.
- I/O schema (case-info, full-case-details, ground-truth) maps cleanly onto our canonical schema.

## Next Steps for Benchmark Integration

### 4-mode switch + cost-cap interface

Our harness wrapper should expose:

```python
def run_maidxo(case, mode, budget=None, backbone="gpt-4o", max_iter=10):
    kwargs = dict(model_name=backbone, max_iterations=max_iter)
    if mode == "budgeted":
        orch = MaiDxOrchestrator.create_variant("budgeted", budget=budget, **kwargs)
    else:
        orch = MaiDxOrchestrator.create_variant(mode, **kwargs)
    return orch.run(case.initial_info, case.full_details, case.ground_truth)
```

For **ablation A2 (mode comparison)**: iterate `mode ∈ {instant, question_only, budgeted@$3000, no_budget}` on the same 200-case subset.

For **ablation A11 (cost-cap sweep)**: with `mode="budgeted"`, sweep `budget ∈ {500, 1000, 2000, 3000, 5000, 10000}`. Each budget value reuses the same Pareto curve (accuracy vs. spend) per case.

### Adapter notes

- **Pillar 2 (HPO-only DDx)**: `initial_case_info` = HPO term list rendered as natural sentence; `full_case_details` = same list (Gatekeeper has nothing extra to drip-feed). Use `instant` or `question_only` modes — `budgeted` is degenerate because no real tests are needed.
- **Pillar 1 (MIMIC EHR)**: `full_case_details` = de-identified note text; `initial_case_info` = first paragraph or HPI summary. All 4 modes meaningful here.
- **PUMCH-ADM (Chinese)**: prompts inside `_get_original_prompt_for_role` are English. We must either prepend a Chinese-input system message or pre-translate; needs smoke test.
- **Backbone smoke test before main run**: verify DeepSeek V3.2 works through LiteLLM with function calling (Consensus + Hypothesis agents). If function-calling fails, the code falls through to its robust JSON parser, but we should confirm before sprint week.
- **Throttling**: set `request_delay=0` for benchmark throughput; rely on provider's TPM.
- **Cost-tracking caveat**: `total_cost` reflects MAI-DxO's *simulated* test cost DB, not LLM token cost. Token cost must be tracked separately via litellm callbacks.
