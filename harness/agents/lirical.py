"""LIRICAL adapter — non-LLM classic Bayesian DDx baseline.

LIRICAL (LIkelihood Ratio Interpretation of Clinical AbnormaLities) is the
Robinson-lab Java tool that replaces PhenoBrain in the v1 lineup (see
round1_execution_report.md "Plan B" decision 2026-05-12). It was used to build
the RareBench LIRICAL split (370 cases) and is the de-facto non-LLM baseline
on phenopacket-style HPO inputs.

Pipeline:
1. Project CanonicalCase.gold_hpo_terms onto a minimal GA4GH Phenopacket JSON
   (subject + phenotypicFeatures with `excluded` flag for negated terms).
2. Subprocess-invoke `lirical phenopacket -p <case>.json -d <data> -f tsv -f json`.
3. Parse the TSV (rank, diseaseName, diseaseCurie, pretestprob, posttestprob,
   compositeLR) into ranked_predictions + confidence_scores.

No LLM is involved → backbone_id is accepted but unused; cost is hard-coded
to zero. Latency is the wall-clock Java subprocess time.

Phenotype-only mode (no `--assembly`, no `--vcf`): LIRICAL still requires the
Jannovar transcript `.ser` files to be present in the data dir, but they are
not actually consulted for likelihood computation. Adapter logs a warning if
they are missing and returns status='agent_error'.

Config (env or constructor `agent_extra`):
  LIRICAL_HOME   — agents/lirical/ root (contains lirical-cli-X.Y.Z/ and data/)
  LIRICAL_JAR    — explicit path to lirical-cli-*.jar
  LIRICAL_DATA   — LIRICAL data directory (default $LIRICAL_HOME/data)
  LIRICAL_JAVA   — java binary (default $LIRICAL_HOME/jdk-*/Contents/Home/bin/java
                   if present, else `java` on PATH)
  LIRICAL_TIMEOUT_S — per-case subprocess timeout (default 180)
  LIRICAL_TOP_K  — how many predictions to keep in ranked_predictions (default 30)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from harness.agents.base import AgentAdapter
from harness.canonical_case import CanonicalCase, HpoTerm
from harness.logging.schema import EvalMode, Pillar, PredictionLog


# -------- defaults / discovery --------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_LIRICAL_HOME = _REPO_ROOT / "agents" / "lirical"


def _discover_jar(lirical_home: Path) -> Optional[Path]:
    """Find the lirical-cli-*.jar inside agents/lirical/lirical-cli-X.Y.Z/."""
    for sub in sorted(lirical_home.glob("lirical-cli-*"), reverse=True):
        if sub.is_dir():
            for jar in sub.glob("lirical-cli-*.jar"):
                return jar
    return None


def _discover_bundled_java(lirical_home: Path) -> Optional[Path]:
    """Find the bundled JRE under agents/lirical/jdk-*/Contents/Home/bin/java."""
    for jdk_dir in sorted(lirical_home.glob("jdk-*"), reverse=True):
        candidate = jdk_dir / "Contents" / "Home" / "bin" / "java"
        if candidate.exists():
            return candidate
        # Linux tarball layout: jdk-*/bin/java
        candidate = jdk_dir / "bin" / "java"
        if candidate.exists():
            return candidate
    return None


def _resolve_java(lirical_home: Path, explicit: Optional[str]) -> Optional[str]:
    if explicit:
        return explicit
    bundled = _discover_bundled_java(lirical_home)
    if bundled:
        return str(bundled)
    sys_java = shutil.which("java")
    return sys_java  # may be None


# -------- phenopacket projection --------


def _hpo_term_to_pf(term) -> Dict[str, Any]:
    """Project one CanonicalCase HpoTerm onto a Phenopacket phenotypicFeature."""
    pf: Dict[str, Any] = {
        "type": {"id": term.id, "label": term.label or ""},
    }
    # negated → `excluded: true` (Phenopacket v2 schema)
    if term.negated:
        pf["excluded"] = True
    if term.onset:
        pf["onset"] = {"ontologyClass": {"id": term.onset, "label": ""}}
    return pf


def case_to_phenopacket(case: CanonicalCase) -> Dict[str, Any]:
    """Build a minimal GA4GH Phenopacket JSON dict from a CanonicalCase.

    Only fields LIRICAL consults in phenotype-only mode are populated:
    subject (id, sex) + phenotypicFeatures. Age, variants, family-history,
    interpretations are intentionally omitted.
    """
    sex_map = {"male": "MALE", "female": "FEMALE", "unknown": "UNKNOWN_SEX"}
    pp: Dict[str, Any] = {
        "id": case.case_id,
        "subject": {
            "id": case.case_id,
            "sex": sex_map.get(case.demographics.sex or "unknown", "UNKNOWN_SEX"),
        },
        "phenotypicFeatures": [_hpo_term_to_pf(t) for t in case.gold_hpo_terms],
        "metaData": {
            "created": "2026-01-01T00:00:00Z",
            "createdBy": "RDAgentBenchmark.LIRICALAdapter",
            "resources": [
                {
                    "id": "hp",
                    "name": "human phenotype ontology",
                    "url": "http://purl.obolibrary.org/obo/hp.owl",
                    "version": "2024-08-13",
                    "namespacePrefix": "HP",
                    "iriPrefix": "http://purl.obolibrary.org/obo/HP_",
                }
            ],
            "phenopacketSchemaVersion": "2.0",
        },
    }
    return pp


# -------- TSV parsing --------


def _parse_tsv(tsv_path: Path) -> Tuple[List[str], List[float]]:
    """Parse a LIRICAL TSV results file.

    Header (phenotype-only):
        rank diseaseName diseaseCurie pretestprob posttestprob compositeLR
    Header (with-genotype):
        ... entrezGeneId varString

    Lines starting with '!' are metadata. Empty diseaseCurie rows are skipped.

    Returns (ranked_disease_ids, posttest_probs).
    """
    ranked: List[str] = []
    scores: List[float] = []
    header: Optional[List[str]] = None
    with tsv_path.open() as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("!"):
                continue
            cols = line.split("\t")
            if header is None and cols and cols[0] == "rank":
                header = cols
                continue
            if header is None:
                continue
            if len(cols) < len(header):
                continue
            row = dict(zip(header, cols))
            curie = row.get("diseaseCurie", "").strip()
            if not curie:
                continue
            ranked.append(curie)
            raw_p = row.get("posttestprob", "0").strip()
            try:
                # LIRICAL emits posttestprob as a percentage string like
                # '100.00000%' or '99.99843%'. Strip the '%' and divide by 100.
                # Handle locale-dependent comma decimal just in case.
                cleaned = raw_p.replace(",", ".")
                if cleaned.endswith("%"):
                    val = float(cleaned[:-1]) / 100.0
                else:
                    val = float(cleaned)
                scores.append(val)
            except ValueError:
                scores.append(0.0)
    return ranked, scores


# -------- adapter --------


class LIRICALAdapter(AgentAdapter):
    """LIRICAL phenotype-only adapter (Pillar 2 DDx baseline, no LLM)."""

    NAME = "lirical"

    def __init__(
        self,
        backbone_id: str = "non-llm/lirical-2.4.0",
        backbone_temperature: float = 0.0,
        backbone_seed: Optional[int] = None,
        agent_extra: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            backbone_id=backbone_id,
            backbone_temperature=backbone_temperature,
            backbone_seed=backbone_seed,
            agent_extra=agent_extra,
        )
        extra = self.agent_extra
        self.lirical_home = Path(
            extra.get("lirical_home")
            or os.environ.get("LIRICAL_HOME")
            or _DEFAULT_LIRICAL_HOME
        )
        self.jar = Path(
            extra.get("lirical_jar")
            or os.environ.get("LIRICAL_JAR")
            or (_discover_jar(self.lirical_home) or "")
        )
        self.data_dir = Path(
            extra.get("lirical_data")
            or os.environ.get("LIRICAL_DATA")
            or (self.lirical_home / "data")
        )
        self.java_bin = _resolve_java(
            self.lirical_home,
            extra.get("java_bin") or os.environ.get("LIRICAL_JAVA"),
        )
        self.timeout_s = int(
            extra.get("timeout_s") or os.environ.get("LIRICAL_TIMEOUT_S") or 180
        )
        self.top_k = int(
            extra.get("top_k") or os.environ.get("LIRICAL_TOP_K") or 30
        )
        self.use_orphanet = bool(extra.get("use_orphanet", False))
        self.agent_version = "lirical-cli-2.4.0"
        # FIX D3 (2026-05-15): for RareArena cases that only carry a free-text
        # vignette, do upstream LLM HPO extraction + phrase→ID normalization
        # before invoking LIRICAL. Only kicks in when eval_mode="end_to_end".
        # Cached lazily to avoid building an LLMControlAdapter for callers that
        # never need it.
        self.hpo_extractor_backbone = extra.get(
            "hpo_extractor_backbone", "openrouter/google/gemini-3-flash-preview"
        )
        self._hpo_extractor = None  # lazy LLMControlAdapter

    def _get_hpo_extractor(self):
        """Lazily build an LLMControlAdapter for free-text → HPO extraction."""
        if self._hpo_extractor is not None:
            return self._hpo_extractor
        # Local import to avoid pulling LLMControlAdapter on offline-only runs.
        from harness.agents.llm_control import LLMControlAdapter

        self._hpo_extractor = LLMControlAdapter(
            backbone_id=self.hpo_extractor_backbone,
            backbone_temperature=0.0,
        )
        return self._hpo_extractor

    def _extract_hpo_for_end_to_end(self, case: CanonicalCase) -> Tuple[List[HpoTerm], dict]:
        """Run LLM Pillar-1 extraction + phrase→HP-ID normalization.

        Returns (extracted HpoTerms with real IDs, debug dict for log.extra).
        Empty list if extraction fails or all phrases miss the fuzzy threshold.
        """
        from harness.metrics.hpo_phrase_to_id import phrase_to_hp_id

        extractor = self._get_hpo_extractor()
        try:
            phrase_terms = extractor.extract_phenotypes(case)
        except Exception as e:  # noqa: BLE001
            return [], {"hpo_extraction_error": f"{type(e).__name__}: {e}"}

        phrases = [t.label for t in phrase_terms if t.label]
        resolved: List[HpoTerm] = []
        misses: List[str] = []
        seen_ids: set[str] = set()
        for ph in phrases:
            hp_id = phrase_to_hp_id(ph)
            if hp_id is None:
                misses.append(ph)
                continue
            if hp_id in seen_ids:
                continue
            seen_ids.add(hp_id)
            resolved.append(HpoTerm(id=hp_id, label=ph))
        debug = {
            "hpo_extraction_phrases_total": len(phrases),
            "hpo_extraction_phrases_resolved": len(resolved),
            "hpo_extraction_misses_sample": misses[:5],
        }
        return resolved, debug

    # ----- install checks -----

    def _install_ok(self) -> Tuple[bool, str]:
        if not self.java_bin or not Path(self.java_bin).exists():
            return False, f"Java binary not found (looked at {self.java_bin!r})"
        if not self.jar or not self.jar.exists():
            return False, f"LIRICAL jar not found at {self.jar!r}"
        if not self.data_dir.exists():
            return False, f"LIRICAL data directory missing at {self.data_dir!r}"
        # check the bare-minimum data files we know are needed
        required = ["hp.json", "phenotype.hpoa", "hgnc_complete_set.txt", "mim2gene_medgen"]
        missing = [f for f in required if not (self.data_dir / f).exists()]
        if missing:
            return False, f"LIRICAL data dir missing files: {missing}"
        return True, ""

    # ----- main entry -----

    def predict(
        self,
        case: CanonicalCase,
        pillar: Pillar,
        eval_mode: EvalMode = "gold_hpo",
        run_id: Optional[str] = None,
    ) -> PredictionLog:
        log = self._new_log(case, pillar, eval_mode, run_id)
        log.agent_version = self.agent_version

        # FIX D3 (2026-05-15): if eval_mode="end_to_end" and the case has only
        # a free-text vignette (RareArena), upstream-extract HPO terms via LLM
        # + phrase→ID normalization, then feed those into LIRICAL. For
        # eval_mode="gold_hpo" we keep the original behaviour (empty gold →
        # status="skipped") so the existing PP-Store evaluation is unchanged.
        hpo_terms_for_lirical = case.gold_hpo_terms
        extra_debug: dict = {}
        used_e2e_extraction = False
        if (
            eval_mode == "end_to_end"
            and not case.gold_hpo_terms
            and (case.free_text_vignette or case.synthetic_vignette)
        ):
            hpo_terms_for_lirical, extra_debug = self._extract_hpo_for_end_to_end(case)
            used_e2e_extraction = True
            log.extra.update(extra_debug)

        if not hpo_terms_for_lirical:
            return self._finalize_log(
                log,
                ranked_predictions=[],
                latency_ms=0,
                status="skipped",
                error_message=(
                    "no HPO terms available (end_to_end extraction yielded none)"
                    if used_e2e_extraction
                    else "case has no gold_hpo_terms; LIRICAL requires at least 1"
                ),
            )

        if used_e2e_extraction:
            # Temporarily project the extracted terms onto the case for the
            # phenopacket builder. Build a shallow copy so we don't mutate.
            case_for_lirical = case.model_copy(
                update={"gold_hpo_terms": hpo_terms_for_lirical}
            )
            log.extracted_hpo_terms = [t.id for t in hpo_terms_for_lirical]
        else:
            case_for_lirical = case

        ok, why = self._install_ok()
        if not ok:
            return self._finalize_log(
                log,
                ranked_predictions=[],
                latency_ms=0,
                status="agent_error",
                error_message=f"LIRICAL install incomplete: {why}",
            )

        pp = case_to_phenopacket(case_for_lirical)
        with tempfile.TemporaryDirectory(prefix="lirical_") as tmp:
            tmp_path = Path(tmp)
            pp_path = tmp_path / "case.json"
            pp_path.write_text(json.dumps(pp, indent=2))
            out_dir = tmp_path / "out"
            out_dir.mkdir()

            cmd = [
                str(self.java_bin), "-jar", str(self.jar),
                "phenopacket",
                "-p", str(pp_path),
                "-d", str(self.data_dir),
                "-o", str(out_dir),
                "-f", "tsv",
                "-f", "json",
                "-x", "lirical",
                "--validation-policy", "MINIMAL",
            ]
            if self.use_orphanet:
                cmd.append("--use-orphanet")

            t0 = time.perf_counter()
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_s,
                )
            except subprocess.TimeoutExpired:
                latency_ms = int((time.perf_counter() - t0) * 1000)
                return self._finalize_log(
                    log,
                    ranked_predictions=[],
                    latency_ms=latency_ms,
                    status="timeout",
                    error_message=f"LIRICAL exceeded {self.timeout_s}s",
                )
            latency_ms = int((time.perf_counter() - t0) * 1000)

            if proc.returncode != 0:
                excerpt = (proc.stderr or proc.stdout or "")[-1500:]
                return self._finalize_log(
                    log,
                    ranked_predictions=[],
                    latency_ms=latency_ms,
                    status="agent_error",
                    error_message=f"LIRICAL exit {proc.returncode}: {excerpt}",
                    raw_response_excerpt=excerpt,
                )

            tsv_path = out_dir / "lirical.tsv"
            if not tsv_path.exists():
                excerpt = (proc.stdout or "")[-1500:]
                return self._finalize_log(
                    log,
                    ranked_predictions=[],
                    latency_ms=latency_ms,
                    status="parser_error",
                    error_message="LIRICAL produced no TSV output",
                    raw_response_excerpt=excerpt,
                )

            ranked, scores = _parse_tsv(tsv_path)
            if self.top_k > 0:
                ranked = ranked[: self.top_k]
                scores = scores[: self.top_k]

            # snippet of TSV (head) for audit
            head = "\n".join(tsv_path.read_text().splitlines()[:20])

        return self._finalize_log(
            log,
            ranked_predictions=ranked,
            confidence_scores=scores,
            latency_ms=latency_ms,
            status="ok",
            raw_response_excerpt=head,
        )


__all__ = ["LIRICALAdapter", "case_to_phenopacket"]
