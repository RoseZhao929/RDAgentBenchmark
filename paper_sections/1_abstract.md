# §1 Abstract (paper draft v0)

> 数据源:`phase4a_summary.json`(2026-05-29 finalized)。Gemini/V4-Flash N=500,
>   V4-Pro/GPT-5 N=100 参考列,RareBench N=378。
> 状态:数字 pinned 到 N=500 + 修复重跑后的最终值;findings (1)-(4) 已按全 N 修订。

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
72,661; MIMIC-IV rare-disease slice *n*=956; post-cutoff PMC OA holdout
*n*=200). We evaluate **8 agent systems** (DeepRare, MDAgents, MedAgents,
AgentClinic, MAI-DxO, RDMA, VC-RDAgent, LIRICAL) against **3 LLM
no-scaffolding controls and one classical baseline**, with all
hypotheses (H1–H11) and ablations (A1–A12) pre-registered.

**Key findings**: (1) classical/offline baselines (LIRICAL 0.46,
VC-RDAgent 0.44 R@1) **exceed every scaffolded LLM agent on HPO-input
datasets** (best LLM cell 0.33 on Phenopacket-Store, a 13 pp gap); (2)
multi-agent scaffolding gives only a small, dataset-dependent gain
(≈2–5 pp R@1 over single-LLM controls), not the uniform boost prior
work implies; (3) DeepSeek V4-Flash is ~10× cheaper than Gemini Flash
but **trades off accuracy** (−2 to −9 pp on structured input, −11 to
−16 pp on free-text) — cost-efficient, not quality-equivalent; (4)
GPT-5 with `reasoning_effort=minimal` carries the highest cost (~34×
V4-Flash) without a consistent accuracy edge — competitive on some
scaffolds yet collapsing on dialogue (−14 pp on AgentClinic),
illustrating **frontier-reasoning models' brittleness under
reasoning-disabled regimes**; (5) an ORPHA-variant evaluation channel
adds ~20 pp R@1 universally — *not* DeepRare-specific. We release
the harness, canonical case schema, per-agent adapter shims, full
per-cell receipts, and a static-site leaderboard.

## CTA

`github.com/<USER>/RDAgentBench` · leaderboard `<USER>.github.io/rdab/`

---

## Scoring checklist

- [x] Hook (2 sentences): agent proliferation vs benchmark gap
- [x] What we built (3 sentences): 5 pillar × 4 layer × 11 systems + pre-registration
- [x] 5 numbered findings with concrete percentages
- [x] Release statement
- [x] ~220 words target
- [x] No model-version aliases that may rot (uses "DeepSeek V4-Flash" not version-string)
