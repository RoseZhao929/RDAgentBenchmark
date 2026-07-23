# DeepRare Reproduction Documentation

## Source

- Repo: `https://github.com/dragon-ZZZ/deeprare` (cloned at `agents/deeprare/`)
- Paper: Sun et al., **DeepRare: A Generalist Diagnosis Assistant for Rare Diseases.**
  *Nature* 2026. [DOI placeholder]
- License: **CC BY-NC 4.0** (non-commercial; academic fair use allowed)
- Date acquired: ~2026-04
- Git commit: see `agents/deeprare/.git/HEAD` (frozen)

## Paper-claimed results

| Setup | Metric | Value | Context |
|---|---|---|---|
| HPO-only DDx, RareBench | R@1 | ~0.55 | Paper Table 3 |
| HPO + VCF, joint genotype-phenotype | R@1 | **0.706** | Paper Table 4 (headline) |
| With web tools enabled | R@1 | ~0.72 | Paper §5.3 |

## How we reproduce

- **Mode**: `--no-web --local-embedding` (env: `DEEPRARE_NO_WEB=1`,
  `DEEPRARE_LOCAL_EMBEDDING=1`)
- **Backbone**: configured via `--model openai --openai_apikey <or-key>
  --openai_model <model_id>` — wires DeepRare's openai client to
  OpenRouter
- **Pillar 2 (HPO-only)**: cases.csv with HPO list only
- **Pillar 3 (genotype-aware)**: variant context appended to
  cases.csv `disease` column (soft hint; DeepRare's variant ingestion
  pathway is partially bypassed because we don't have real VCFs for
  every case)
- **Sample**: 50 case (25 PP-Store + 25 RareArena), seed=42

## Endpoint patches (allowed: OpenRouter wiring only)

| File | Lines | Purpose | Behavior-preserving? |
|---|---|---|---|
| `api/interface.py` | ~3 LOC | accept `OPENAI_BASE_URL` env + `DEEPRARE_MINI_MODEL` override for OpenRouter | Yes |

## Behavior-changing patches (must be documented in paper)

> ⚠️ **2026-05-19 patch — flagged in baseline-strict reproduction**

| File | Change | Rationale | Effect |
|---|---|---|---|
| `agents/deeprare/diagnosis.py` line 63-65 | Added fallback regex `r"^##\s+(.+?)\s*\(Rank\s*#\d+"` when primary `\*\*(.*?)\*\*` returns 0 matches | GPT-5 minimal does not emit markdown bold; primary parser returns empty `diseases` list → `eval_tokenizer([])` crashes with `IndexError` in `transformers.tokenization_utils_fast` | **Dual-reported**: see Observed Results below |
| `agents/deeprare/diagnosisGene.py` line 63-65 | Same fallback regex | Genotype mode mirrors HPO-only mode | Same |

**Why this was added**: without the fallback, DeepRare × GPT-5 = 50/50
systematic `agent_error` (tokenizer crash). With the fallback, DeepRare
× GPT-5 = R@1 ≈ 0.30 with the actual differentials GPT-5 generated.

**Behavior-preserving check**: the fallback ONLY activates when
primary regex returns 0. For backbones that emit markdown bold
(Gemini 3 Flash, DeepSeek V3.2, Claude), the fallback never fires →
behavior identical to upstream.

## Adapter wrapper

- File: `harness/agents/deeprare.py`
- Pattern: subprocess to `agents/deeprare/.venv/bin/python
  agents/deeprare/main.py …`
- Per-case unique output dir
  (`result_harness_<run_id>_<case_id>_<suffix>/`) to prevent first-case
  state leak (fix 2026-05-16, Retrospective #2)
- Wrapper-side ranked_predictions parser (`_RANK_RE`) — also accepts
  no-bold format (separate from in-baseline fallback)
- ENV `OPENROUTER_REASONING_EFFORT=minimal` forwarded to subprocess
  for GPT-5 / o-series

## Observed results vs paper (50-case pilot, dual report)

### Pillar 2 (HPO-only)

| Backbone | Mode | n_ok | R@1 | R@5 | Paper expected |
|---|---|---|---|---|---|
| Gemini 3 Flash | no-web + local-embed | 50/50 | 0.22 | — | ~0.55 |
| DeepSeek V3.2 | no-web + local-embed | 50/50 | 0.12 | — | ~0.55 |
| GPT-5 (minimal) **strict** | no-web + local-embed | **0/50** | — | — | n/a |
| GPT-5 (minimal) **with fallback** | no-web + local-embed | (in flight) | ~0.30 | — | n/a |

### Pillar 3 (HPO + structured variants)

| Backbone | n_ok | R@1 | R@5 | Paper expected |
|---|---|---|---|---|
| Gemini 3 Flash | 50/50 | **0.38** | 0.42 | 0.706 (HPO+VCF) |

### Gap analysis (Pillar 3 = paper headline)

- Paper: 0.706 with HPO+VCF and web tools
- Ours: 0.38 with structured-text variants, web disabled, harder
  Phenopacket-Store sample
- 32 pp gap attributable to:
  1. **Web tools disabled** (`DEEPRARE_NO_WEB=1`) — paper's headline
     uses full web+RAG stack
  2. **Variants as structured text, not VCF** — DeepRare's
     Phenotype Tool variant integration partially bypassed
  3. **Harder corpus**: PP-Store mixed-difficulty vs DeepRare's
     curated set
  4. **Local embedding (bge-small-en-v1.5)** — paper uses dedicated
     biomedical embedding

## Known incompatibilities

| Backbone | Issue | Resolution |
|---|---|---|
| GPT-5 (minimal) **strict mode** | Empty `diseases` list → `IndexError` in `transformers.tokenization_utils_fast._batch_encode_plus` | **Strict-mode**: documented incompat in §9 L1 + this doc. **Adapter-relaxed mode**: in-baseline fallback regex accepts `## Disease (Rank #N/5)` header (see §Behavior-changing patches) |
| MAI-DxO interaction | N/A — DeepRare runs alone |
| **Legacy MIMIC ICD-title task (all backbones)** | **R@1 = 0.000** (V4-Flash 0/214, Gemini 0/495) | Archived construct-mismatched result; not part of the replacement structured-EHR task. |

### DeepRare × legacy MIMIC ICD-title task: R@1 = 0.000 root-cause (2026-05-28)

A near-zero score looked suspicious, so we audited it (no-skip principle). It is
**genuine, not an eval bug**:

- **Eval works**: on the *same* MIMIC golds, `llm_control` matches (e.g. gold
  "Essential thrombocythemia" ORPHA:3318 → llm_control predicts ORPHA:3318 ✓).
  So `gold_hit_with_crossmap` is functioning.
- **DeepRare produces predictions**: 192/218 ok-cases have non-empty
  `ranked_predictions` (only 26 empty). It is not silently failing — it emits
  rare-syndrome guesses that are simply wrong.
- **Why all wrong**: DeepRare is a rare-disease HPO-pipeline. On MIMIC it
  (a) extracts *noisy* HPO from unstructured discharge summaries (unlike the
  clean HPO in Phenopacket-Store), and (b) only ever outputs *rare genetic
  syndromes*. Many MIMIC golds are common ICU conditions that merely carry an
  ORPHA code (Cardiogenic shock ORPHA:97292, Dilated cardiomyopathy
  ORPHA:217604, Anal fistula ORPHA:228113), which DeepRare's rare-syndrome
  search will never surface. Example: gold "Cardiogenic shock" → DeepRare
  predicts "Syphilis / Neurosyphilis / Congenital Syphilis".
- **Cross-backbone consistency** (V4-Flash 0/214, Gemini 0/495) → robust, not a
  single-run artifact.

**Paper finding** (not a limitation to hide): specialized HPO-pipeline agents
collapse on free-text clinical notes because they depend on clean structured
HPO that free-text does not provide; a plain LLM that reads the note and echoes
the stated diagnosis does far better. **Caveat to state in the MIMIC-layer
method note**: this layer tests *named-disease recognition from free text*, not
*rare genetic diagnosis* — some golds are common conditions with ORPHA codes.

Note: V4-Flash MIMIC cell was stopped at N=214 (would need ~2.3 days more for
N=500; 0/214 is already statistically conclusive, 95% CI upper bound ~0.017).

## Run receipts

- Pillar 2 pilot:
  `data/round2/phase2_fix/predictions_deeprare_{gemini,ds,gpt5}_v3.jsonl`
- Pillar 3 pilot:
  `data/round2/phase3/p3_genotype.jsonl`
- RUN_REPORT (historical):
  `tasks/stream_E_agent_scouting/agents/deeprare_RUN_REPORT.md`

## Last-updated

- 2026-05-19 — Initial doc; dual-reporting protocol locked
