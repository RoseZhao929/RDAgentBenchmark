"""OpenRouter call wrapper that auto-fills CostBreakdown into PredictionLog (S3).

Usage:
    from harness.logging.openrouter_wrapper import openrouter_chat, fill_cost
    resp = openrouter_chat(
        model="google/gemini-3-flash-preview",
        messages=[{"role": "user", "content": "..."}],
        max_tokens=1500,
    )
    log.cost = fill_cost(resp, log.cost)
    log.raw_response_excerpt = resp["choices"][0]["message"]["content"][:2000]

Pricing pulled from `.env` (per-million-token rates).
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

import requests

from harness.logging.schema import CostBreakdown

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


# Price table per 1M tokens (USD).
# Filled from .env if present, otherwise hard-coded fallback at submission rates.
_PRICES = {
    "google/gemini-3-flash-preview": (
        float(os.environ.get("PRICE_GEMINI_FLASH_IN", "0.50")),
        float(os.environ.get("PRICE_GEMINI_FLASH_OUT", "3.00")),
    ),
    # 2026-05-19: OpenRouter resolves bare alias to this dated id in response
    # JSON. fill_cost reads response.model so we need both keys to match.
    "google/gemini-3-flash-preview-20251217": (
        float(os.environ.get("PRICE_GEMINI_FLASH_IN", "0.50")),
        float(os.environ.get("PRICE_GEMINI_FLASH_OUT", "3.00")),
    ),
    "deepseek/deepseek-v3.2-exp": (
        float(os.environ.get("PRICE_DEEPSEEK_IN", "0.27")),
        float(os.environ.get("PRICE_DEEPSEEK_OUT", "1.10")),
    ),
    # 2026-05-19: BACKBONE_LO upgraded to v4-pro for main experiment
    "deepseek/deepseek-v4-pro": (
        float(os.environ.get("PRICE_DEEPSEEK_V4_PRO_IN", "0.435")),
        float(os.environ.get("PRICE_DEEPSEEK_V4_PRO_OUT", "0.870")),
    ),
    # 2026-05-20: V4-Flash (4x cheaper than V4-Pro for Phase 4c scale)
    "deepseek/deepseek-v4-flash": (
        float(os.environ.get("PRICE_DEEPSEEK_V4_FLASH_IN", "0.112")),
        float(os.environ.get("PRICE_DEEPSEEK_V4_FLASH_OUT", "0.224")),
    ),
    # 2026-05-20: GLM-5 (Chinese closed mid, replacement for GPT-5 minimal)
    "z-ai/glm-5": (
        float(os.environ.get("PRICE_GLM5_IN", "0.60")),
        float(os.environ.get("PRICE_GLM5_OUT", "1.92")),
    ),
    "openai/gpt-5": (
        float(os.environ.get("PRICE_GPT5_IN", "1.25")),
        float(os.environ.get("PRICE_GPT5_OUT", "10.00")),
    ),
    # Added 2026-05-14 as a fallback during the sanity-check pilot when gpt-5
    # turned out to be too slow / unreliable for batch use. OpenRouter price
    # as of 2026-05: $0.15 / $0.60 per 1M (input / output) tokens.
    "openai/gpt-4o-mini": (
        float(os.environ.get("PRICE_GPT4O_MINI_IN", "0.15")),
        float(os.environ.get("PRICE_GPT4O_MINI_OUT", "0.60")),
    ),
    # Added 2026-05-15 to back P5 v2 re-run with a non-Gemini LLM judge so
    # we can detect self-preference bias against scaffolded agents. OpenRouter
    # rates as of 2026-05: $3 / $15 per 1M (input / output) tokens.
    "anthropic/claude-sonnet-4.5": (
        float(os.environ.get("PRICE_CLAUDE_SONNET_45_IN", "3.00")),
        float(os.environ.get("PRICE_CLAUDE_SONNET_45_OUT", "15.00")),
    ),
    # OpenRouter resolves anthropic/claude-sonnet-4.5 to this dated alias in
    # the response body; keep the same price so fill_cost() reads the right
    # column when the API echoes the resolved id.
    "anthropic/claude-4.5-sonnet-20250929": (
        float(os.environ.get("PRICE_CLAUDE_SONNET_45_IN", "3.00")),
        float(os.environ.get("PRICE_CLAUDE_SONNET_45_OUT", "15.00")),
    ),
}


def get_price(model: str) -> tuple[float, float]:
    """Return (input_price_per_1M, output_price_per_1M) USD for a model id.

    Falls back to (0,0) — caller will see cost_usd=0 if unknown, prompting fix.
    """
    # exact match
    if model in _PRICES:
        return _PRICES[model]
    # openrouter/<provider>/<model> form
    bare = model.removeprefix("openrouter/")
    return _PRICES.get(bare, (0.0, 0.0))


def fill_cost(response_json: dict, prior: Optional[CostBreakdown] = None) -> CostBreakdown:
    """Read prompt_tokens / completion_tokens / cached_prompt_tokens from an
    OpenRouter-compatible response and compute cost_usd.

    Accumulates with `prior` if provided (for multi-call agents).
    """
    usage = response_json.get("usage", {}) or {}
    pt = int(usage.get("prompt_tokens", 0))
    ct = int(usage.get("completion_tokens", 0))
    cached_pt = int(
        usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)
        or usage.get("cached_prompt_tokens", 0)
    )

    model = response_json.get("model", "") or ""
    p_in, p_out = get_price(model)

    # Cached prompt tokens are usually billed at 25% (OpenAI) or 10% (Anthropic)
    # — OpenRouter normalizes but each provider varies. Use 25% as a conservative
    # default; downstream can recompute if exact rate matters.
    billable_input = (pt - cached_pt) + 0.25 * cached_pt

    cost_usd = (billable_input * p_in + ct * p_out) / 1_000_000

    if prior is None:
        prior = CostBreakdown()
    return CostBreakdown(
        prompt_tokens=prior.prompt_tokens + pt,
        completion_tokens=prior.completion_tokens + ct,
        cached_prompt_tokens=prior.cached_prompt_tokens + cached_pt,
        cost_usd=prior.cost_usd + cost_usd,
        provider="openrouter",
    )


def openrouter_chat(
    model: str,
    messages: list[dict],
    *,
    max_tokens: int = 2000,
    temperature: float = 0.0,
    api_key: Optional[str] = None,
    timeout: int = 120,
    extra: Optional[dict[str, Any]] = None,
    reasoning_effort: Optional[str] = None,
    reasoning_disabled: bool = False,
) -> dict:
    """Thin wrapper around OpenRouter chat completions.

    Returns the parsed JSON response.

    Args:
        reasoning_effort: For reasoning models (GPT-5, o1, DeepSeek R1, etc.).
            One of "minimal" / "low" / "medium" / "high". For our P2 no-scaffold
            LLM controls we use "minimal" to measure raw capability without
            extra chain-of-thought. For H6 reasoning-mode ablation we vary this.

            Verified 2026-05-14: GPT-5 default = "medium" or "high" consumes
            up to 6000 tokens of reasoning before producing visible content,
            leaving `content=null` with `finish_reason="length"`. With
            "minimal" it emits 0 reasoning tokens and full content in ~2s.
    """
    key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY missing")

    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if reasoning_effort is not None:
        # OpenRouter accepts both flat `reasoning_effort` (passed through to
        # provider) and the normalized `reasoning: {effort}` object. Use the
        # normalized form to be provider-agnostic.
        body["reasoning"] = {"effort": reasoning_effort}
    if reasoning_disabled:
        # 2026-07-03 — DeepSeek-V4-Pro reasons *unbounded* and ignores every
        # effort/cap knob; only reasoning={"enabled": false} actually turns it
        # off (verified: rt=0, content 3/3, 1.9s). Takes precedence over effort.
        body["reasoning"] = {"enabled": False}
    if extra:
        body.update(extra)

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    r = requests.post(OPENROUTER_URL, headers=headers, json=body, timeout=timeout)
    r.raise_for_status()
    return r.json()


def timed_openrouter_chat(model: str, messages: list[dict], **kwargs) -> tuple[dict, int]:
    """Same as `openrouter_chat` but also returns latency_ms."""
    t0 = time.time()
    resp = openrouter_chat(model, messages, **kwargs)
    return resp, int((time.time() - t0) * 1000)


__all__ = [
    "openrouter_chat",
    "timed_openrouter_chat",
    "fill_cost",
    "get_price",
]
