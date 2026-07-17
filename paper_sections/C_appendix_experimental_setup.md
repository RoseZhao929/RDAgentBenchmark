# Experimental Setup Details

The four backbones evaluated in this work, with their dated OpenRouter aliases,
pricing, context windows, reasoning channel and role, are given below.

| Alias | OpenRouter ID | Price ($/M tok in/out) | Context | Reasoning channel | Role |
|---|---|---|---|---|---|
| **Open-cheap** | `deepseek/deepseek-v4-flash` | 0.28 / 0.42 | 128K | light reasoning (fits default budget) | Open-weight low-cost ceiling |
| **Open-frontier** | `deepseek/deepseek-v4-pro` (reasoning **disabled**) | 0.55 / 2.19 | 128K | heavy reasoning (forced **off**) | Open-weight frontier |
| **Mid** | `google/gemini-3-flash-preview-20251217` | 0.50 / 3.00 | 1M | thinking (default off) | Primary baseline and LLM-judge candidate (later swapped, §7.5) |
| **Frontier** | `openai/gpt-5` (`reasoning_effort=minimal`) | 1.25 / 10.00 | 256K | reasoning tokens (forced minimal) | Frontier ceiling |

Settings held constant across all (agent, backbone) cells: temperature `0.0`,
seed `42` (where the SDK exposes one), per-call timeout `600–1200 s`, retry
policy `tenacity` exponential backoff capped at 3 attempts, and `max_tokens`
left at each adapter's published default (2K–6K).
