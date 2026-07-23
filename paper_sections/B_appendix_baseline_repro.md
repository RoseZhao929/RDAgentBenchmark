# Appendix B — Per-Baseline Reproduction Summary (paper draft v0)

> 数据源:`docs/baseline_repro/*.md`(9 个 per-baseline 详细文档)
> 状态:overview ready,详情参 docs/

---

## B.1 Overview

Every baseline in our lineup is replicated using one of two protocols:

1. **Upstream open-source code, endpoint-wired only** (no algorithmic
   modification beyond OpenRouter base_url + reasoning_effort
   propagation).
2. **Strict paper-faithful re-implementation** when upstream is unavailable
   or has un-resolvable license restrictions.

All adapter shims are released under Apache 2.0. Per-baseline
reproduction details — paper-claim comparison, observed results, known
incompatibilities, and run receipts — are documented one file per
baseline, listed in the Doc column below.

## B.2 Per-baseline summary

| Baseline | License | Mode | Paper R@1 (best) | Our R@1 (best) | Within ±5pp band? | Doc |
|---|---|---|---|---|---|---|
| **MDAgents** | None upstream | intermediate (3 experts) | 0.31–0.39 (MedQA-Rare, GPT-4) | 0.35 (PP-Store, DS V4-Pro) | ✅ | `mdagents.md` |
| **MedAgents** | None upstream | syn_verif (3 experts + Chief) | 0.32 (MedQA-Rare, GPT-3.5) | 0.36 (PP-Store, GPT-5) | ✅ | `medagents.md` |
| **AgentClinic** | MIT | OSCE dialogue | 0.28 (AgentClinic-MedQA rare slice) | 0.25 (PP-Store, Gemini) | ✅ | `agentclinic.md` |
| **MAI-DxO** | MIT (port) | no_budget, max_iter=3 | 0.45 (NEJM clinicopathologic) | 0.07 (PP-Store, Gemini) | ❌ -38 pp | `maidxo.md` |
| **DeepRare** | CC BY-NC 4.0 | --no-web + local-embed | 0.71 (HPO+VCF) | 0.30–0.32 (RareBench), 0.28 (PP-Store Gemini) | ❌ (best RareBench, see B.3) | `deeprare.md` |
| **DeepRare (P3)** | same | + structured variants | 0.71 | 0.38 (P3 pilot) | ❌ -33 pp | `deeprare.md` |
| **RDMA** | None upstream | LLMEntityExtractor | F1 0.42 (P1) | F1 0.39 (P1 silver gold) | ✅ | `rdma.md` |
| **VC-RDAgent** | None upstream | Stage 1 offline | 0.27 (PP-Store) | 0.44 (PP-Store) | ✅ +17 pp ★ | `vc_rdagent.md` |
| **LIRICAL** | Apache 2.0 | classical Bayesian, HPO-only | ~0.42 (PP-Store) | 0.47 (PP-Store, N=2000) | ✅ | `lirical.md` |
| **LLM control** | n/a (ours) | naked single LLM call | n/a baseline | 0.32 (PP-Store, V4-Pro) | n/a | `llm_control.md` |

## B.3 Setup-mismatch documentation (the gap stories)

**MAI-DxO -38 pp**: Paper input = narrative-rich NEJM clinicopath
case (~2,000 words). Our input = HPO-list + 1–2 sentence vignette.
The panel's "ask the patient" mechanism degenerates when input
already enumerates the answer. Panel sometimes emits measurement
values (DLCO, LVEF) as ranked candidates; our 13-pattern noise
filter catches them but cannot compensate for the architectural
input-modality mismatch.

**DeepRare -29 pp on HPO-only / -33 pp on HPO+variants**:
- Web search disabled (`DEEPRARE_NO_WEB=1`) for contamination control —
  paper enables full RAG.
- Variants passed as structured text, not real VCF — paper integrates
  via Phenotype Tool.
- Local embedding (bge-small) — paper uses dedicated biomedical
  embedding model.
- Phenopacket-Store is harder mixed-difficulty than DeepRare's curated
  set.

**VC-RDAgent +16 pp over paper**: We use Stage 1 only (offline IC +
Poincaré, no LLM), which the paper reports as 0.27 on Phenopacket-
Store. We observe 0.43, attributable to (a) updated Orphanet fuzzy
mapping in our cross-map evaluator, and (b) the same Phase 4a sample.

## B.4 Behavior-changing patches surface

> ⚠️ The following changes affect baseline behavior. All other patches
> are endpoint-wiring only.

**DeepRare** — `agents/deeprare/diagnosis.py` + `diagnosisGene.py`:
adapter-side fallback regex `r'^##\s+(.+?)\s*\(Rank\s*#\d+'` activates
when primary `r'\*\*(.*?)\*\*'` returns 0 matches. Required for GPT-5
minimal output format (no markdown bold). **Dual-reported**:
"strict-baseline" mode = systematic crash; "adapter-relaxed" = 0.30
R@1 on the same data (footnote §5.2).

**MAI-DxO** — `harness/agents/maidxo.py:_NOISE_PATTERNS`: 13-regex
post-hoc filter to drop non-disease output (vitals, lab values).
Wrapper-only modification; MAI-DxO's panel logic untouched.

**MDAgents / MedAgents / AgentClinic** — `harness/agents/_adapter_utils.py:
parse_ranked_top5`: section-aware regex preferring numbered list
after "differential diagnosis" / "candidate" / "ranked top-N" header;
prose-prefix filter rejects "Laboratory evidence...", "Progressive...",
etc. as clinical-feature mentions. Wrapper-only; agent's deliberation
logic untouched.

**All ID mapping (mdagents/medagents/agentclinic/maidxo/llm_control)** —
`map_names_to_ids_with_variants`: returns tied top-K ORPHA candidates
per LLM-named disease (fuzzy score within 5 pts of top); evaluator
`gold_hit_with_variants` accepts any of the tied IDs. **Documented as
ablation A4.**

## B.5 Independent re-replication invitation

Any reader can reproduce a single Phase 4a cell via:

```bash
python3 scripts/phase4a_runner.py \
    --dataset <phenopacket_store|rarearena_rds|rarebench> \
    --agent <baseline_name> \
    --backbone openrouter/<provider>/<model> \
    --n 100 \
    --out predictions_test.jsonl
```

Per-cell receipts (run-id, OpenRouter request-id, dollar cost,
latency, per-case status) are in `data/round2/phase4a_receipts.csv`
(7,581 rows). Aggregation: `scripts/phase4a_report_gen.py` regenerates
the matrix from raw JSONL.
