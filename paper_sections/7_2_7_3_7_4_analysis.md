# §7.2 / 7.3 / 7.4 / 7.6 Analysis (paper draft v0)

> 数据源:Phase 4a N=100 × 4 dataset, dual-report (strict + variants),
> + Phase 3.2 P3 genotype 50-case pilot
> 状态:文字 ready,等 Phase 4a final 后 pin 终 number

---

## §7.2 Scaffolding Pays — but only on free-text + non-reasoning backbones

Phase 4a holds the central backbone constant and varies scaffold complexity:
- **No scaffold** (llm_control): single LLM call, structured output.
- **Single-pass multi-agent** (mdagents): 3-domain experts + Chief MO synthesis.
- **Multi-round debate** (medagents): 3-expert iterative refinement.
- **OSCE simulation** (agentclinic): doctor / patient / measurement / moderator loop.
- **Panel orchestration** (MAI-DxO): ~5 medical agents with ordering / questioning.

**On PP-Store with Gemini Flash** (N=2000, frozen main matrix) the scaffolding ladder shows:
- llm_control: 0.29
- mdagents (intermediate): 0.28 (−1 pp vs control)
- medagents (debate): 0.30 (+1 pp over llm_control)
- agentclinic (OSCE): 0.21 (−8 pp regression vs control)
- maidxo (panel): 0.03 (catastrophic, see § below)

**Interpretation**: scaffolding does *not* reliably beat a single-LLM control on
phenotype-only DDx. Deepening deliberation on the same input (medagents debate)
helps at most marginally (+1 pp, within overlapping CIs at N=2000), and mdagents
actually sits ~1 pp *below* the control. Scaffolding that *changes the input
format* (agentclinic OSCE dialogue, maidxo panel orchestration) regresses sharply
on HPO-list input because the agent's design assumes narrative input. At the full
N=2000 the direction is clear: for P2 the scaffold is a net-neutral-to-negative
choice on this backbone. (The +2 pp "medagents best" reading in earlier drafts was
a small-sample N=500 artifact; see §A1.)

**Backbone interaction**: on DS V4-Pro mdagents reaches 0.35 (best of its
backbones, N=100), suggesting V4-Pro pairs well with mdagents' moderator-vote
architecture. On GPT-5-minimal mdagents drops to 0.28 — the moderator's "weigh
expert opinions" prompt benefits from GPT-5's reasoning, which we forced off.

**MAI-DxO catastrophic failure (R@1 ≤ 0.07 across all backbones)**:
MAI-DxO is designed for NEJM clinicopathologic case-reports (≥2000-word
narratives). On HPO-list input the panel's "ask the patient" mechanism
degenerates — the input *is* the answer to most questions. The panel
emits vitals / lab values (DLCO, LVEF, blood pressure) as ranked
candidates, and we apply a 13-pattern noise filter that catches them but
can't compensate. Documented in §5.1.

---

## §7.3 Genotype Channel Helps Any Agent that Ingests It (+20 pp)

Phase 3.2 P3 (HPO + structured variants), **full-N paired** on 500 PP-Store
cases with ≥1 structured variant (2026-07-06; llm_control, Gemini Flash, same
cases both modes):

| Agent | P2 (HPO-only) R@1 | P3 (HPO + variants) R@1 | Lift |
|---|---|---|---|
| llm_control (n=500 paired) | 0.296 | **0.494** | **+19.8 pp** |
| deeprare (n=50 pilot) | 0.22 | **0.38** | +16 pp |

**H2 confirmed at full-N and FWE-robust** (§8.8): the +19.8 pp lift on n=500
paired cases gives a McNemar χ²(cc)=85 (P3-win 106 vs P2-win 7) and 2-prop
z=6.40 (Holm-adj p=3.0e-10) — up from the earlier n=50 pilot (z=2.08) that did
not survive correction. Both agents gain ~20 pp R@1 from a structured-text
variants block in the prompt. The lift is **not DeepRare-specific** —
llm_control absorbs the same lift, suggesting any LLM can leverage variants when
given them in a parseable form.

The 28-pp gap to DeepRare's published HPO+VCF 70.6 % is explained by
three documented setup differences:
- Our variants are a structured-text block, not real VCF integrated through
  DeepRare's Phenotype Tool.
- Web search disabled (`DEEPRARE_NO_WEB=1`) for contamination control.
- Phenopacket-Store is a harder mixed-difficulty corpus.

**Honest framing**: variant channel adds ~20 pp R@1 to any agent that
ingests it, *not* "DeepRare specifically exploits genotype-aware
reasoning" — the latter claim does not survive contact with the LLM
control baseline.

---

## §7.4 Faithfulness vs Accuracy — H10 exploratory (judge-dependent)

Phase 1 P5 reasoning_communication pilot on the 40-trace sample (LLM-judge
faithfulness scoring; see §7.5 for the judge-family analysis):

**Finding (de-confounded, 2026-07-22 frozen audit)**: measured on identical
repaired traces (n=40), the Spearman ρ between the judge's faithfulness score
and the agent's actual top-1 accuracy is **0.457 (Gemini judge)** and **0.640
(Claude judge)**. The pre-registered H10 threshold for "decoupled" was ρ < 0.5,
so H10 is **borderline and judge-dependent** — met under one judge, not the
other — and we report it as **exploratory, not confirmed**. (An earlier draft
reported ρ = 0.098 under the Gemini judge and read this as strong decoupling;
that value was a trace-capture artifact and is withdrawn — see §7.5 Correction.)
The durable, direction-independent point remains: **accuracy-only benchmarks can
under-evaluate rare-disease diagnostic AI**, because a high-accuracy agent can
still score low on faithfulness (high confidence without justification,
hallucinated differential reasoning) — but we no longer claim a strong
quantitative decoupling.

---

## §7.6 Dataset Difficulty Stratification

Four-layer dataset selection deliberately spans difficulty:

| Layer | Best LLM R@1 (N=2000) | Best Classical/Offline R@1 |
|---|---|---|
| Phenopacket-Store (HPO+demographic, curated rare diseases) | 0.30 (medagents Gemini) | **0.47** (lirical) |
| RareArena RDS (free-text vignette, narrative) | 0.30 (medagents Gemini) | n/a (no HPO) |
| RareBench HF (HPO-only, sparse, expert curated) | 0.30 (deeprare Gemini) | 0.28 (vc_rdagent offline) |
| MIMIC-IV diverse (structured note → named disease) | see note | n/a |

(MIMIC-IV rows are omitted from this recomputed table: its gold labels were stripped from the frozen slim release, so R@1 is not recomputable at commit `43efa1e5`; the earlier N=500 MIMIC figures are not carried forward. All non-MIMIC values are the N=2000 frozen-matrix recompute.)

**Reading**:
- **PP-Store is the "easiest" layer** — curated cases, expert-cleaned HPO,
  paper-faithful baselines (lirical 0.47, replicating its paper-claimed range).
- **RareBench HF is the layer where classical and LLM are closest** — at
  N=2000 the best LLM (deeprare Gemini 0.30) slightly edges the best classical
  (vc_rdagent 0.28), and both sit well below their PP-Store levels; the sparse,
  expert-curated HPO and ID-mapping cross-ref make it the hardest HPO layer for
  *both* families. We report strict R@1 with the variant-aware channel (§7.3);
  a hierarchy-aware secondary metric is left to future work.
- **MIMIC-IV** is excluded from the recomputed frozen table (gold labels
  stripped from the slim release); we do not carry forward the earlier
  MIMIC point estimates.

---

## Cross-references

- §6 Main Results — full matrix
- §7.5 Self-Preference Bias — judge model methodology
- the reproducibility audit Reproducibility — per-baseline replication audit
- §9 Limitations — MAI-DxO×GPT-5 incompat, MIMIC framing

---

## §7.7 H1 — Prevalence stratification (real Orphanet prevalence)

Pre-registered H1: R@1 declines monotonically from common-rare to super-rare.
Tested with **real Orphadata prevalence** (5,108 ORPHA
codes; point-prevalence preferred, rarest validated class per disease), gold
mapped via direct ORPHA or OMIM→ORPHA cross-map. Pooled R@1 by tier
(commonest→rarest):

| Tier | LLM (Gemini, N=500 cells) | Classical (LIRICAL+VC-RDAgent) |
|---|---|---|
| common-rare (≥1/10,000) | 0.37 (n=156) | 0.30 (n=64) |
| moderate (1-9/100,000) | 0.26 (n=690) | 0.23 (n=347) |
| ultra-rare (1-9/1,000,000) | 0.39 (n=693) | 0.33 (n=322) |
| **super-rare (<1/1,000,000)** | **0.22** (n=1167) | **0.50** (n=529) |

**Strict monotonic H1 is _not_ supported** for either class (an ultra-rare
mid-spike breaks monotonicity). But the **tail contrast is the real story**:
- **LLMs decline toward the rarest tier** (common 0.37 → super-rare 0.22,
  −15 pp) — consistent with the training-frequency-exposure mechanism H1
  posits, just non-monotonic in the middle.
- **Classical/offline agents do their _best_ on super-rare disease** (0.50,
  their top tier) — the **inverse** of H1. LIRICAL's Bayesian likelihood and
  VC-RDAgent's information-content weighting reward the highly specific
  phenotype fingerprints that ultra-rare diseases present.
- On the rarest tier the classical-vs-LLM gap widens to **+28 pp** (0.50 vs
  0.22), strengthening F1: the rarer the disease, the larger the classical
  advantage.

**Operationalization note (for PI review)**: "rarest validated class per
disease" is a conservative choice when a disorder has multiple prevalence
estimates; point-prevalence entries are preferred over cases/families.
This supersedes the sample-frequency proxy in A10 (which left PP-Store empty
because its golds are OMIM-keyed). Visualised in **Figure 5** — the LLM-classical
crossover at super-rare is the headline F1 evidence.

---

## §7.8 H4 — Scaffolding × case complexity (organ-system count) ✅

Pre-registered H4: multi-agent scaffolding *helps on complex cases but hurts on
simple ones* (overthinking). Complexity = # distinct HPO organ systems the gold
phenotype touches (single=1, oligo=2–3, multi=4+; HPO-input layers, full-N
2026-07-06). Scaffold − no-scaffold-control (llm_control) R@1 delta, Gemini Flash:

| Complexity | mdagents − control | medagents − control |
|---|---|---|
| single-system (n≈221–321) | **−0.08** | **−0.09** |
| oligo (2–3, n≈765–1061) | −0.01 | −0.05 |
| multi-system (4+, n≈3012–4329) | **+0.00** | −0.02 |

**H4 supported (FWE-robust, §8.8)**: the difference-of-differences —
(mdagents−control on multi) − (mdagents−control on single) = +0.081 — is
significant at full-N (2-prop z=2.51, Holm-adj p=0.012), up from the n=42
sub-bin pilot that was under-powered. The mechanism is a *shrinking penalty*
rather than a gain: both multi-agent scaffolds clearly *trail* the single-LLM
control on single-system cases (overthinking simple presentations, −0.08/−0.09)
and *catch up to parity* (mdagents ≈ +0.00) as organ-system involvement grows.
This sharpens §7.2: the small average scaffolding gain (F2) is really a *penalty
on simple cases that dissolves on complex ones* — the scaffolding's benefit is
avoiding its own overthinking cost when the case genuinely warrants deliberation,
not adding accuracy above the control.

## §7.10 A6 — Data-Contamination Audit (TS-Guessing approximation) ✅

Anticipated objection #1 is that LLM agents may perform well only because
pre-cutoff PubMed corpora *contain* the diseases we test on; the agents
would be exploiting training-frequency, not phenotype-disease reasoning.
We test this via a TS-Guessing approximation: for each gold ORPHA in
our phase4a predictions (top 600 by occurrence, ≥5 cases each), we
query NCBI PubMed `esearch.fcgi` with `"<disease name>"[All Fields]`
and `maxdate=2024/06/30` (a conservative pre-cutoff for all four
backbones), then correlate **log(mention count + 1)** with per-disease
R@1, per backbone, via Spearman ρ.

| Backbone | n diseases | Spearman ρ | Interpretation |
|---|---|---|---|
| `gemini` (Gemini 3 Flash) | 244 | **0.365** | 🟡 weak |
| `gpt-5` (GPT-5 minimal) | 87 | **0.354** | 🟡 weak |
| `v4-flash` (DeepSeek V4-Flash) | 244 | **0.348** | 🟡 weak |
| `v4-pro` (DeepSeek V4-Pro) | 179 | **0.294** | 🟡 weak |
| `lirical` (classical Bayesian) | 26 | −0.155 | ✅ null (control) |
| `vc_rdagent` (offline IC) | 26 | −0.059 | ✅ null (control) |

**Dichotomy** is the clean finding: every LLM backbone clusters at
ρ ≈ 0.29–0.37, every classical / offline baseline at ρ ≈ 0. The
classical baselines do not consume text — they cannot have been
"trained on" PubMed — so their null ρ acts as a **methodological
control**, confirming our pipeline introduces no spurious correlation.

**Reading**.
1. There IS a measurable training-frequency bias in LLM agents; the
   simplest contamination critique is *partially* supported.
2. But ρ ≈ 0.3 means pre-cutoff exposure explains ≈ 9 % of R@1 variance
   (ρ² ≈ 0.09), leaving ≈ 91 % to phenotype reasoning + extraction
   quality + scaffold design. The contamination signal is real but
   **bounded**.
3. The L4 post-cutoff PMC-OA holdout (2024-01-01+, after every backbone's
   training cutoff) provides the bias-free reference. **We now report the
   difficulty-matched cutoff experiment (H3, §7.10.1)**: performance does
   *not* drop across the training cutoff, bounding contamination from a
   second, independent angle.

### §7.10.1 H3 — Difficulty-matched pre- vs post-cutoff (contamination, controlled)

A naive "post-cutoff R@1" is confounded by dataset difficulty. We remove that
confound by building a **pre-cutoff PMC set with the identical pipeline** —
same source (PMC-OA rare-disease case reports), same MeSH query, same
Gemini-3-Flash extraction, same Orphanet mapping, same Opus-4.8 gold
verification — changing only the publication window (**2016–2020, inside every
backbone's training window** vs **2024+, after all cutoffs**). On the
Opus-diagnosis-agreed clean-gold subset (pre 195/220, post 198/198), Gemini-Flash:

| Agent | pre-cutoff R@1 | post-cutoff R@1 | Δ (post−pre) |
|---|---|---|---|
| llm_control | 0.559 | 0.616 | +0.057 |
| mdagents | 0.582 | 0.611 | +0.029 |
| medagents | 0.564 | 0.626 | +0.062 |
| **pooled (single-pass)** | **0.568** | **0.618** | **+0.049** (z=1.72) |

**Post-cutoff R@1 is at least as high as pre-cutoff for every agent.** If
memorisation inflated LLM rare-disease performance, memorisable (pre-cutoff)
cases would score *higher* than unmemorisable (post-cutoff) ones — the opposite
of what we observe. Strong performance transfers to genuinely unseen 2024+ cases,
so **memorisation is not the driver**. The small post-cutoff *advantage* is most
plausibly newer case reports being marginally clearer (more routine genetic
confirmation), not contamination. Together A6 (weak within-dataset frequency
ρ≈0.3) and H3 (no drop across the cutoff) bound contamination to a small effect.

**Strengthens F1, does not weaken it**. The LLMs' small ρ-explained
advantage is concentrated on diseases LLMs have seen more often; the
classical baselines deliver consistent reasoning across the entire
prevalence spectrum. This is the same direction as F1 (classical >
LLM on the rarest tier, §7.7 H1, +28 pp on super-rare) viewed from a
different axis.

Visualised in **Figure 4**.

---

## §7.9 H7 — Failures cluster by specialty (shared blind spots) ✅

Pre-registered H7: agents' weakest specialties *correlate across agents*
(Spearman ρ≥0.6), implying dataset/ontology gaps rather than agent-specific
weaknesses. Specialty = modal HPO organ system per case (23-category HPO axis).
Cross-agent rank correlation of per-specialty R@1 (full-N 2026-07-06, **18
specialties** n≥10 each, Gemini Flash):

| Pair | Spearman ρ |
|---|---|
| llm_control vs mdagents | **0.93** |
| llm_control vs medagents | **0.96** |
| mdagents vs medagents | **0.92** |

**H7 confirmed and FWE-robust** (§8.8): all ρ≥0.92 (up from the
n=13-specialty pilot at ρ≈0.73); the conservative ρ=0.92 gives Holm-adj
p=0.0016. Universally **weak** specialties: nervous system
(0.11–0.14), metabolism/homeostasis (0.10–0.16), digestive (0.09); universally
**strong**: cardiovascular (0.41–0.44), integument (0.44–0.56). The shared
ordering points to ontology/data-level difficulty, not scaffold-specific gaps.
Notably the **classical baselines invert the nervous-system weakness** (LIRICAL
0.35, VC-RDAgent 0.43 vs LLM ~0.12) and lead on head/neck (0.52–0.54) — another
facet of F1's classical advantage. Visualised in **Figure 7**.
