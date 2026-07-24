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
multi-agent debate (MDAgents, MedAgents, MAI-DxO)
\citep{mdagents2024,medagents2024,maidxo2025}, OSCE dialogue simulation
(AgentClinic) \citep{agentclinic2024}, domain-specialised retrieval and
reasoning (DeepRare) \citep{deeprare2026}, HPO-conditional fusion
(VC-RDAgent) \citep{vcrdagent}, phrase-mining (RDMA) \citep{rdma2025},
and classical Bayesian likelihood (LIRICAL) \citep{lirical2020}.
Each system reports R@1 in the 0.3–0.7 range on its own evaluation set.

## 2.2 The gap — no shared benchmark

But **no shared benchmark exists**. Each paper evaluates on an ad-hoc
subset: MDAgents on MedQA-Rare, MAI-DxO on NEJM clinicopathologic
cases, DeepRare on a 9-source proprietary mix, RareBench on a 1.1k HPO
subset, etc. Cross-system comparison is impossible. A recent
systematic review and meta-analysis identified 15 studies contributing 19
system--dataset entries; every entry was assessed as high risk of bias, most
often because of potential leakage and limited reproducibility, and benchmark
disease composition was associated with performance
\citep{sysreview2026}. Without a shared evaluation infrastructure, "agent X
beats agent Y" is unverifiable.

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
(1,122) → RareArena RDS (72,661) → PMC OA post-cutoff holdout (200).
A separate, exploratory MIMIC-IV protocol defines early structured-event
prediction plus ICD leakage auditing on 956 code-supervised admissions;
replacement scoring is pending and is not pooled with the diagnostic layers.
The layering spans difficulty, contamination risk, input
modality (HPO vs free-text), and prevalence
distribution. The PMC layer is publication-date held out (2024+), but an exact
PMCID overlap audit prevents us from claiming that it eliminates contamination;
we use it as a bounded temporal sensitivity analysis.

**Repository-defined hypotheses + ablations**: H1–H11 + A1–A12 and the
Holm correction are documented in the released analysis plan. The OSF file is
still an unregistered draft with placeholder metadata, so the current study
does not claim formal pre-registration.

## 2.5 Key findings preview

We implement eight published systems plus one no-scaffold control. Compatible
LLM agents are evaluated across Gemini 3 Flash, DeepSeek V4-Flash,
DeepSeek V4-Pro reasoning-off, and GPT-5 minimal; Table 1 reports the actual
per-cell attempted N and Appendix J reports $270.74 aggregate diagnostic cost.

Five findings:

1. **Classical/offline baselines decisively lead on Phenopacket-Store**:
   LIRICAL (Bayesian) R@1 = 0.47 [0.45–0.49];
   VC-RDAgent (offline IC+Poincaré) 0.44 [0.40–0.48]; best LLM cell
   0.30 (MedAgents × Gemini, N=2000) — a 17 pp gap. RareBench is near
   parity, with best LLM 0.30 and best classical/offline 0.28.
2. **Multi-agent scaffolding gives only a small, dataset-dependent
   gain (≈0–2 pp R@1)** over single-LLM controls, not the uniform
   boost prior work implies (medagents 0.30 vs llm_control 0.29,
   Phenopacket-Store / Gemini, N=2000; within overlapping CIs — and
   several scaffolds fall *below* the control, see §7.2).
3. **DeepSeek V4-Flash is ~10× cheaper than Gemini Flash but usually
   trades off accuracy** (R@1 −3 to −8 pp on Phenopacket-Store and
   −4 to −14 pp on RareArena; RareBench is mixed) — cost-efficient,
   not quality-equivalent.
4. **GPT-5 with `reasoning_effort=minimal` is the most expensive
   backbone (~24× V4-Flash, receipt-weighted) with no consistent
   accuracy edge** — near-competitive on MedAgents yet falling by
   ~9 pp on AgentClinic dialogue —
   exposing frontier reasoning models' brittleness under
   reasoning-disabled regimes.
5. **Variant channel adds ~20 pp R@1 to *any* agent that ingests
   structured variants** (Phase 3.2 P3 pilot: llm_control 0.26 → 0.46,
   deeprare 0.22 → 0.38) — *not* DeepRare-specific.

## 2.6 Contributions

- **RareAgentBench benchmark**: 5 pillars × 3 diagnostic layers plus one
  structured-EHR probe × 9 implementations × 4 hosted backbones where
  compatible, with code and receipts released.
- **Per-agent adapter shims** (3,485 LOC): unified `CanonicalCase` input
  contract + subprocess isolation, with per-baseline reproducibility
  documentation.
- **Reproducibility receipts**: per-cell run-id + OpenRouter request-id
  + dollar cost; 90,046 successful diagnostic attempts aggregated in the
  frozen cost receipt.
- **Repository-defined statistical protocol**: Holm–Bonferroni for H1–H11,
  bootstrap 95% CIs, and LLM-judge sensitivity analysis with matched-trace
  Gemini/Claude agreement.
- **Static-site leaderboard** for community ratchet.

---

[1-8]: Cite each agent paper here when finalising.
