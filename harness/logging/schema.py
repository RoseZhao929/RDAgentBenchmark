"""Prediction log schema — JSONL per (agent_id, backbone_id, pillar, case).

Every agent call gets one row written to a JSONL file. The harness aggregates
these rows for metric computation, cost tracking, and reliability analysis.

Why JSONL not Parquet/DB: streaming append-safe, human-readable, trivial diff,
no schema migration headache. Aggregation is one pass with `polars` / `pandas`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Pillar = Literal["P1_extraction", "P2_phenotype_ddx", "P3_genotype_aware",
                 "P4_family_aware", "P5_reasoning_communication"]

EvalMode = Literal["gold_hpo", "end_to_end"]   # see plan.md §3 dual-pass


class ToolCall(BaseModel):
    """One tool invocation by the agent (for Stream E/A1 tool-level ablation)."""
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    args_redacted: Optional[str] = None   # redact PII / secrets
    success: bool = True
    latency_ms: int = 0
    output_chars: int = 0


class CostBreakdown(BaseModel):
    """Per-call cost from the LLM provider's response or our wrapper."""
    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_prompt_tokens: int = 0
    cost_usd: float = 0.0
    provider: Optional[str] = None       # "openrouter" / "openai" / "anthropic" / "google"


class PredictionLog(BaseModel):
    """One row per agent prediction.

    Indexed by (agent_id, backbone_id, dataset, pillar, eval_mode, case_id).
    """
    model_config = ConfigDict(extra="forbid")

    # identity
    run_id: str = Field(..., description="UUID for the whole benchmark run.")
    agent_id: str
    backbone_id: str = Field(
        ...,
        description="Canonical backbone identifier, e.g. "
        "'openrouter/google/gemini-3-flash-preview-20251217'.",
    )
    backbone_temperature: Optional[float] = None
    backbone_seed: Optional[int] = None

    # data
    case_id: str
    source_dataset: str
    source_split: Optional[str] = None
    pillar: Pillar
    eval_mode: EvalMode

    # prediction
    ranked_predictions: List[str] = Field(
        default_factory=list,
        description="Ranked list of predicted disease IDs (top-k or longer).",
    )
    confidence_scores: List[float] = Field(
        default_factory=list,
        description="Parallel to ranked_predictions; for calibration metrics.",
    )

    # Pillar 1 specific
    extracted_hpo_terms: List[str] = Field(
        default_factory=list,
        description="HPO IDs extracted by the agent (Pillar 1 output).",
    )

    # Pillar 5 specific (reasoning trace + citations)
    reasoning_trace: Optional[str] = None
    citations: List[str] = Field(default_factory=list)

    # raw provider response (truncated)
    raw_response_excerpt: Optional[str] = Field(
        default=None,
        description="First ~2000 chars of agent's final response for audit.",
    )

    # operational metrics
    tool_calls: List[ToolCall] = Field(default_factory=list)
    total_latency_ms: int = 0
    cost: CostBreakdown = Field(default_factory=CostBreakdown)

    # outcome
    status: Literal["ok", "agent_error", "timeout", "rate_limited",
                    "parser_error", "skipped"] = "ok"
    error_message: Optional[str] = None

    # timestamps
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: Optional[str] = None

    # version pinning (for reproducibility)
    harness_version: str = "0.1.0"
    agent_version: Optional[str] = Field(
        default=None,
        description="Agent repo commit hash if available.",
    )

    # arbitrary side info
    extra: dict[str, Any] = Field(default_factory=dict)


__all__ = ["PredictionLog", "ToolCall", "CostBreakdown", "Pillar", "EvalMode"]
