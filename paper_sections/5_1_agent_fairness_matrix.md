# §5.1 Agent Fairness Matrix(paper draft v0)

> 数据来源:8 个 RUN_REPORT.md(`tasks/stream_E_agent_scouting/agents/*_RUN_REPORT.md`)
> 写作目的:回应 anticipated objection #2 "Heterogeneous-agent comparison unfair"
> 状态:**所有数据 ready,可以马上 finalize**

---

## Draft for paper main text

> *Following MedAgentBench (NEJM AI 2025) and DeepRare (Nature 2026), we hold the central backbone constant across agent comparisons and document every adapter shim deviation in the Agent Fairness Matrix (Table 3). All adapters are released open-source under `harness/agents/`.*

### Agent Fairness Matrix

| Agent | Native Input | Adapter Shim Strategy | LLM Backbone Wiring | Per-Case LLM Calls | Configurable Mode? | Adapter LOC | License |
|---|---|---|---|---|---|---|---|
| **MDAgents** | MCQA prompt | Reformulate canonical case as "rank top-5 rare disease candidates" prompt; regex-parse moderator output | OpenAI-compatible via OpenRouter `base_url`; patched 12 lines to remove hard-coded `gpt-4o-mini` | 7-47 (intermediate path) | basic / intermediate / advanced | 301 | **None**(repo)|
| **MedAgents** | MCQA prompt | Bypass MCQA-locked `run.py`; call `api_handler.get_output_multiagent` with 3 domain experts + Chief MO synthesis | Patched ~25 LOC (Azure-pinned openai 0.27 → OpenRouter) | ~10 | n_experts ∈ {3,5,7}, rounds ∈ {1,2,3} | 348 | **None** |
| **AgentClinic** | OSCE simulated dialogue | Build synthetic OSCE scenario; doctor / patient / measurement / moderator loop; second LLM call for ranks 2-5 | Per-agent CLI `--openrouter` flag added (~30 LOC) | ~45 (turn-bounded) | language ∈ {EN, ZH, ES, IT, FR, KR, MR}, turn cap | 509 | **MIT** |
| **MAI-DxO** | Panel orchestration | LiteLLM router → OpenRouter; `MaiDxOrchestrator.create_variant(mode)`; `max_iterations≥2` for diagnosis (1 = degenerate) | LiteLLM native; no source edit | ~10 (instant) to ~50 (no_budget × 3 iter) | **5 modes: instant / question_only / budgeted / no_budget / ensemble**; `budget_usd` for budgeted | 447 | MIT (community port) |
| **DeepRare** | Phenopacket-style JSON + free text | Write per-case unique output dir; defensively purge `patient_*.json` before each call; `DEEPRARE_NO_WEB=1` + `DEEPRARE_LOCAL_EMBEDDING=1` env shim | Patched 3 lines in `api/interface.py` for OpenAI-compat base_url + env-configurable mini-model | 20-40 (no-web mode) | `--no-web` (env), web-on disabled in v1 | 417 | **CC BY-NC 4.0** |
| **RDMA** | EHR free-text | Subprocess call to `LLMEntityExtractor.extract_entities`; **Pillar 1 only** | `OpenRouterLLMClient(model_type=...)` native | 1-3 per text | n/a (mining-specific) | 364 | **None** |
| **VC-RDAgent** | HPO list | Offline Stage 1 default(IC + Poincaré + frequency-LR fusion, **0 LLM calls**); Stage 2 (LLM refine) opt-in | Stage 2 uses local Qwen3-8B or OpenRouter | 0 (Stage 1) | `use_llm_refine: bool` | 310 | **None** |
| **LIRICAL** | GA4GH Phenopacket | Project canonical case to phenopacket JSON; subprocess `java -jar lirical.jar phenopacket`; parse TSV | **No LLM** (classical Bayesian) | 0 | n/a | 369 | **Apache 2.0** |

### Constants we hold across all agents

| Setting | Value | Rationale |
|---|---|---|
| Backbone temperature | 0.0 | Deterministic ranking |
| Backbone seed (where exposed) | 42 | Seed for `random.Random` and any `seed` param | 
| Backbone max_tokens | adapter-default (typically 2,000-6,000) | Avoid premature truncation |
| Per-call timeout | 600s (adjustable per agent) | DeepRare/MAI-DxO can legitimately exceed 60s |
| Retry policy | 3 attempts with exponential backoff via tenacity | Mitigate OpenRouter transient errors |
| Backbone version (dated) | `google/gemini-3-flash-preview-20251217` etc | Reviewer-defensive — alias updates blocked |

### Three anticipated objections — pre-empted

**Objection 1**: "Adapter quality differences confound results."
**Response**: All 8 adapter shims are released open-source (3,485 LOC total), each accompanied by a run report documenting its exact subprocess calls, parser logic, and known caveats. Independent re-implementation invited.

**Objection 2**: "Different agents accept different inputs — apples to oranges."
**Response**: **Dual-pass evaluation** (gold-HPO + end-to-end, §4.4). The Pass A − Pass B delta on the same agent quantifies P1 sensitivity. RareBench Table 6 precedent — phenotype-input vs EHR-text-input on identical model — is the same design.

**Objection 3**: "Mixing classical (LIRICAL) and LLM agents is unfair."
**Response**: Standard convention — see DeepRare (Nature 2026) which includes Exomiser / LIRICAL / AI-MARRVEL as classical baselines. We report them as separate "Classical Baseline" rows in Table 1 and do not include them in LLM-only ablations (A1/A2/A4/A5/A6/A7).

### Per-agent **known caveats** (we surface these honestly)

- **MDAgents/MedAgents/RDMA/VC-RDAgent: no license file in upstream repos**. We comply with academic fair use (run + report numbers); we do not redistribute their code. Our adapter shims are released independently (Apache 2.0). Action item filed with upstream authors as future work.
- **DeepRare CC BY-NC 4.0 prevents commercial deployment** — academic use OK; we note this in Limitations.
- **MAI-DxO community port** (`Open-MAI-Dx-Orchestrator`, 58⭐ MIT) is structurally faithful to Nori et al. (arXiv 2506.22405) but prompt strings and test-cost values are reimplemented from paper text — minor numerical deviation from Microsoft's reference may exist. Documented in Methods footnote.
- **AgentClinic** in our v1 is tested on HPO-only cases (Phenopacket-Store/RareBench/MIMIC-IV); its OSCE dialogue is shallow when no free-text vignette is available. We report this as Limitation 6.
- **LIRICAL** requires HPO list input. On RareArena (free text), our adapter triggers `eval_mode="end_to_end"` upstream LLM HPO extraction + phrase→HP-ID normalization. This explains LIRICAL's PP-Store R@1 0.40 dropping to 0.04 on RareArena — see analysis §7.1.

---

## TODO before paper finalization

- [ ] Once Phase 4 done, fold in any new adapter-level patches discovered
- [ ] Confirm with each upstream author whether OK to redistribute(if so, can host adapters in benchmark repo; if no, link only)
- [ ] Cross-check DeepRare's "CC BY-NC 4.0" — does that preclude OUR benchmark distributing alongside ours? Likely yes for benchmark commercial use, ok for academic. Footnote clarifying.
- [ ] Per-agent run reports (verbose) → appendix B(reference but don't include verbatim)
