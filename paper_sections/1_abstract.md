# §1 Abstract (paper draft v0)

> 数据源:frozen main manifest(N=2000 harmonized;audit_frozen/frozen_main_manifest.csv,
>   commit 43efa1e5)。R@1 = variant-aware,attempted 分母。
> 状态:2026-07-22 冻结审计对齐——headline 数字改用 N=2000 最终值(LIRICAL 0.47 /
>   best LLM 0.30 / 17 pp gap),替换早期 N=500 pilot 值(0.46 / 0.33 / 13 pp)。

---

**Target word count**: 220 words

---

## Draft

Rare disease diagnostic AI agents have proliferated (8+ systems in
2024-2026), yet no shared benchmark exists; each agent paper evaluates
on an ad-hoc subset, making cross-system claims unverifiable. We
introduce **RareAgentBench**, an agent-native benchmark spanning **five capability
pillars** (phenotype extraction, phenotype-only DDx, genotype-aware DDx,
family-aware DDx, clinical-communication faithfulness) on a layered
dataset (Phenopacket-Store *n*=10,051; RareBench HF 1,122; RareArena RDS
72,661; post-cutoff PMC OA holdout *n*=200), plus a separately specified,
exploratory MIMIC-IV structured-EHR protocol (956 code-supervised admissions;
no clinical notes; replacement scoring pending). We implement **eight
published systems** (five scaffolded diagnostic agents, RDMA extraction, and
two classical/offline baselines) plus a no-scaffold LLM control, using four
hosted backbones where compatible. H1–H11 and A1–A12 form a
repository-defined analysis family; the OSF document remains an unregistered
draft, so we do not claim formal pre-registration.

**Key findings**: (1) classical/offline baselines (LIRICAL 0.47,
VC-RDAgent 0.44 R@1) **decisively lead on Phenopacket-Store**
(best LLM cell 0.30, a 17 pp gap), while RareBench is near parity
(best LLM 0.30 vs classical/offline 0.28); (2)
multi-agent scaffolding gives only a small, dataset-dependent gain
(≈0–2 pp R@1 over single-LLM controls), not the uniform boost prior
work implies; (3) DeepSeek V4-Flash is ~10× cheaper than Gemini Flash
but **usually trades off accuracy** (3–8 pp on Phenopacket-Store and
4–14 pp on RareArena, with mixed RareBench results) — cost-efficient,
not quality-equivalent; (4) GPT-5 with `reasoning_effort=minimal`
carries the highest receipt-weighted cost (~24× V4-Flash) without a
consistent accuracy edge — near-competitive on some scaffolds yet
falling by ~9 pp on AgentClinic,
illustrating **frontier-reasoning models' brittleness under
reasoning-disabled regimes**; (5) a structured genotype channel adds
about 20 pp R@1 in the paired HPO-plus-variant experiment, while the
faithfulness--accuracy threshold remains judge-sensitive and exploratory.
We release
the harness, canonical case schema, per-agent adapter shims, full
per-cell receipts, and a static-site leaderboard.

## CTA

`github.com/<USER>/RDAgentBench` · leaderboard `<USER>.github.io/rdab/`

---

## Scoring checklist

- [x] Hook (2 sentences): agent proliferation vs benchmark gap
- [x] What we built: five pillars, three diagnostic layers plus separate resources,
  eight published systems plus one no-scaffold control, and a repository-defined analysis family
- [x] 5 numbered findings with concrete percentages
- [x] Release statement
- [x] ~220 words target
- [x] No model-version aliases that may rot (uses "DeepSeek V4-Flash" not version-string)
