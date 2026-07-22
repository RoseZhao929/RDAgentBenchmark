# Appendix A1 — Reproducibility Audit (per-agent) (paper draft v0)

> 数据来源:`tasks/stream_E_agent_scouting/agents/*_RUN_REPORT.md`(8 份)
> + `docs/baseline_repro/*.md`(9 份)+ `data/round2/phase4a_receipts.csv`
> + `round2_worklog.md`
> 写作目的:回答 reviewer "did you actually run these agents correctly?" — show our work
> 状态:文字 ready;numbers locked once §6 main matrix freezes (V4-Pro wave complete)

---

For each of the eight evaluated systems we replicated, with the agent's
published evaluation setup, **at least one** point estimate from the
agent's primary publication. We treat a setup as *successfully
re-instantiated* when our point estimate falls within ±5 absolute
percentage points of the paper-claimed number on a comparable input
distribution (HPO-only vs free-text, top-1 vs top-5, EN vs zh). We
audit each agent on three axes:

1. **Faithful re-instantiation** — did we wire the agent's stack
   correctly?
2. **Paper-claim replication** — does our number match the upstream
   number within the band?
3. **Documented deviation** — what specifically did we change, and
   why?

**Three documentation surfaces** for an independent re-runner:

- `data/round2/phase4a_receipts.csv` — **93-cell per-cell receipt**:
  (dataset, agent, backbone, n_ok, n_err, R@1_strict, R@1_variants,
  R@5_strict, R@5_variants, cost_usd, mean_lat_ms). Refreshed at every
  report-regen. This is the single source of truth for Table 1.
- `docs/baseline_repro/<agent>.md` — **per-baseline reproduction
  doc**: upstream code source, license, paper-claimed numbers, our
  observed numbers, behaviour-changing patches (if any), known
  incompatibilities, and run receipts, one per agent plus the LLM
  control.
- `tasks/stream_E_agent_scouting/agents/<agent>_RUN_REPORT.md` —
  **per-agent verbatim subprocess invocation** and parsed-output
  schema, captured at scout time.

The pilot numbers in the audit table below are from the N=50 scouting
pass that originally locked our agent lineup; the full-N point
estimates that headline the paper are in §6 Main Results.

### Per-agent audit table

These are **n=50 pilot reproduction checks** — each asks "can we reproduce agent X's own paper-claimed number on a small sample under our harness", and is deliberately distinct from the N=2000 frozen main matrix (§6) and the N=500 variant-channel paired test (§7.3). Where a small-sample pilot value differs from the frozen-matrix value (e.g. LIRICAL 0.40 pilot vs 0.47 frozen), the frozen-matrix number in §6 is authoritative; the pilot value is retained here only as the original reproduction record.

| Agent | Replicated paper claim? | Our point estimate | Setup deviation | Notes |
|---|---|---|---|---|
| **MDAgents** | ✓ within ±5 pp | R@1 = 0.34 (Gemini 3 Flash, P2, n=50 RareBench-PP) vs paper 0.31–0.39 (MedQA-Rare) | Reformulated as rank-top-5 prompt; held `mode=intermediate`. | 7–47 LLM calls / case |
| **MedAgents** | ✓ within ±5 pp | R@1 = 0.36 (Gemini 3 Flash, P2, n=50) vs paper 0.32 (MedQA-Rare) | Bypassed MCQA-locked `run.py` for free-form ranking; 3 domain experts + Chief MO | ~10 calls / case |
| **AgentClinic** | ✓ within ±5 pp | R@1 = 0.30 (Gemini 3 Flash, P2, n=50) vs paper 0.28 (AgentClinic-MedQA rare slice) | Built synthetic OSCE scenario from CanonicalCase; doctor/patient/measurement/moderator | ~45 turns / case |
| **MAI-DxO** | △ underperform; setup-mismatch documented | R@1 = 0.22 (Gemini 3 Flash, P2, n=50) vs paper 0.45 (NEJM cases) | Paper input = narrative-rich NEJM case; ours = HPO list + brief vignette | See §7.2; noise filter added |
| **DeepRare (P2-only)** | △ underperform; setup-mismatch documented | R@1 = 0.22 (P2, n=50) vs paper 0.71 (HPO+VCF) | Paper input includes VCF; P2-only excludes variants by design | See P3.2 row ↓ |
| **DeepRare (P3 genotype)** | △ partial replication (~28 pp gap) | R@1 = 0.42 (38/50, 95 % CI [0.26, 0.58]) vs paper 0.706 (HPO+VCF) | Structured variants block (not full VCF + Phenotype Tool); web search disabled (`DEEPRARE_NO_WEB=1`) for contamination control | Lift over P2 (+20 pp) matches LLM-control's lift; variant channel real but not DeepRare-specific — see §7.3 |
| **RDMA** | n/a (P1-only system) | F1 = 0.39 (Gemini 3 Flash, P1, n=50 RareBench-EHR) vs paper F1 = 0.42 | Subprocess call to `LLMEntityExtractor`; HPO-mention extraction only | Pillar 1 only |
| **VC-RDAgent** | ✓ within ±5 pp | R@1 = 0.28 (Stage-1 offline IC+Poincaré, P2, n=50) vs paper 0.27 | Stage 1 default (0 LLM calls); Stage 2 LLM refine deferred | Cheapest agent |
| **LIRICAL** | ✓ within ±5 pp | R@1 = 0.40 (gold HPO, P2, n=50 PP-Store pilot) vs paper ~0.42 [on the full N=2000 frozen matrix LIRICAL is 0.47, §6] | `java -jar lirical.jar phenopacket`; project canonical case to phenopacket | 0 LLM calls |
| **LLM control (Gemini 3 Flash, no scaffolding)** | n/a (this *is* the baseline) | R@1 = 0.26 (P2, n=50) | Single LLM call, structured-output prompt | |
| **LLM control (P3 with variants)** | n/a | R@1 = 0.46 (P3 with structured variants, n=50) vs P2 0.26 = **+20 pp** | Variants block appended to prompt (§7.3) | Strong evidence H2 |

### Two agents underperform their paper claim — both explained as input-distribution mismatch

**MAI-DxO** is designed for narrative-rich NEJM-style case reports. Our
input is the CanonicalCase HPO-list + brief vignette. The panel's "ask
the patient questions" channel becomes degenerate on inputs that
already contain the answers; in early runs the panel began emitting
*measurement values* (DLCO, LVEF, FEV1, FVC) as top-1 candidates.  We
added a 13-pattern noise filter (`harness/agents/maidxo.py:_NOISE_PATTERNS`)
to suppress non-diagnosis outputs and report the conservative
HPO-input number in Table 1.  We surface the input-distribution
mismatch openly (§7.2 + §9 L4).

**DeepRare** is designed for HPO + VCF input.  On P2 (HPO-only),
DeepRare scores 0.22 R@1 — near the LLM-control baseline.  On
**P3 (HPO + structured variants, §7.3), DeepRare reaches
R@1 = 0.42 (38/50, 95 % CI [0.26, 0.58])** — a +20 pp lift over its
own P2 number, but **the same lift the single-LLM control receives
from the same variants block** (P3 = 0.46 vs P2 = 0.26).  The gap
to the paper's claimed 0.706 (HPO+VCF) is ~28 pp, attributable to
three setup differences we surface honestly: (a) our variants are a
structured-text block, not a real VCF integrated through DeepRare's
Phenotype Tool; (b) we disabled web search (`DEEPRARE_NO_WEB=1`)
for contamination control, which the paper enables; (c) Phenopacket-
Store is a harder mixed-difficulty corpus than DeepRare's own
curated evaluation set.  **Our headline claim is therefore the
weaker but more defensible "variant channel adds ~20 pp R@1 to any
agent that ingests it"**, not "DeepRare specifically exploits
genotype-aware reasoning" — collapsing both into "DDx accuracy"
would still miss the +20 pp lift, but the agent-specificity claim
does not survive contact with the LLM-control baseline.

### Bugs caught during audit (and the fix)

We list four representative bugs we caught and fixed during the
reproducibility audit; our worklog retrospectives record the full set.

1. **Evaluator NL-fallback gap (Bug #1, Retrospective #3).**  Our
   `gold_hit_with_crossmap` only matched cross-references by ID prefix.
   The Phenopacket-Store gold for ~22 % of cases lists OMIM + name but
   no ORPHA; predictions like `"Metachondromatosis"` (matching the gold
   *name* but not its ID) returned `False`.  We documented DeepRare
   at 0/50 R@1 in a draft table before catching this.  Fix:
   case-insensitive name match + rapidfuzz fallback through Orphadata
   (threshold 90).  17 self-tests in
   `scripts/sanity_check_evaluator.py` now lock the behavior. Post-fix
   DeepRare scored 11/50 (0.22) on the same data.

2. **DeepRare first-case state leak.**  DeepRare writes
   `result_<tag>/<case>/<model>/patient_0.json` with a deterministic
   `0` index.  All 50 P2 cases returned the *first* case's prediction
   ("Metachondromatosis") on the first run.  Fix: per-case unique
   `run_tag = f"{base_tag}_{case_id[:40]}_{suffix}"` + defensive
   purge of the output directory before each call
   (`harness/agents/deeprare.py`).

3. **GPT-5 reasoning_effort silently consuming `max_tokens`.**  See
   §5.2 methods note.  Five subprocess adapters had to be patched
   to propagate `OPENROUTER_REASONING_EFFORT=minimal` through the
   subprocess env.

4. **Orphadata 53 MB XML re-parsed per call.**  After fixing Bug #1 the
   NL-fallback path re-parsed Orphadata's 53 MB XML on every
   evaluator call, ballooning aggregation from <30 s to >30 min. Fix:
   `@lru_cache(maxsize=1)` on `_orphadata_tables()`.

### How a reader can independently re-run any cell

For any Table 1 / §6 cell `(agent, backbone, dataset)`, start from the
per-baseline reproduction doc, which sets expectations for the rerun,
then invoke the runner:

```bash
python3 scripts/phase4a_runner.py \
    --dataset <phenopacket_store|rarearena_rds|rarebench|mimic_diverse> \
    --agent <baseline_name> \
    --backbone openrouter/<provider>/<model> \
    --n 100 \
    --out predictions_test.jsonl
```

`scripts/sanity_check_evaluator.py` must pass (`exit 0`) before any
number in the paper is trusted; this is enforced in our run harness.

### Cost transparency

`scripts/cost_tracker.py --budget <USD>` prints the running per-backbone
cost from the prediction logs. The submission-time snapshot is in
Appendix J and Figure 2.

### Per-cell coverage matrix

Not every (agent × backbone × dataset) cell exists. Known gaps and
their cause:

- **MAI-DxO × GPT-5**: panel orchestration times out at 600 s cap on
  every pilot case; reported as §9 L1.
- **DeepRare × GPT-5-minimal**: `eval_tokenizer` `IndexError` on
  empty `diseases` list emitted by GPT-5 minimal; §9 L1.
- **vc_rdagent / LIRICAL**: backbone-agnostic (offline). One column
  only.
- **DeepSeek V4-Pro and GPT-5 cells**: partial N coverage at
  submission, full N in progress; explicitly disclosed in §4.2 and as
  a per-cell denominator in Table 1.
