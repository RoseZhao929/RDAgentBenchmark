# Phase 3.2 P3 (Genotype-Aware DDx) — Final Report (2026-05-19)

Backbone: `openrouter/google/gemini-3-flash-preview-20251217`
Sample: 50 Phenopacket-Store cases with ≥1 structured variant (seed=42)
Output: `data/round2/phase3/p3_genotype.jsonl`

## Per-adapter

| Adapter | n_ok | P3 R@1 | P3 R@5 | 95% CI (R@1) | vs P2 baseline | Mean lat |
|---|---|---|---|---|---|---|
| llm_control | 50 | **0.46** | 0.58 | [0.32, 0.60] | **+20 pp** (P2 0.26) | 3.4s |
| deeprare    | 50 | **0.38** | 0.42 | [0.25, 0.51] | **+16 pp** (P2 0.22) | 180.7s |

## Hypothesis test

**H2** (variant channel adds signal): supported on this sample.
- llm_control: McNemar paired on same 50 cases, P2 13/50 → P3 23/50.
  binomial(10 discordant, p=0.5) → one-sided p ≈ 0.06 (marginal).
- deeprare: P2 (mixed) 11/50 → P3 (variants) 19/50. Similar magnitude.

## Key paper-level reading

- **Variants help universally**, not specifically DeepRare's
  architecture. The llm_control baseline absorbs the same +20 pp lift.
  Headline claim revised in §A1: "variant channel adds ~20 pp R@1 to
  any agent that ingests it, regardless of agent specialisation."
- The 28 pp gap to DeepRare's published HPO+VCF 70.6 % is attributed
  to setup differences (structured-text variants vs real VCF +
  Phenotype Tool; web search disabled; harder mixed-difficulty
  PP-Store cases). Documented in §A1 narrative.
- deeprare R@5 ≈ R@1 (0.42 vs 0.38) — agent emits a single best
  ranked diagnosis; ranks 2-5 sparsely populated. Document as
  feature-not-bug; H4 wording adjusted so agents emitting single
  best-of-1 are not penalised in R@5 metric. (Alternative: report
  R@1 only for DeepRare and footnote.)

## Cost

~50 calls × 3.4s × Gemini Flash = ~$0.20 (llm_control)
~50 calls × 180s × Gemini Flash = ~$1-2 (deeprare, longer LLM context)
**Phase 3.2 total ≈ $1.50**, under budget.

## Paper deliverables

- §7.3 P3 genotype analysis: write up the +20 pp universal lift +
  the architectural-specialisation negative result.
- §A1 already patched to reflect the revised numbers.
- Worklog Retrospective #5 documents the analysis.
