"""Adapter base class — common interface all agent shims implement.

Each concrete adapter (e.g., `MDAgentsAdapter`, `DeepRareAdapter`) implements:
- `predict(case, pillar) -> PredictionLog`: main DDx output
- optional `extract_phenotypes(case) -> List[HpoTerm]`: Pillar 1 capability
- optional `supports_pillar(pillar) -> bool`: declares which pillars work

Backbone is passed at construction time (e.g., "openrouter/google/gemini-3-flash-preview").
The adapter is responsible for wiring its agent to use this backbone.

The caller persists returned PredictionLog via `JsonlPredictionLogger`.
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from harness.canonical_case import CanonicalCase, HpoTerm
from harness.logging.schema import EvalMode, Pillar, PredictionLog


class AgentAdapter(ABC):
    """All concrete adapters subclass this.

    Subclass MUST set:
    - NAME: short string id (e.g., "deeprare", "mdagents")

    Subclass MUST implement:
    - predict(case, pillar, ...)

    Subclass MAY override:
    - supports_pillar(pillar)
    - extract_phenotypes(case)
    """

    NAME: str = ""

    def __init__(
        self,
        backbone_id: str,
        backbone_temperature: float = 0.0,
        backbone_seed: Optional[int] = None,
        agent_extra: Optional[Dict[str, Any]] = None,
    ):
        if not self.NAME:
            raise NotImplementedError(
                f"{type(self).__name__} must set NAME class var (short agent id)"
            )
        self.backbone_id = backbone_id
        self.backbone_temperature = backbone_temperature
        self.backbone_seed = backbone_seed
        self.agent_extra = agent_extra or {}

    @abstractmethod
    def predict(
        self,
        case: CanonicalCase,
        pillar: Pillar,
        eval_mode: EvalMode = "gold_hpo",
        run_id: Optional[str] = None,
    ) -> PredictionLog:
        """Run the agent on one case for one pillar.

        Returns a fully-populated PredictionLog (ranked_predictions, cost,
        latency, status, etc.). Caller persists.
        """

    def supports_pillar(self, pillar: Pillar) -> bool:
        """Whether this adapter handles the given pillar.

        Default: only Pillar 2 (phenotype-only DDx). Override for richer agents.
        """
        return pillar == "P2_phenotype_ddx"

    def extract_phenotypes(self, case: CanonicalCase) -> List[HpoTerm]:
        """Pillar 1 capability. Default: not implemented.

        Override in adapters whose agent does HPO extraction (e.g., RDMA, DeepRare).
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not implement Pillar 1 extraction"
        )

    # ---------- helpers for subclasses ----------

    def _new_log(
        self,
        case: CanonicalCase,
        pillar: Pillar,
        eval_mode: EvalMode,
        run_id: Optional[str],
    ) -> PredictionLog:
        """Construct an initial PredictionLog with identity fields filled."""
        return PredictionLog(
            run_id=run_id or str(uuid.uuid4()),
            agent_id=self.NAME,
            backbone_id=self.backbone_id,
            backbone_temperature=self.backbone_temperature,
            backbone_seed=self.backbone_seed,
            case_id=case.case_id,
            source_dataset=case.source_dataset,
            source_split=case.source_split,
            pillar=pillar,
            eval_mode=eval_mode,
        )

    def _finalize_log(
        self,
        log: PredictionLog,
        ranked_predictions: List[str],
        *,
        confidence_scores: Optional[List[float]] = None,
        extracted_hpo_terms: Optional[List[str]] = None,
        reasoning_trace: Optional[str] = None,
        citations: Optional[List[str]] = None,
        raw_response_excerpt: Optional[str] = None,
        latency_ms: int = 0,
        status: str = "ok",
        error_message: Optional[str] = None,
    ) -> PredictionLog:
        log.ranked_predictions = ranked_predictions
        if confidence_scores is not None:
            log.confidence_scores = confidence_scores
        elif ranked_predictions:
            # FIX B3 (2026-05-15): default rank-decreasing placeholder so Brier /
            # ECE / Confidence-AUROC can compute SOMETHING even before adapters
            # surface real LLM logprob. Adapters that want true confidence
            # should pass `confidence_scores` explicitly (overrides this).
            log.confidence_scores = [1.0 / (i + 1) for i in range(len(ranked_predictions))]
        if extracted_hpo_terms is not None:
            log.extracted_hpo_terms = extracted_hpo_terms
        if reasoning_trace is not None:
            log.reasoning_trace = reasoning_trace
        if citations is not None:
            log.citations = citations
        if raw_response_excerpt is not None:
            log.raw_response_excerpt = raw_response_excerpt[:2000]
        log.total_latency_ms = latency_ms
        log.status = status  # type: ignore[assignment]
        if error_message:
            log.error_message = error_message
        log.finished_at = datetime.now(timezone.utc).isoformat()
        return log


__all__ = ["AgentAdapter"]
