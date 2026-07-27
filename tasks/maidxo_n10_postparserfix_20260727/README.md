# MAI-DxO post-fix N=10 semantic validation

The earlier N=100 receipts are retained as failure evidence, not benchmark
results. Their model calls silently hit an exhausted direct OpenRouter key
because this workstation had no LiteLLM gateway configuration. Swarms swallowed
the repeated HTTP 403 errors and MAI-DxO emitted forced fallback diagnoses.

This validation refuses to run unless `LLM_GATEWAY_URL` and its configured
credential are present. It sends one minimal real request to both required
backbones, then runs each of the five missing cells in two stages:

1. deterministic N=2 probe, requiring at least one valid `ok` prediction and
   zero `agent_error`/`timeout`;
2. resume the same receipt to N=10, so the first two cases are not repeated.

Run:

```bash
bash tasks/maidxo_n10_postparserfix_20260727/run.sh
```

Receipts are isolated under
`logs/maidxo_n10_postparserfix_20260727/receipts/`. A failed semantic gate stops
the entire sequence immediately. N=100 is not authorized until all five N=10
gates pass and their disease predictions are manually/auditor reviewed.
