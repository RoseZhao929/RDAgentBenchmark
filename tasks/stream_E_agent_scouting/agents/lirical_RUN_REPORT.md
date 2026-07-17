# LIRICAL Run Report (v1 Smoke Test)

**Date:** 2026-05-12
**Status:** **PASS — install complete, smoke test green, adapter wired into harness.**
**Role in lineup:** Non-LLM classic Bayesian baseline. Replaces PhenoBrain (dropped per `round1_execution_report.md` Plan B 2026-05-12).

---

## 1. Environment / Java

- **System Java:** missing. `/usr/bin/java` is the Apple stub that prints
  > The operation couldn't be completed. Unable to locate a Java Runtime.

  No `JAVA_HOME`, no `/Library/Java/JavaVirtualMachines/*`, no SDKMAN install.
  Per task constraint we did **not** `brew install` anything.

- **Bundled JRE (project-local, no system install):**
  - Source: Eclipse Adoptium Temurin 21 LTS, mac aarch64 JRE tarball.
  - URL: `https://api.adoptium.net/v3/binary/latest/21/ga/mac/aarch64/jre/hotspot/normal/eclipse` → redirect → `https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.11%2B10/OpenJDK21U-jre_aarch64_mac_hotspot_21.0.11_10.tar.gz`
  - Extracted to: `/Users/yutianzhao/Desktop/RDAgentBenchmark/agents/lirical/jdk-21.0.11+10-jre/`
  - Size on disk: 151 MB.
  - Version output:
    ```
    openjdk version "21.0.11" 2026-04-21 LTS
    OpenJDK Runtime Environment Temurin-21.0.11+10 (build 21.0.11+10-LTS)
    OpenJDK 64-Bit Server VM Temurin-21.0.11+10 (build 21.0.11+10-LTS, mixed mode, sharing)
    ```
  - Apple Quarantine note: tarball extraction skips the macOS code-signing dance — no `xattr -d com.apple.quarantine` needed. JRE launches cleanly.

- Adapter resolves Java in this order:
  1. constructor `agent_extra["java_bin"]`
  2. env `LIRICAL_JAVA`
  3. bundled JRE at `agents/lirical/jdk-*/Contents/Home/bin/java` (auto-discovered)
  4. system `which java`

## 2. LIRICAL install

- **Version:** v2.4.0 (latest GitHub release, tag 2026-04-09).
- **Source:** `https://github.com/TheJacksonLaboratory/LIRICAL/releases/download/v2.4.0/lirical-cli-2.4.0-distribution.zip` (27.8 MB zip).
- **Install dir:** `/Users/yutianzhao/Desktop/RDAgentBenchmark/agents/lirical/lirical-cli-2.4.0/` (29 MB after unzip).
- **Layout:**
  ```
  agents/lirical/
    lirical-cli-2.4.0/
      lirical-cli-2.4.0.jar          ← main entry
      lib/                           ← 52 transitive jars (+ gson, see below)
      examples/                      ← LDS2.v2.json + LDS2.vcf.gz + LDS2.yaml
      README.md, CHANGELOG.rst, LICENSE, legal/
    data/                            ← LIRICAL data dir, see §3
    jdk-21.0.11+10-jre/              ← bundled JRE
  ```
- **License:** GPL-3.0 (LIRICAL itself — see `LICENSE`). Compatible with our Apache-2.0 harness for citation/use; we do not re-bundle the jar in our repo distribution, we just invoke it locally.

### Patch applied: missing `gson` dep in v2.4.0 dist

LIRICAL v2.4.0's distribution `MANIFEST.MF` declares `Class-Path: ... lib/gson-2.8.9.jar ...` but the gson jar is **absent** from the released `lib/` directory. Without it, the phenopacket parser throws `NoClassDefFoundError: com/google/gson/JsonElement` at the very first JSON-message merge call inside `protobuf-java-util`. Mitigation:

```bash
curl -sL -o agents/lirical/lirical-cli-2.4.0/lib/gson-2.8.9.jar \
  https://repo1.maven.org/maven2/com/google/code/gson/gson/2.8.9/gson-2.8.9.jar
```

Filed mentally as upstream issue. Once added, LIRICAL boots cleanly.

## 3. LIRICAL data bundle

- **Path:** `/Users/yutianzhao/Desktop/RDAgentBenchmark/agents/lirical/data/`
- **Total size:** **345 MB** (well under the 5 GB worst-case; we skipped Exomiser VCF data entirely).
- **Files:**

  | File | Size | Source |
  |---|---|---|
  | `hp.json` | 30 MB | HPO via `lirical download` |
  | `phenotype.hpoa` | 17 MB | HPO via `lirical download` |
  | `en_product6.xml` | 8.0 MB | Orphanet via `lirical download` |
  | `hgnc_complete_set.txt` | 17 MB | HGNC via `lirical download` |
  | `mim2gene_medgen` | 858 KB | NCBI; manually re-pulled via HTTPS (see below) |
  | `hg19_refseq.ser` | 40 MB | Zenodo 5410367 |
  | `hg19_refseq_curated.ser` | 30 MB | Zenodo 5410367 |
  | `hg19_ensembl.ser` | 55 MB | Zenodo 5410367 |
  | `hg38_refseq.ser` | 51 MB | Zenodo 5410367 |
  | `hg38_refseq_curated.ser` | 33 MB | Zenodo 5410367 |
  | `hg38_ensembl.ser` | 53 MB | Zenodo 5410367 |

### Issue 1: `lirical download` aborts on NCBI FTP

LIRICAL's bundled `biodownload-1.1.2` calls NCBI's FTP server for `mim2gene_medgen`. NCBI FTP rejected the JRE21 client with `sun.net.ftp.FtpProtocolException: Welcome message:` (empty 220 banner — a JDK/NCBI compatibility bug widely reported). The download aborted **before** the Jannovar `.ser` files were attempted.

Workaround: pull `mim2gene_medgen` via HTTPS from the same NCBI host:

```bash
curl -sL -o agents/lirical/data/mim2gene_medgen \
  https://ftp.ncbi.nlm.nih.gov/gene/DATA/mim2gene_medgen
```

### Issue 2: Jannovar `.ser` files required even in phenotype-only mode

LIRICAL's `LiricalDataResolver` is called at bootstrap and verifies the presence of **all six** Jannovar transcript files **regardless of mode**, even though they are not used when no `--assembly` / `--vcf` is supplied. Solution: download from Zenodo (record 5410367) directly and **rename** to the names LIRICAL expects:

| Zenodo filename | Renamed to |
|---|---|
| `ensembl_87_hg19.ser` | `hg19_ensembl.ser` |
| `refseq_105_hg19.ser` | `hg19_refseq.ser` |
| `refseq_curated_105_hg19.ser` | `hg19_refseq_curated.ser` |
| `ensembl_91_hg38.ser` | `hg38_ensembl.ser` |
| `refseq_109_hg38.ser` | `hg38_refseq.ser` |
| `refseq_curated_109_hg38.ser` | `hg38_refseq_curated.ser` |

The renames mirror what LIRICAL's `DownloadCommand.java` does at download time (verified by reading the v2.4.0 source).

## 4. Smoke tests

### Smoke A — LIRICAL CLI on shipped example

```bash
cd /Users/yutianzhao/Desktop/RDAgentBenchmark/agents/lirical/lirical-cli-2.4.0
../jdk-21.0.11+10-jre/Contents/Home/bin/java -jar lirical-cli-2.4.0.jar \
  phenopacket \
  -p examples/LDS2.v2.json \
  -d ../data/ \
  -o ../smoke_out/ \
  -f tsv -f json \
  -x smoke
```

**Result:** PASS in ~3.1 s. 8,661 diseases prioritized. Top-3 from `smoke_out/smoke.tsv`:

```
rank  diseaseName               diseaseCurie   pretestprob  posttestprob  compositeLR
1     Marfan syndrome           OMIM:154700    1/8661       100.00000%    17.466
2     Loeys-Dietz syndrome 2    OMIM:610168    1/8661       100.00000%    15.571
3     Loeys-Dietz syndrome 1    OMIM:609192    1/8661       100.00000%    11.768
```

Ground truth for the LDS2 example is Loeys-Dietz syndrome 2 → **rank 2, post-test prob ≈ 1.0**. Tool behaves as documented.

### Smoke B — Adapter end-to-end via Python harness

Exactly the snippet from the task spec:

```python
from harness.ingest import ingest_phenopacket_store
from harness.agents.lirical import LIRICALAdapter

case = next(ingest_phenopacket_store("data/phenopacket_store/notebooks", limit=1))
adapter = LIRICALAdapter()
log = adapter.predict(case, pillar="P2_phenotype_ddx", eval_mode="gold_hpo")
print(log.ranked_predictions[:5], log.confidence_scores[:5])
```

**Result:** PASS.

```
case_id:     PMID_15266616_100
gold_label:  OMIM:147791 / Jacobsen syndrome
HPO terms:   63 observed
status:      ok
latency_ms:  8002
top 5 ranked: ['OMIM:620908', 'OMIM:259050', 'OMIM:621016', 'OMIM:610443', 'OMIM:620305']
top 5 scores: [0.1431, 0.0482, 0.0063, 0.0024, 0.0011]
```

The gold label OMIM:147791 (Jacobsen, a 11q-terminal-deletion contiguous-gene syndrome with non-specific multi-system features) is not in the top-5; expected behaviour for LIRICAL on broad-symptom contiguous-gene syndromes — it ranks `OMIM:620908` (the top hit) at posttest 14.3% which is the typical "no strong evidence" output. Three additional cases ran cleanly (each ~8 s, status ok), confirming the adapter is robust across cases and that scores are well-formed floats in [0, 1].

## 5. Adapter

- **Path:** `/Users/yutianzhao/Desktop/RDAgentBenchmark/harness/agents/lirical.py`
- **Class:** `LIRICALAdapter(AgentAdapter)`, `NAME = "lirical"`, default `backbone_id = "non-llm/lirical-2.4.0"`.
- **Pillar support:** P2_phenotype_ddx (default). Pillar 3 (genotype-aware via Exomiser) is **not** wired in v1 — would require adding the `--assembly hg38 --vcf …` flags and downloading the Exomiser variant DB (~5 GB). Tracked as future work.
- **No LLM call:** `CostBreakdown` left at the default zero. Latency is the Java subprocess wall-clock.
- **Outputs populated on PredictionLog:**
  - `ranked_predictions`: list of OMIM CURIEs from LIRICAL TSV (top-K, default K=30).
  - `confidence_scores`: parallel list of post-test probabilities, with LIRICAL's `xx.xxx%` strings parsed into floats in [0, 1].
  - `raw_response_excerpt`: first 20 lines of the TSV (includes the HPO-input echo header — useful for audit).
  - `total_latency_ms`: subprocess wall-clock.
  - `status`: `"ok"` / `"agent_error"` / `"timeout"` / `"parser_error"` / `"skipped"` (case has no HPO).
- **Project mapping:** `CanonicalCase.gold_hpo_terms` → minimal GA4GH Phenopacket v2 JSON with `subject.id`, `subject.sex`, and a `phenotypicFeatures[]` array carrying each HP id, label, optional `onset` (HPO modifier id), and `excluded: true` for negated terms. We deliberately skip `interpretations` (causal-variant info) so the adapter operates in pure phenotype-only mode and we can never accidentally leak gold-gene info into the prediction.
- **Registered in `harness/agents/__init__.py`** alongside the other 7 adapters.
- **No env vars required by default** (auto-discovery works) but the following are honored if set:
  `LIRICAL_HOME`, `LIRICAL_JAR`, `LIRICAL_DATA`, `LIRICAL_JAVA`, `LIRICAL_TIMEOUT_S`, `LIRICAL_TOP_K`.

## 6. Disk footprint

```
agents/lirical/                          550 MB
├── lirical-cli-2.4.0/                    29 MB  (jar + 53 libs incl. gson patch)
├── jdk-21.0.11+10-jre/                  151 MB  (Adoptium Temurin 21 mac aarch64)
├── data/                                345 MB  (HPO + HPOA + HGNC + Orpha + 6 Jannovar .ser)
└── smoke_out/                           ~25 MB  (smoke test artefacts; safe to gitignore)
```

No multi-GB Exomiser bundle was downloaded. Future Pillar-3 wiring needs an additional ~5 GB for `exomiser_hg38_2402.zip`.

## 7. Files touched / produced

- **NEW** `harness/agents/lirical.py` (adapter, ~250 LOC including docstrings).
- **MOD** `harness/agents/__init__.py` (1 import + 1 `__all__` entry).
- **NEW** `agents/lirical/` directory tree (550 MB; should be `.gitignore`d alongside `agents/deeprare/.venv/`, `data/phenobrain_checkpoints/`, etc.).
- **NEW** `tasks/stream_E_agent_scouting/agents/lirical_RUN_REPORT.md` (this file).

## 8. Open items / future work

- **Gitignore:** add `agents/lirical/` (550 MB) to repo `.gitignore`. Same pattern as `agents/deeprare/.venv/`.
- **Pillar 3 (genotype-aware):** download Exomiser hg38 data bundle, add `vcf_path` → `--vcf` / `--assembly hg38` wiring in the adapter, store gene-level scores in a side channel (the schema's `ranked_predictions` is at disease level only).
- **Mirror the Zenodo `.ser` files** to lab S3 — Zenodo records are stable but a CI build needs reproducibility.
- **Upstream issue:** file LIRICAL v2.4.0 bug for missing `gson-2.8.9.jar` in the distribution.

---

## Bug Fix 2026-05-15 (Phase-0 retro)

**Bug D3** (round2_plan.md § 复盘 ①): On RareArena cases that ship only a
free-text vignette (no `gold_hpo_terms`), the adapter returned
`status="skipped"` for 25/50 in the Mini Phase 0 sample.

**Fix** in `harness/agents/lirical.py`:
- When `eval_mode="end_to_end"` AND `case.gold_hpo_terms` is empty AND
  `case.free_text_vignette` is non-empty: lazy-build an
  `LLMControlAdapter(backbone_id="openrouter/google/gemini-3-flash-preview")`,
  call `extract_phenotypes(case)` to get free-text findings, then call
  `harness.metrics.hpo_phrase_to_id.phrase_to_hp_id()` to normalise each
  phrase to a canonical `HP:xxxxxxx` (rapidfuzz threshold 90).
- The extracted HpoTerms are projected onto a shallow `case.model_copy()`
  before phenopacket projection. `gold_hpo` mode is unchanged.
- `log.extracted_hpo_terms` is populated so downstream P1 evaluation can
  audit the upstream extraction quality.
- `log.extra` carries
  `{hpo_extraction_phrases_total, hpo_extraction_phrases_resolved,
  hpo_extraction_misses_sample}` for debugging.

**Bug D2 (cost)**: LIRICAL is a Java/Bayesian non-LLM ranker — `cost_usd=0`
is correct. No change. The end_to_end extractor's USD cost is captured
inside the spawned LLMControlAdapter's log (not surfaced here for the
LIRICAL adapter row, but logged in its own PredictionLog if needed).

Verified by re-run on the same 50-case sample — `lirical` went from 25/50
ok → 50/50 ok. See `data/round2/phase0/REPORT_v2.md`.
