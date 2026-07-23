# Experimental Setup Details

The four backbones evaluated in this work, with dated OpenRouter aliases,
pricing and reasoning configuration, are given below.

| Alias | OpenRouter ID | Price ($/M tok in/out) | Evaluation mode |
|---|---|---|---|
| **Open-cheap** | `deepseek/v4-flash` | 0.28 / 0.42 | default light reasoning |
| **Open-frontier** | `deepseek/deepseek-v4-pro` | 0.55 / 2.19 | reasoning disabled |
| **Mid** | `gemini-3-flash-20251217` | 0.50 / 3.00 | thinking off |
| **Frontier** | `openai/gpt-5` | 1.25 / 10.00 | `reasoning_effort=minimal` |

Settings held constant across all (agent, backbone) cells: temperature `0.0`,
seed `42` (where the SDK exposes one), per-call timeout `600–1200 s`, retry
policy `tenacity` exponential backoff capped at 3 attempts, and `max_tokens`
left at each adapter's published default (2K–6K).
