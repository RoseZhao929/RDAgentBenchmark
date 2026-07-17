"""LLM no-scaffolding control adapter.

A `baseline` agent that just sends the case-as-prompt to a single LLM via
OpenRouter and parses the ranked top-5 disease list out of its free-text
response. No tool use, no retrieval, no ontology grounding -- the simplest
possible "agent" we can compare scaffolded systems against.

Why this exists:
  Per plan.md A1 ablation, every scaffolded agent (MDAgents, MedAgents,
  AgentClinic, DeepRare, RDMA, etc.) should be compared against a no-scaffolding
  control on the same backbone. This adapter is that control.

Supports:
  - Pillar 1 (extract phenotypes): ask the LLM to surface HPO-like phrases
    from a free-text vignette. Returns `HpoTerm`s with placeholder ID = the
    phrase as `label`, ID set to "HP:0000000". Downstream HPO normalization
    step is expected to resolve canonical IDs.
  - Pillar 2 (phenotype DDx): top-5 ranked candidate diagnoses.
  - Pillar 5 (reasoning communication): same as P2 but also persists the full
    reasoning prose in `reasoning_trace`.

Pillars 3 / 4 are out of scope here -- a no-scaffolding LLM can't do trio
analysis or variant ranking on its own in any meaningful way without tool use.

Unlike `MDAgentsAdapter`, this adapter does NOT need subprocess isolation:
the LLM is reached directly via `harness.logging.openrouter_wrapper`
(OpenRouter chat completions), and the cost block is auto-filled from the
provider's `usage` field.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from harness.agents._adapter_utils import (
    case_to_question,
    estimate_tokens,
    load_dotenv,
    map_names_to_ids,
    map_names_to_ids_with_variants,
    parse_ranked_top5,
)
from harness.agents.base import AgentAdapter
from harness.canonical_case import CanonicalCase, HpoTerm
from harness.logging.openrouter_wrapper import (
    fill_cost,
    timed_openrouter_chat,
)
from harness.logging.schema import EvalMode, Pillar, PredictionLog


# Stripped-down system prompt for P2: just say "you are a rare-disease expert".
# We intentionally keep it small so the comparison vs scaffolded agents is fair
# (no chain-of-thought priming, no role play).
_SYSTEM_PROMPT_P2 = (
    "You are an expert clinical geneticist specializing in rare diseases. "
    "Given clinical findings, produce a ranked differential diagnosis as a "
    "numbered list (most likely first). Each line must be exactly '1. "
    "<Disease Name>'. Use canonical Orphanet / OMIM disease names."
)

# Prompt for Pillar 1 extraction.
_SYSTEM_PROMPT_P1 = (
    "You are a clinical phenotyping assistant. Given a case description, "
    "extract every distinct clinical phenotypic finding as a short noun "
    "phrase (e.g. 'progressive proximal muscle weakness', 'optic atrophy', "
    "'macrocephaly'). Output ONLY a numbered list, one finding per line, no "
    "commentary. Do not infer diseases."
)


def _strip_or_prefix(model_id: str) -> str:
    """`openrouter/x/y` -> `x/y`. OpenRouter SDK uses the bare form."""
    if model_id.startswith("openrouter/"):
        return model_id[len("openrouter/") :]
    return model_id


class LLMControlAdapter(AgentAdapter):
    """No-scaffolding single-LLM baseline.

    Backbone is invoked directly via OpenRouter; no agent venv / subprocess.

    Args:
        backbone_id: Full OpenRouter model id, e.g.
            ``"google/gemini-3-flash-preview"``. The optional
            ``"openrouter/"`` prefix is stripped automatically.
        backbone_temperature: Forwarded to OpenRouter; default 0.0 for
            reproducibility.
        agent_extra: Recognized keys:
          - ``"max_tokens"``  -- per-call response budget (default 4000;
             reasoning models like gpt-5 need >2000 to emit any visible text).
          - ``"timeout_s"``   -- HTTP timeout, default 180.
          - ``"max_retries"`` -- network retries on transient failures
             (default 2).
    """

    NAME = "llm_control"

    def __init__(
        self,
        backbone_id: str,
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
        load_dotenv()  # populate OPENROUTER_API_KEY etc.
        self._model = _strip_or_prefix(backbone_id)
        self._max_tokens: int = int(self.agent_extra.get("max_tokens", 4000))
        self._timeout_s: int = int(self.agent_extra.get("timeout_s", 180))
        self._max_retries: int = int(self.agent_extra.get("max_retries", 2))

    # ------------------------------------------------------------------

    def supports_pillar(self, pillar: Pillar) -> bool:
        return pillar in (
            "P1_extraction",
            "P2_phenotype_ddx",
            "P3_genotype_aware",
            "P5_reasoning_communication",
        )

    # ------------------------------------------------------------------

    def _chat_with_retry(
        self, messages: List[dict]
    ) -> tuple[dict, int]:
        """Call OpenRouter with up to ``self._max_retries`` retries on
        transient network / 5xx errors. Raises the last exception on failure.

        Returns (response_json, latency_ms_total).
        """
        last_exc: Optional[Exception] = None
        total_latency_ms = 0
        for attempt in range(self._max_retries + 1):
            try:
                # 2026-05-19: propagate reasoning_effort=minimal for
                # GPT-5 / o-series (consistent with subprocess adapters).
                # Without this, GPT-5 default reasoning eats the whole
                # max_tokens budget and returns content_len=0.
                # 2026-07-03: V4-Pro reasons unbounded and ignores effort, so
                # it needs reasoning={"enabled": false}. Main matrix runs all
                # reasoning backbones OFF for cross-backbone consistency; the H6
                # thinking-mode ablation sets agent_extra={"force_reasoning_on":
                # True} to keep reasoning ON on this single-call control.
                from harness.agents._adapter_utils import (
                    reasoning_effort_for_backbone,
                    reasoning_disabled_for_backbone,
                )
                re_effort = reasoning_effort_for_backbone(self.backbone_id)
                _force_on = bool((self.agent_extra or {}).get("force_reasoning_on"))
                re_disabled = (
                    reasoning_disabled_for_backbone(self.backbone_id)
                    and not _force_on
                )
                resp, latency_ms = timed_openrouter_chat(
                    self._model,
                    messages,
                    max_tokens=self._max_tokens,
                    temperature=self.backbone_temperature,
                    timeout=self._timeout_s,
                    reasoning_effort=re_effort,
                    reasoning_disabled=re_disabled,
                )
                total_latency_ms += latency_ms
                # 2026-05-28: treat an HTTP-200 empty-content response as
                # transient and retry (some backbones, e.g. DeepSeek V4-Flash,
                # intermittently return content="" on RareBench/MIMIC). Without
                # this it surfaces as a parser_error. Reasoning models that
                # legitimately need budget are handled via reasoning_effort.
                if self._extract_content(resp).strip() or attempt == self._max_retries:
                    return resp, total_latency_ms
                time.sleep(2**attempt)
                continue
            except Exception as e:  # noqa: BLE001
                last_exc = e
                # Exponential backoff: 1s, 2s, ...
                if attempt < self._max_retries:
                    time.sleep(2**attempt)
                    continue
        assert last_exc is not None
        raise last_exc

    @staticmethod
    def _extract_content(resp: dict) -> str:
        """Pull the assistant content out of a chat-completions response.

        Some reasoning models (gpt-5) may return ``content=None`` together with
        a separate ``reasoning_details`` block when ``max_tokens`` was too low
        to allow any visible output; we surface an empty string in that case
        and let the caller decide what to do.
        """
        try:
            choice = resp["choices"][0]
        except (KeyError, IndexError, TypeError):
            return ""
        msg = choice.get("message") or {}
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            # Some providers wrap content into [{"type": "text", "text": "..."}].
            chunks: List[str] = []
            for piece in content:
                if isinstance(piece, dict) and isinstance(piece.get("text"), str):
                    chunks.append(piece["text"])
            return "\n".join(chunks)
        return ""

    # ------------------------------------------------------------------

    def predict(
        self,
        case: CanonicalCase,
        pillar: Pillar = "P2_phenotype_ddx",
        eval_mode: EvalMode = "gold_hpo",
        run_id: Optional[str] = None,
    ) -> PredictionLog:
        log = self._new_log(case, pillar, eval_mode, run_id)

        if not self.supports_pillar(pillar):
            return self._finalize_log(
                log,
                ranked_predictions=[],
                status="skipped",
                error_message=(
                    f"LLMControlAdapter does not support pillar {pillar}; "
                    "supported: P1_extraction, P2_phenotype_ddx, "
                    "P5_reasoning_communication"
                ),
            )

        if pillar == "P1_extraction":
            # Delegate; build a stub PredictionLog from extract_phenotypes' result.
            t0 = time.monotonic()
            try:
                hpo_terms = self.extract_phenotypes(case)
                latency_ms = int((time.monotonic() - t0) * 1000)
                # The cost was filled in `extract_phenotypes` via log_cost_acc;
                # but we don't pass that back here. Use a fresh cost-less log
                # for P1 -- callers who care should call extract_phenotypes()
                # directly.
                return self._finalize_log(
                    log,
                    ranked_predictions=[],
                    extracted_hpo_terms=[t.id for t in hpo_terms],
                    raw_response_excerpt=" | ".join(
                        (t.label or t.id) for t in hpo_terms
                    )[:2000],
                    latency_ms=latency_ms,
                    status="ok",
                )
            except Exception as e:  # noqa: BLE001
                return self._finalize_log(
                    log,
                    ranked_predictions=[],
                    latency_ms=int((time.monotonic() - t0) * 1000),
                    status="agent_error",
                    error_message=f"{type(e).__name__}: {e}",
                )

        # P2 / P3 / P5: ask for ranked DDx.
        question = case_to_question(case, eval_mode=eval_mode)

        # FIX 2026-05-19: P3 genotype-aware — append a structured variants block
        # so the LLM has the gene/HGVS/ACMG context. Other pillars (P2/P5) use
        # phenotype-only question as before.
        if pillar == "P3_genotype_aware" and case.variants:
            var_lines = []
            for v in case.variants[:10]:  # cap at 10 to keep prompt tight
                bits = []
                if v.gene_symbol: bits.append(f"gene={v.gene_symbol}")
                if v.hgvs_c: bits.append(f"hgvs.c={v.hgvs_c}")
                if v.hgvs_p: bits.append(f"hgvs.p={v.hgvs_p}")
                if v.acmg_classification: bits.append(f"acmg={v.acmg_classification}")
                if v.zygosity: bits.append(f"zygosity={v.zygosity}")
                if v.structural_type: bits.append(f"so={v.structural_type}")
                if bits: var_lines.append("- " + ", ".join(bits))
            if var_lines:
                question = (question +
                            "\n\nIdentified variants (structured):\n" +
                            "\n".join(var_lines))

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT_P2},
            {"role": "user", "content": question},
        ]

        try:
            resp, latency_ms = self._chat_with_retry(messages)
        except Exception as e:  # noqa: BLE001
            # Network / API failure. Best-effort cost estimate from prompt only.
            est_pt = estimate_tokens(question + _SYSTEM_PROMPT_P2)
            log.cost.prompt_tokens = est_pt
            log.cost.provider = "openrouter"
            return self._finalize_log(
                log,
                ranked_predictions=[],
                latency_ms=0,
                status="agent_error",
                error_message=f"{type(e).__name__}: {str(e)[:500]}",
            )

        content = self._extract_content(resp)
        # OpenRouter resolves preview ids to dated versions (e.g.
        # 'google/gemini-3-flash-preview' -> '...preview-20251217') which
        # misses our price table. Substitute the configured base id so the
        # cost block stays accurate.
        resolved_model_id = resp.get("model")
        resp_for_cost = dict(resp)
        resp_for_cost["model"] = self._model
        log.cost = fill_cost(resp_for_cost, log.cost)

        ranked_names = parse_ranked_top5(content, k=5)
        if not ranked_names:
            return self._finalize_log(
                log,
                ranked_predictions=[],
                raw_response_excerpt=content,
                latency_ms=latency_ms,
                status="parser_error",
                error_message=(
                    "No ranked '1. <Name>' lines found in LLM response "
                    f"(content_len={len(content)})."
                ),
            )

        ranked_ids, ranked_variants = map_names_to_ids_with_variants(ranked_names)
        log.extra["llm_control_ranked_names"] = ranked_names
        log.extra["llm_control_resolved_model"] = resolved_model_id
        log.extra["ranked_predictions_variants"] = ranked_variants

        reasoning_trace = content if pillar == "P5_reasoning_communication" else None

        return self._finalize_log(
            log,
            ranked_predictions=ranked_ids,
            reasoning_trace=reasoning_trace,
            raw_response_excerpt=content,
            latency_ms=latency_ms,
            status="ok",
        )

    # ------------------------------------------------------------------
    # Pillar 1 helper. Returns HpoTerm objects with placeholder IDs.
    # ------------------------------------------------------------------

    def extract_phenotypes(self, case: CanonicalCase) -> List[HpoTerm]:
        """Pillar 1: free-text phenotypic finding extraction.

        Sends the case's vignette to the LLM, asks for a numbered list of
        phenotypic findings, parses one phrase per line. Returns HpoTerm with:
          - id = "HP:0000000" placeholder (schema requires HP:\\d{7})
          - label = the natural-language phrase
        Downstream HPO normalization step should overwrite `id` with the real
        canonical code.
        """
        text = case.free_text_vignette or case.synthetic_vignette
        if not text:
            # Some datasets (Phenopacket-Store) have no prose, only HPO. If the
            # case already has gold HPO we don't really need to extract -- but
            # produce a sensible fallback for consistency.
            if case.gold_hpo_terms:
                return [
                    HpoTerm(id=t.id, label=t.label)
                    for t in case.gold_hpo_terms
                ]
            raise ValueError(
                f"case {case.case_id} has no free_text_vignette / "
                "synthetic_vignette to extract phenotypes from."
            )

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT_P1},
            {"role": "user", "content": text},
        ]
        resp, _ = self._chat_with_retry(messages)
        content = self._extract_content(resp)

        # Parse a numbered list -- reuse the same regex as DDx but extract up
        # to 50 entries.
        phrases: List[str] = []
        seen_lower: set[str] = set()
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            # Strip leading "1." / "1)" / "- " / "* " markers.
            import re as _re

            m = _re.match(r"^\s*(?:\d+[\.\)]|[-*•])\s*(.+)$", line)
            if not m:
                continue
            phrase = m.group(1).strip().rstrip(".;,")
            if not phrase:
                continue
            key = phrase.lower()
            if key in seen_lower:
                continue
            seen_lower.add(key)
            phrases.append(phrase)

        # Placeholder HPO ID = "HP:0000000". The schema requires a 7-digit code.
        return [HpoTerm(id="HP:0000000", label=p) for p in phrases]


__all__ = ["LLMControlAdapter"]


# ----------------------------------------------------------------------
# Smoke test entrypoint -- run a single case end-to-end.
# ----------------------------------------------------------------------

if __name__ == "__main__":
    from harness.ingest import ingest_phenopacket_store

    adapter = LLMControlAdapter(
        backbone_id="google/gemini-3-flash-preview"
    )
    case = next(
        ingest_phenopacket_store(
            "/Users/yutianzhao/Desktop/RDAgentBenchmark/data/phenopacket_store/notebooks",
            limit=1,
        )
    )
    print(
        f"[llm_control] case_id={case.case_id} hpo_n={len(case.gold_hpo_terms)}"
    )
    log = adapter.predict(case, pillar="P2_phenotype_ddx", eval_mode="gold_hpo")
    print(f"Status: {log.status}")
    print(f"Ranked: {log.ranked_predictions}")
    print(f"Names:  {log.extra.get('llm_control_ranked_names')}")
    print(
        f"Tokens: {log.cost.prompt_tokens}+{log.cost.completion_tokens} "
        f"(cost=${log.cost.cost_usd:.5f})"
    )
    print(f"Latency: {log.total_latency_ms}ms")
    if log.error_message:
        print(f"Error: {log.error_message}")
