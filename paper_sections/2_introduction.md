# §2 Introduction (paper draft v0)

> 数据源:Phase 4a 21/23 cells done + Phase 3.2 P3 + Phase 1 P5
> 状态:文字 ready,等 final Phase 4a numbers 后 pin

---

**Target length**: ~1.25 pages (~750 words)

---

## 2.1 The phenomenon — agent proliferation in rare disease

Rare disease diagnosis is undergoing a **diagnostic-agent renaissance**.
In 2024–2026 alone, eight distinct agent systems were proposed that
attack the problem with markedly different architectures: medical
multi-agent debate (MDAgents [1], MedAgents [2], MAI-DxO [3]), OSCE
dialogue simulation (AgentClinic [4]), domain-specialised retrieval +
reasoning (DeepRare [5]), HPO-conditional fusion (VC-RDAgent [6]),
phrase-mining (RDMA [7]), and classical Bayesian likelihood (LIRICAL [8]).
Each system reports R@1 in the 0.3–0.7 range on its own evaluation set.

## 2.2 The gap — no shared benchmark

But **no shared benchmark exists**. Each paper evaluates on an ad-hoc
subset: MDAgents on MedQA-Rare, MAI-DxO on NEJM clinicopathologic
cases, DeepRare on a 9-source proprietary mix, RareBench on a 1.1k HPO
subset, etc. Cross-system comparison is impossible. A recent
systematic review (Garrett et al., *npj Digital Medicine* 2026) audited
19 LLM rare-disease studies and flagged **(i) absence of
pre-registration** in all but one, **(ii) high contamination risk**
across all 19, and **(iii) R² = 0.55** between disease prevalence and
reported R@1 — a strong signal that selection bias dominates published
numbers. Without a shared evaluation infrastructure, "agent X beats
agent Y" is unverifiable.

## 2.3 Why agent-native, not LLM++

One could argue an LLM-only benchmark suffices. We disagree on three
grounds. **First**, the diagnostic agent designs we audit differ on
*non-LLM* axes — RAG pipelines (DeepRare), panel orchestration
(MAI-DxO), OSCE dialogue (AgentClinic), classical fusion
(VC-RDAgent) — that LLM-only benchmarks cannot disentangle from
backbone choice. **Second**, the *evaluation surface* matters: pure
accuracy ignores faithfulness, cost, and pass-k reliability, all of
which matter in clinical deployment. **Third**, **classical / offline
baselines** (LIRICAL Bayesian, VC-RDAgent Stage 1) are competitive
with LLM agents on HPO-input datasets — a result that *no* prior
benchmark would have surfaced because none of them run classical
baselines side-by-side with the LLM lineup.

## 2.4 Our approach

We introduce **RareAgentBench**, a benchmark with three structural commitments:

**Five capability pillars**: phenotype extraction (P1), phenotype-only
DDx (P2), genotype-aware DDx (P3), family-aware DDx (P4, deferred to
v2), and clinical-communication faithfulness (P5). Each pillar surfaces
different agent capabilities; collapsing all into a single accuracy
number can hide faithfulness failures — a correct diagnosis can rest on an
unfaithful reasoning trace — though we report the strength of that
faithfulness/accuracy decoupling (§7.4) as judge-dependent and exploratory
rather than a firm quantitative claim.

**Layered dataset**: Phenopacket-Store (10,051 cases) → RareBench HF
(1,122) → RareArena RDS (72,661) → MIMIC-IV rare-disease slice (956)
→ PMC OA post-cutoff holdout (200). The layering spans difficulty,
contamination risk, input modality (HPO vs free-text), and prevalence
distribution. Holdout case excerpts are post-LLM-training-cutoff (after
2026-02), eliminating the contamination concern that plagues prior
work.

**Pre-registered hypotheses + ablations**: H1–H11 + A1–A12 frozen at
OSF prior to holdout unblinding. To our knowledge this is **the first
pre-registered rare-disease diagnostic-AI evaluation**.

## 2.5 Key findings preview

We evaluate 8 agent systems against 3 LLM controls (Gemini 3 Flash,
DeepSeek V4-Flash, GPT-5 *reasoning_effort=minimal*) and 1 classical
baseline across the four pre-holdout layers (Phase 4a, N=100/dataset,
$54 cumulative cost — code, data, and per-cell receipts open-sourced).

Five findings:

1. **Classical/offline baselines exceed every scaffolded LLM agent
   on HPO-input datasets**: LIRICAL (Bayesian) R@1 = 0.47 [0.45–0.49];
   VC-RDAgent (offline IC+Poincaré) 0.44 [0.40–0.48]; best LLM cell
   0.30 (MedAgents × Gemini, N=2000) on Phenopacket-Store — a 17 pp gap.
2. **Multi-agent scaffolding gives only a small, dataset-dependent
   gain (≈0–2 pp R@1)** over single-LLM controls, not the uniform
   boost prior work implies (medagents 0.30 vs llm_control 0.29,
   Phenopacket-Store / Gemini, N=2000; within overlapping CIs — and
   several scaffolds fall *below* the control, see §7.2).
3. **DeepSeek V4-Flash is ~10× cheaper than Gemini Flash but trades
   off accuracy** ($0.11/$0.22 vs higher Gemini pricing; R@1 −2 to −9 pp
   on structured input, −11 to −16 pp on free-text) — cost-efficient,
   not quality-equivalent.
4. **GPT-5 with `reasoning_effort=minimal` is the most expensive
   backbone (~34× V4-Flash) with no consistent accuracy edge** — best
   on MedAgents yet collapsing −14 pp on AgentClinic dialogue —
   exposing frontier reasoning models' brittleness under
   reasoning-disabled regimes.
5. **Variant channel adds ~20 pp R@1 to *any* agent that ingests
   structured variants** (Phase 3.2 P3 pilot: llm_control 0.26 → 0.46,
   deeprare 0.22 → 0.38) — *not* DeepRare-specific.

## 2.6 Contributions

- **RareAgentBench benchmark**: 5 pillars × 4 layers × 11 systems × 3 backbones,
  pre-registered + open-sourced.
- **Per-agent adapter shims** (3,485 LOC): unified `CanonicalCase` input
  contract + subprocess isolation, with per-baseline reproducibility
  documentation.
- **Reproducibility receipts**: per-cell run-id + OpenRouter request-id
  + dollar cost; full Phase 4a matrix (7,581 predictions) released.
- **Pre-registered statistical protocol**: Holm–Bonferroni for H1–H11,
  bootstrap 95% CIs, LLM-judge self-preference detection (Gemini-judge
  → Claude-judge agreement floor).
- **Static-site leaderboard** for community ratchet.

---

[1-8]: Cite each agent paper here when finalising.
