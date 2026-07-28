"""Phase 4a Mini-Sample runner — 100 case × 4 dataset × adapters × backbones.

Per round2_plan §6.2:
- Phenopacket-Store 100 (seed=42)
- RareArena RDS 100 (seed=42)
- RareBench HF 100 stratified across RAMEDIS/LIRICAL/MME/HMS (25 each)
- MIMIC-IV diverse 100

Adapters: configurable (default 7: mdagents/medagents/agentclinic/maidxo/
deeprare/llm_control/vc_rdagent). LIRICAL only on PP-Store (classical, HPO).
RDMA is P1-only.

Backbones: configurable (default 3: Gemini Flash, DeepSeek V4-Pro, GPT-5 minimal).

Known agent×backbone failure modes (scored honestly, NOT skipped):
- MAI-DxO × GPT-5: structured-output protocol collapse under GPT-5-minimal
  (prompt-placeholder echo → vitals-fragment scraping). No timeout on the
  mimic_note probe (416/416, median ~78s). Scored as very-low R@1.
- DeepRare × GPT-5: parser fallback partial (empty diseases → relaxed parse).
See the INCOMPAT set below (now empty; matcher compares the full backbone id).

Output: data/round2/phase4a/predictions_<dataset>_<adapter>_<backbone>.jsonl
"""

from __future__ import annotations

import argparse, json, os, random, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def load_env(env_path: Path = Path(".env")) -> None:
    if not env_path.exists(): return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def load_phenopacket_store(n=100, seed=42):
    from harness.ingest import ingest_phenopacket_store
    cases = list(ingest_phenopacket_store("data/phenopacket_store/notebooks"))
    rng = random.Random(seed)
    rng.shuffle(cases)
    return cases[:n]


def load_rarearena_rds(n=100, seed=42):
    from harness.ingest import ingest_rarearena
    cases = list(ingest_rarearena("data/rarearena/benchmark_data/RDS_benchmark.jsonl", "RDS"))
    rng = random.Random(seed)
    rng.shuffle(cases)
    return cases[:n]


def load_rarebench_stratified(n=100, seed=42, n_per_split=None):
    """Load an exact-size, prefix-stable stratified RareBench cohort.

    The legacy N=100 cohort shuffled each of the four splits with seed 42 and
    took 25 from each. Preserve that exact case set, but interleave the split
    buckets so N=2 and N=10 are balanced prefixes of the same N=100 cohort.
    ``n_per_split`` remains for audit callers that need the legacy grouped
    ordering.
    """
    from harness.ingest import ingest_rarebench
    buckets = []
    width = n_per_split if n_per_split is not None else max(25, (n + 3) // 4)
    for split in ("RAMEDIS", "LIRICAL", "MME", "HMS"):
        cases = list(ingest_rarebench(f"data/rarebench_hf/data_unzipped/data/{split}.jsonl", split))
        rng = random.Random(seed)
        rng.shuffle(cases)
        buckets.append(cases[:width])
    if n_per_split is not None:
        return [case for bucket in buckets for case in bucket]
    interleaved = []
    for index in range(width):
        for bucket in buckets:
            if index < len(bucket):
                interleaved.append(bucket[index])
    return interleaved[:n]


def load_mimic_diverse(n=100):
    from harness.canonical_case import CanonicalCase
    out = []
    with open("data/mimic_iv_rd_slice/cases_filtered_diverse.jsonl") as f:
        for line in f:
            try:
                out.append(CanonicalCase.model_validate_json(line))
            except Exception:
                continue
            if len(out) >= n: break
    return out


def load_mimic_note_hpo_line(n=416):
    """De-leaked MIMIC-IV-Note strict-A HPO line (416 cases / 68 diseases).

    Distinct from the old `mimic_diverse` (leaked ICD-title input, now removed).
    Input = discharge-summary presentation span (gold name + synonyms masked);
    gold = code-derived ORPHA (evaluation_only). See
    audit_frozen/mimic_note_experiment/. Free-text only (no case-level HPO), so
    the HPO-only agents (vc_rdagent / lirical) are auto-skipped by the runner.

    model_input      -> free_text_vignette  (agents read this via case_to_question)
    evaluation_only  -> gold_label {orphanet_id, disease_name}
    demographics.sex -> sex  (age is ADMISSION age, not onset -> deliberately dropped)
    """
    from harness.canonical_case import CanonicalCase
    path = "data/mimic_iv_rd_slice/note_eval_hpo_line_v1.jsonl"
    out = []
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            ev = r["evaluation_only"]
            sex = (r.get("demographics") or {}).get("sex")
            if sex not in ("male", "female", "unknown"):
                sex = None
            case = CanonicalCase(
                case_id=r["case_id"],
                source_dataset="mimic_iv_rd",
                source_split="note_strict_A_hpo_line",
                free_text_vignette=r["model_input"],
                demographics={"sex": sex} if sex else {},
                gold_label={
                    "orphanet_id": ev["gold_orpha"],
                    "disease_name": ev["gold_disease"],
                },
            )
            out.append(case)
            if len(out) >= n:
                break
    return out


def load_mimic_note_leaked_416(n=416):
    """BEFORE-de-leak baseline: same 416 case_ids as the de-leaked probe, but
    the FULL note (no truncation, no gold-name masking) as input.

    Pairs 1:1 with load_mimic_note_hpo_line so before/after is a true same-case
    comparison. Built by `build_mimic_note_deleaked.py --leaked --restrict-to
    note_eval_hpo_line_v1.jsonl` → note_leaked_v1_416.jsonl. Same record schema
    as the de-leaked file, so the mapping below is identical.
    """
    from harness.canonical_case import CanonicalCase
    path = "data/mimic_iv_rd_slice/note_leaked_v1_416.jsonl"
    out = []
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            ev = r["evaluation_only"]
            sex = (r.get("demographics") or {}).get("sex")
            if sex not in ("male", "female", "unknown"):
                sex = None
            case = CanonicalCase(
                case_id=r["case_id"],
                source_dataset="mimic_iv_rd",
                source_split="note_leaked_v1_416",
                free_text_vignette=r["model_input"],
                demographics={"sex": sex} if sex else {},
                gold_label={
                    "orphanet_id": ev["gold_orpha"],
                    "disease_name": ev["gold_disease"],
                },
            )
            out.append(case)
            if len(out) >= n:
                break
    return out


def load_pmc_holdout(n=1000):
    # Post-cutoff (2024+) PMC-OA holdout; gold from Opus-4.8 agent annotation
    # (stand-in physician gold, §9 L5 / A5). Bias-free reference for H3.
    from harness.canonical_case import CanonicalCase
    out = []
    with open("data/pmc_oa_holdout/holdout_gold_opus.jsonl") as f:
        for line in f:
            try:
                out.append(CanonicalCase.model_validate_json(line))
            except Exception:
                continue
            if len(out) >= n:
                break
    return out


def load_pmc_precutoff(n=1000):
    from harness.canonical_case import CanonicalCase
    out = []
    with open("data/pmc_precutoff/holdout_gold_opus.jsonl") as f:
        for line in f:
            try:
                out.append(CanonicalCase.model_validate_json(line))
            except Exception:
                continue
            if len(out) >= n:
                break
    return out


DATASETS = {
    "phenopacket_store": load_phenopacket_store,
    "rarearena_rds":     load_rarearena_rds,
    "rarebench":         load_rarebench_stratified,
    "mimic_diverse":     load_mimic_diverse,
    "mimic_note":        load_mimic_note_hpo_line,
    "mimic_note_leaked": load_mimic_note_leaked_416,
    "pmc_oa_holdout":    load_pmc_holdout,
    "pmc_precutoff":     load_pmc_precutoff,
}


def get_adapter(name: str, backbone_id: str, timeout_s: int | None = None,
                reasoning_on: bool = False):
    from harness.agents import (
        AgentClinicAdapter, DeepRareAdapter, LIRICALAdapter, LLMControlAdapter,
        MDAgentsAdapter, MaiDxOAdapter, MedAgentsAdapter, RDMAAdapter,
        VCRDAgentAdapter,
    )
    # timeout_s override (2026-05-28): empty-content retries + slow synth on
    # RareBench/MIMIC can exceed the default 300s subprocess cap (A9: a
    # medagents V4-Flash case completed in 309s). Allow per-run override.
    to = {"timeout_s": timeout_s} if timeout_s else {}
    # reasoning_on (2026-07-03): H6 thinking-mode ablation. Only meaningful for
    # llm_control on a reasoning backbone (V4-Pro); forces reasoning ON where
    # the main matrix runs it OFF. See harness/agents/llm_control.py.
    if name == "mdagents":    return MDAgentsAdapter(backbone_id=backbone_id, agent_extra=to or None)
    if name == "medagents":   return MedAgentsAdapter(backbone_id=backbone_id, agent_extra=to or None)
    if name == "agentclinic": return AgentClinicAdapter(backbone_id=backbone_id, agent_extra=to or None)
    if name == "maidxo":      return MaiDxOAdapter(backbone_id=backbone_id, agent_extra={"mode": "no_budget", "max_iterations": 3, **({"timeout_seconds": timeout_s} if timeout_s else {})})
    if name == "deeprare":    return DeepRareAdapter(backbone_id=backbone_id)
    if name == "llm_control":
        extra = dict(to)
        if reasoning_on:
            extra["force_reasoning_on"] = True
        return LLMControlAdapter(backbone_id=backbone_id, agent_extra=extra or None)
    if name == "vc_rdagent":  return VCRDAgentAdapter(backbone_id="vc_rdagent-offline-v1")
    if name == "lirical":     return LIRICALAdapter(backbone_id="lirical-2.4.0")
    raise ValueError(name)


# Known agent×backbone incompatibilities to auto-skip. Keys are (agent,
# "provider/model") — the FULL canonical backbone id, matched exactly.
#
# 2026-07-26: emptied. The earlier ("maidxo", "openai/gpt-5") entry was BOTH
#   (a) never actually firing — the matcher below only ever compared split
#       fragments ("gpt-5" / "openai"), never the full "openai/gpt-5" string,
#       so the entry silently no-op'd; and
#   (b) mis-motivated — on the mimic_note probe via the litellm gateway,
#       maidxo×gpt-5 does NOT time out (416/416 complete, median 78s, 0 over
#       600s). Its real failure mode is structured-output PROTOCOL COLLAPSE
#       (GPT-5-minimal echoes the "[detailed reasoning...]" prompt placeholder
#       ~380/416 and the panel scrapes vitals fragments as the "diagnosis").
#       That is a genuine framework×backbone finding, so it is now scored
#       honestly (very low R@1) rather than hidden as N/A.
# The matcher is fixed to compare the full id, so future TRUE incompats work.
INCOMPAT: set[tuple[str, str]] = set()

# vc_rdagent Stage 1 is HPO-input-only (no NLP extraction step). Skip datasets
# that don't supply structured HPO terms in CanonicalCase.gold_hpo_terms.
NO_HPO_DATASETS = {"rarearena_rds", "mimic_diverse", "mimic_note", "mimic_note_leaked"}
HPO_ONLY_AGENTS = {"vc_rdagent", "lirical"}


def run(
    dataset,
    agent,
    backbone,
    n,
    out_path,
    timeout_s=None,
    reasoning_on=False,
    concurrency=1,
    resume_statuses=("ok", "skipped"),
    max_attempts_per_case=None,
    cohort_n=None,
):
    load_env()
    print(f"[p4a] dataset={dataset} agent={agent} backbone={backbone} n={n}"
          f"{' reasoning_ON' if reasoning_on else ''} concurrency={concurrency}", flush=True)
    if (agent, backbone) in INCOMPAT:
        print(f"  → known incompat,skip", flush=True)
        return
    # vc_rdagent / lirical require HPO input — skip on free-text datasets
    if agent in HPO_ONLY_AGENTS and dataset in NO_HPO_DATASETS:
        print(f"  → {agent} requires HPO input; {dataset} has none, skip", flush=True)
        return
    if cohort_n is not None:
        # 2026-07-28: split a fixed cohort front/back so two operators can fill
        # the same N=cohort_n cell without overlapping. The loaders are
        # seed-stable prefixes, so cohort[cohort_n-n:cohort_n] is disjoint from
        # the cohort[:cohort_n-n] prefix another run is already covering.
        cases = DATASETS[dataset](n=cohort_n)[-n:]
    else:
        cases = DATASETS[dataset](n=n)
    print(f"  loaded {len(cases)} cases", flush=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    from harness.logging import JsonlPredictionLogger
    from harness.metrics.cross_map import gold_hit_with_crossmap

    # 2026-05-21 RESUME mode: if out_path already exists, skip case_ids
    # that are already in it. Enables N=100 → N=500 scaling without
    # re-running cases 0-99.
    already_done = set()
    attempt_counts = {}
    if out_path.exists():
        with out_path.open() as f:
            for line in f:
                try:
                    r = json.loads(line)
                    case_id = r.get("case_id")
                    if case_id is not None:
                        attempt_counts[case_id] = attempt_counts.get(case_id, 0) + 1
                    if r.get("status") in resume_statuses:
                        already_done.add(case_id)
                except Exception:
                    continue
        if max_attempts_per_case is not None:
            already_done.update(
                case_id
                for case_id, attempts in attempt_counts.items()
                if attempts >= max_attempts_per_case
            )
        print(f"  RESUME: {len(already_done)} cases already done in {out_path.name}", flush=True)

    logger = JsonlPredictionLogger(out_path)
    adapter = get_adapter(agent, backbone, timeout_s=timeout_s, reasoning_on=reasoning_on)

    run_id = f"p4a_{dataset}_{agent}_{int(time.time())}"
    from threading import Lock
    lock = Lock()
    st = {"hits": 0, "ok": 0, "total": 0}
    todo = [(i, c) for i, c in enumerate(cases, 1) if c.case_id not in already_done]
    ntodo = len(todo)

    def work(item):
        # Cases are independent; subprocess adapters use a unique temp/output dir
        # per predict() call (thread-safe). Only the shared logger + counters are
        # guarded by `lock`.
        i, case = item
        try:
            log = adapter.predict(case, pillar="P2_phenotype_ddx", eval_mode="gold_hpo", run_id=run_id)
        except Exception as e:
            # Never let a top-level adapter exception disappear from the
            # attempted-denominator audit trail.  A missing row is ambiguous
            # (not launched vs. crashed) and prevents the supervisor from
            # applying a bounded retry policy.
            failure_log = adapter._new_log(
                case, "P2_phenotype_ddx", "gold_hpo", run_id
            )
            failure_log = adapter._finalize_log(
                failure_log,
                ranked_predictions=[],
                status="agent_error",
                error_message=(
                    f"phase4a runner caught {type(e).__name__}: {str(e)[:1000]}"
                ),
            )
            with lock:
                logger.write(failure_log)
                st["total"] += 1
                if st["total"] % 10 == 0:
                    print(f"  [{st['total']}/{ntodo}] EXC: {type(e).__name__}: {str(e)[:80]}", flush=True)
            return
        with lock:
            logger.write(log)
            st["total"] += 1
            if log.status == "ok":
                st["ok"] += 1
                if log.ranked_predictions and case.gold_label and gold_hit_with_crossmap(log.ranked_predictions[0], case.gold_label):
                    st["hits"] += 1
            if st["total"] % 10 == 0 or st["total"] == ntodo:
                print(f"  [{st['total']}/{ntodo}] ok={st['ok']} R@1={st['hits']}/{st['ok']}", flush=True)

    if concurrency <= 1:
        for item in todo:
            work(item)
    else:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            list(ex.map(work, todo))
    print(f"[p4a] DONE: {st['ok']}/{st['total']} ok, R@1={st['hits']}", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", required=True, choices=list(DATASETS.keys()))
    p.add_argument("--agent", required=True)
    p.add_argument("--backbone", required=True)
    p.add_argument("--n", type=int, default=100)
    p.add_argument("--out", required=True)
    p.add_argument("--reasoning_on", action="store_true",
                   help="H6 ablation: force reasoning ON (llm_control + reasoning backbone)")
    p.add_argument("--timeout_s", type=int, default=None,
                   help="override subprocess/call timeout (default per-adapter)")
    p.add_argument("--concurrency", type=int, default=1,
                   help="process N cases in parallel via a thread pool (cases are "
                        "independent; I/O-bound on LLM/subprocess). Default 1 = serial.")
    p.add_argument(
        "--resume-statuses",
        default="ok,skipped",
        help=(
            "comma-separated receipt statuses treated as terminal on resume "
            "(default: ok,skipped). For attempted-denominator pilots, include "
            "parser_error to avoid repeating a completed but unparseable call."
        ),
    )
    p.add_argument(
        "--max-attempts-per-case",
        type=int,
        default=None,
        help="optional retry ceiling across resumed receipts for each case_id",
    )
    p.add_argument(
        "--cohort-n",
        type=int,
        default=None,
        help=(
            "take the LAST --n cases of the seed-stable --cohort-n cohort "
            "instead of the first --n. Lets a second operator fill the tail of "
            "a cell while the head is being run elsewhere."
        ),
    )
    args = p.parse_args()
    resume_statuses = tuple(
        status.strip() for status in args.resume_statuses.split(",") if status.strip()
    )
    run(args.dataset, args.agent, args.backbone, args.n, Path(args.out),
        timeout_s=args.timeout_s, reasoning_on=args.reasoning_on,
        concurrency=args.concurrency, resume_statuses=resume_statuses,
        max_attempts_per_case=args.max_attempts_per_case,
        cohort_n=args.cohort_n)
