# §10 Conclusion (paper draft v0)

> 数据源:Phase 4a + Phase 3.2 P3 + dual-report
> 状态:文字 ready

---

We introduced a multi-pillar agent-native benchmark for rare disease
diagnosis spanning five capability pillars, four data layers, eight agent
systems, three LLM backbones, and one classical baseline, with all
hypotheses and ablations pre-registered. The benchmark surfaces five
findings with concrete reviewer-defensible numbers. **First**,
classical/offline approaches (LIRICAL Bayesian, VC-RDAgent IC+Poincaré)
remain competitive with — and on HPO-input datasets *exceed* — every
scaffolded LLM agent at R@1 (0.47 vs best-LLM 0.30, a 17 pp gap),
despite consuming no LLM tokens. This is the most consequential single
result, and motivates our **classical baseline column** as a permanent
part of any future rare-disease agent leaderboard. **Second**,
multi-agent scaffolding helps only marginally (≈2–5 pp R@1, within
overlapping CIs) on free-text input and regresses on phenotype-list
input when the scaffold's design (OSCE dialogue, panel orchestration)
is mismatched to the input modality. **Third**, frontier-cheap LLMs
(DeepSeek V4-Flash at $0.11/$0.22 per 1M) are ~10× cheaper than Gemini
Flash but trade off accuracy (−2 to −16 pp R@1, worst on free-text) —
the *cost-efficient*, not quality-equivalent, choice for rare-disease
deployment. **Fourth**, GPT-5 with `reasoning_effort=minimal` is the
costliest backbone with no consistent accuracy edge (best on MedAgents,
−14 pp on AgentClinic dialogue), demonstrating that frontier reasoning
models are brittle when their core mechanism is disabled. **Fifth**, whether
faithfulness ranks decouple from accuracy ranks is **judge-dependent and we
report it as exploratory** (same-trace Spearman ρ = 0.457 under a Gemini judge,
0.640 under a Claude judge; the pre-registered ρ < 0.5 threshold is met under one
judge but not the other) — the durable, direction-independent point is that
accuracy-only evaluation can undersell the risk profile of rare-disease AI, since
a correct diagnosis can still rest on an unfaithful reasoning trace.

We frame these findings as **retrospective decision support evaluation,
not autonomous diagnosis**. No clinical deployment claims are made; the
benchmark, harness, adapter shims, per-cell receipts, and leaderboard
are released to enable independent replication and to ratchet up the
shared evaluation standard in this rapidly-growing area.

**Limitations** are detailed in §9; the principal three are deferred
Pillar 4 (family-aware) reporting, single-language English evaluation,
and the LLM-generated silver-gold reference for Pillar 1 (mitigated by
the in-progress 200-case physician-validated holdout).

**Reproducibility**: all 7,581 Phase 4a predictions ship with per-call
OpenRouter request-ids, exact subprocess invocation commands per
adapter, and a Docker image hash. The OSF pre-registration document
(frozen prior to holdout unblinding) is referenced in §5.4.

---

**Word count**: ~330 words. Targets ~250 words for camera-ready;
trim "We frame ... shared evaluation standard" paragraph for tightness
if needed.
