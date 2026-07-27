"""MDAgents harness adapter.

MDAgents is an MCQA-style multi-agent collaboration framework (recruiter +
experts + moderator). For rare-disease DDx we drive it via its `basic` /
`intermediate` paths with a free-text question (no MCQ options) — see
`tasks/stream_E_agent_scouting/agents/mdagents_RUN_REPORT.md` for the
patches applied to its `utils.py` / `main.py`.

This shim:
1. Projects a CanonicalCase to MDAgents' expected `sample['question']` schema.
2. Writes a one-line `test.jsonl` into a temporary data dir.
3. Calls `agents/mdagents/.venv/bin/python main.py --dataset <tmpname> ...`
   as a subprocess (the agent's venv has openai==1.x, the harness venv may
   have older / newer SDKs — keep them separated).
4. Parses the resulting JSON output, pulls the moderator's free-text top-5,
   regex-extracts ranked names, maps to ORPHA IDs.
5. Returns a fully-populated PredictionLog.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import List, Optional

from harness.agents._adapter_utils import (
    PROJECT_ROOT,
    case_to_question,
    estimate_tokens,
    fill_cost_from_tokens,
    load_dotenv,
    map_names_to_ids,
    map_names_to_ids_with_variants,
    parse_ranked_top5,
    reasoning_disabled_for_backbone,
    reasoning_effort_for_backbone,
    resolve_llm_gateway,
)
from harness.agents.base import AgentAdapter
from harness.canonical_case import CanonicalCase
from harness.logging.schema import CostBreakdown, EvalMode, Pillar, PredictionLog


MDAGENTS_ROOT = PROJECT_ROOT / "agents" / "mdagents"
MDAGENTS_PY = MDAGENTS_ROOT / ".venv" / "bin" / "python"
MDAGENTS_MAIN = MDAGENTS_ROOT / "main.py"


class MDAgentsAdapter(AgentAdapter):
    """MDAgents shim. Pillar 2 (phenotype-only DDx) primary. Optional P5."""

    NAME = "mdagents"

    def __init__(
        self,
        backbone_id: str = "openrouter/google/gemini-3-flash-preview",
        backbone_temperature: float = 0.0,
        backbone_seed: Optional[int] = None,
        agent_extra: Optional[dict] = None,
    ):
        super().__init__(
            backbone_id=backbone_id,
            backbone_temperature=backbone_temperature,
            backbone_seed=backbone_seed,
            agent_extra=agent_extra,
        )
        load_dotenv()  # populate OPENROUTER_API_KEY etc.
        # MDAgents accepts model id as-is on CLI (after our patch); strip the
        # 'openrouter/' prefix because OpenRouter's own SDK uses the bare
        # 'google/gemini-3-flash-preview' id.
        if backbone_id.startswith("openrouter/"):
            self._model_cli = backbone_id[len("openrouter/"):]
        else:
            self._model_cli = backbone_id
        self._difficulty = (self.agent_extra or {}).get("difficulty", "basic")
        self._timeout_s = int((self.agent_extra or {}).get("timeout_s", 300))

    def supports_pillar(self, pillar: Pillar) -> bool:
        return pillar in ("P2_phenotype_ddx", "P5_reasoning_communication")

    # --------------------------------------------------------------

    def _run_mdagents_subprocess(
        self, question: str, run_id: str
    ) -> tuple[dict, str, int]:
        """Drive MDAgents end-to-end on a one-case dataset.

        Returns (parsed_output_record, stdout_excerpt, latency_ms).
        Raises CalledProcessError / TimeoutExpired on failure (caller handles).
        """
        if not MDAGENTS_PY.exists():
            raise FileNotFoundError(
                f"MDAgents venv python not found at {MDAGENTS_PY} — "
                "did you run the scouting install?"
            )

        # Build a one-record dataset under MDAgents' data root.
        # Avoid colliding with the existing `raredx_smoke` dataset by using
        # a unique dataset name keyed off the run_id.
        ds_name = f"harness_{run_id[:8]}_{uuid.uuid4().hex[:6]}"
        ds_dir = MDAGENTS_ROOT / "data" / ds_name
        ds_dir.mkdir(parents=True, exist_ok=True)
        try:
            (ds_dir / "test.jsonl").write_text(
                json.dumps({"question": question}) + "\n", encoding="utf-8"
            )

            env = os.environ.copy()
            # Wire backbone via env (MDAgents reads lowercase `openai_api_key`).
            sdk_base, api_key = resolve_llm_gateway()
            env["OPENAI_BASE_URL"] = sdk_base
            env["openai_api_key"] = api_key
            env["OPENAI_API_KEY"] = api_key
            env["MDAGENTS_MODEL"] = self._model_cli
            env["PYTHONUNBUFFERED"] = "1"
            # 2026-05-19 — propagate reasoning_effort=minimal for GPT-5 / o-series.
            # mdagents was the only adapter that passed P2 with GPT-5 (50/50),
            # but only because its max_tokens budget happened to be large
            # enough. Add this defensively so GPT-5 stays cheap and stable.
            re_effort = reasoning_effort_for_backbone(self.backbone_id)
            if re_effort:
                env["OPENROUTER_REASONING_EFFORT"] = re_effort
            # 2026-07-03 — V4-Pro reasons unbounded (15-32s/call); across the
            # 7-10 debate calls this blows the timeout cap. Disable reasoning
            # (reasoning={"enabled": false}) → ~1.9s/call, consistent with the
            # reasoning-off config used for GPT-5.
            if reasoning_disabled_for_backbone(self.backbone_id):
                env["OPENROUTER_REASONING_DISABLE"] = "1"

            cmd = [
                str(MDAGENTS_PY),
                str(MDAGENTS_MAIN),
                "--dataset",
                ds_name,
                "--model",
                self._model_cli,
                "--difficulty",
                self._difficulty,
                "--num_samples",
                "1",
            ]
            t0 = time.time()
            proc = subprocess.run(
                cmd,
                cwd=str(MDAGENTS_ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=self._timeout_s,
            )
            latency_ms = int((time.time() - t0) * 1000)
            if proc.returncode != 0:
                stderr_tail = proc.stderr[-1500:] if proc.stderr else ""
                raise RuntimeError(
                    f"mdagents main.py exited {proc.returncode}: {stderr_tail}"
                )

            # Output file naming: '{safe_model}_{dataset}_{difficulty}.json'
            safe_model = self._model_cli.replace("/", "__")
            out_path = (
                MDAGENTS_ROOT
                / "output"
                / f"{safe_model}_{ds_name}_{self._difficulty}.json"
            )
            if not out_path.exists():
                raise FileNotFoundError(
                    f"mdagents output file missing: {out_path}\n"
                    f"stdout tail: {proc.stdout[-800:]}"
                )
            data = json.loads(out_path.read_text())
            if not isinstance(data, list) or not data:
                raise RuntimeError(f"mdagents output empty/wrong shape: {data!r}")
            record = data[0]
            stdout_excerpt = proc.stdout[-2000:]
            return record, stdout_excerpt, latency_ms
        finally:
            shutil.rmtree(ds_dir, ignore_errors=True)

    @staticmethod
    def _extract_final_text(record: dict) -> str:
        """Pull the moderator's / single-agent's final free-text answer.

        Output shape after main.py:
        - basic / intermediate: `response` is a dict {temperature_str: text}.
        - advanced: `response` is `final_decision` (a dict with 'majority').

        Returns the longest text payload as a robust default.
        """
        resp = record.get("response")
        if isinstance(resp, str):
            return resp
        if isinstance(resp, dict):
            # intermediate path may yield {'majority': {'0.0': '...'}}
            majority = resp.get("majority")
            if isinstance(majority, dict):
                texts = [v for v in majority.values() if isinstance(v, str)]
                if texts:
                    return max(texts, key=len)
            if isinstance(majority, str):
                return majority
            # basic path: {'0.0': '...'}
            texts = [v for v in resp.values() if isinstance(v, str)]
            if texts:
                return max(texts, key=len)
        return json.dumps(resp)[:2000] if resp else ""

    # --------------------------------------------------------------

    def predict(
        self,
        case: CanonicalCase,
        pillar: Pillar,
        eval_mode: EvalMode = "gold_hpo",
        run_id: Optional[str] = None,
    ) -> PredictionLog:
        log = self._new_log(case, pillar, eval_mode, run_id)
        question = case_to_question(case, eval_mode=eval_mode)

        try:
            record, stdout_excerpt, latency_ms = self._run_mdagents_subprocess(
                question, log.run_id
            )
        except subprocess.TimeoutExpired:
            return self._finalize_log(
                log,
                ranked_predictions=[],
                latency_ms=self._timeout_s * 1000,
                status="timeout",
                error_message=f"mdagents subprocess exceeded {self._timeout_s}s",
            )
        except Exception as e:  # noqa: BLE001 — wrap any agent-side failure
            return self._finalize_log(
                log,
                ranked_predictions=[],
                latency_ms=0,
                status="agent_error",
                error_message=f"{type(e).__name__}: {e}",
            )

        final_text = self._extract_final_text(record)
        ranked_names = parse_ranked_top5(final_text, k=5)
        # FIX 2026-05-19 — noise filter (B-C bug audit of DeepSeek -10pp gap).
        # mdagents on DeepSeek V3.2 occasionally surfaces phenotype mentions
        # ("Elevated PTH", "Structural Brain Abnormality") in the ranked top-N.
        # Drop them before downstream ID mapping. Same pattern as maidxo
        # _NOISE_PATTERNS. We log the drops on `log.extra` for audit.
        if ranked_names:
            from harness.agents.maidxo import _is_noise_candidate
            kept, dropped = [], []
            for n in ranked_names:
                if _is_noise_candidate(n):
                    dropped.append(n)
                else:
                    kept.append(n)
            if dropped:
                log.extra["mdagents_noise_filtered"] = dropped
            ranked_names = kept
        if not ranked_names:
            return self._finalize_log(
                log,
                ranked_predictions=[],
                reasoning_trace=record.get("difficulty"),
                raw_response_excerpt=final_text,
                latency_ms=latency_ms,
                status="parser_error",
                error_message="No ranked '1. <Name>' lines found in mdagents output.",
            )

        ranked_ids, ranked_variants = map_names_to_ids_with_variants(ranked_names)
        log.extra["ranked_predictions_variants"] = ranked_variants

        # Cost: MDAgents doesn't surface OpenAI usage in its JSON output. Use
        # token-count heuristics on the prompt + final answer as a floor.
        prompt_tok = estimate_tokens(question)
        completion_tok = estimate_tokens(final_text)
        cost = CostBreakdown(
            prompt_tokens=prompt_tok,
            completion_tokens=completion_tok,
            provider="openrouter",
        )
        log.cost = cost
        # FIX D2 (2026-05-15): compute cost_usd from backbone price table.
        fill_cost_from_tokens(log.cost, self.backbone_id)
        log.extra["mdagents_difficulty"] = record.get("difficulty")
        log.extra["mdagents_ranked_names"] = ranked_names

        # FIX P5-2 (2026-05-15): build a richer reasoning_trace for the LLM
        # judge. The 'basic' path is a single agent, so we use the model's
        # answer text. The 'intermediate' path now (after upstream utils.py
        # patch) returns {'majority': ..., 'debate': {...}} — surface the
        # recruiter recruit list, initial expert opinions, per-round opinions,
        # each expert's final answer, then moderator majority. The 'advanced'
        # path keeps the JSON dump fallback.
        reasoning_trace = None
        difficulty = record.get("difficulty")
        resp = record.get("response")
        if difficulty == "intermediate" and isinstance(resp, dict):
            debate = resp.get("debate") if isinstance(resp.get("debate"), dict) else {}
            chunks: List[str] = []
            recruited = debate.get("recruited")
            if recruited:
                chunks.append("=== Step 1. Recruited experts ===\n" + str(recruited))
            init_rep = debate.get("initial_report")
            if init_rep:
                chunks.append("=== Step 2.1. Initial individual opinions ===\n" + str(init_rep))
            round_opinions = debate.get("round_opinions") or {}
            for rn in sorted(round_opinions.keys()):
                ops = round_opinions[rn]
                if not ops:
                    continue
                rendered = "\n".join(f"({role}): {opin}" for role, opin in ops.items())
                chunks.append(f"=== Round {rn} opinions ===\n{rendered}")
            final_ans = debate.get("final_answer") or {}
            if final_ans:
                rendered = "\n".join(f"({role}): {ans}" for role, ans in final_ans.items())
                chunks.append("=== Step 2.2. Each expert's final answer ===\n" + rendered)
            if final_text:
                chunks.append("=== Step 3. Moderator majority verdict ===\n" + final_text)
            reasoning_trace = "\n\n".join(chunks) if chunks else None
        elif difficulty == "advanced":
            try:
                reasoning_trace = json.dumps(resp)[:16000]
            except Exception:
                reasoning_trace = None
        elif difficulty == "basic":
            # Basic path is a single LLM call — surface the answer text as
            # the trace so P5 still gets graded (otherwise trace is empty).
            reasoning_trace = final_text or None

        return self._finalize_log(
            log,
            ranked_predictions=ranked_ids,
            reasoning_trace=reasoning_trace,
            raw_response_excerpt=final_text,
            latency_ms=latency_ms,
            status="ok",
        )


__all__ = ["MDAgentsAdapter"]


if __name__ == "__main__":
    from harness.ingest import ingest_rarebench

    adapter = MDAgentsAdapter(
        backbone_id="openrouter/google/gemini-3-flash-preview"
    )
    case = next(
        ingest_rarebench(
            "data/rarebench_hf/data_unzipped/data/RAMEDIS.jsonl",
            "RAMEDIS",
            limit=1,
        )
    )
    print(f"[mdagents] case_id={case.case_id} hpo_n={len(case.gold_hpo_terms)}")
    log = adapter.predict(case, pillar="P2_phenotype_ddx", eval_mode="gold_hpo")
    print(f"Status: {log.status}")
    print(f"Ranked predictions: {log.ranked_predictions[:5]}")
    print(f"Ranked names: {log.extra.get('mdagents_ranked_names')}")
    print(
        f"Tokens: {log.cost.prompt_tokens}+{log.cost.completion_tokens} "
        f"({log.cost.provider})"
    )
    print(f"Latency: {log.total_latency_ms}ms")
    if log.error_message:
        print(f"Error: {log.error_message}")
