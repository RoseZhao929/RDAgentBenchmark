# MAI-DxO post-fix N=10 semantic validation

The earlier N=100 receipts are retained as failure evidence, not benchmark
results. Their model calls silently hit an exhausted direct OpenRouter key
because this workstation had no LiteLLM gateway configuration. Swarms swallowed
the repeated HTTP 403 errors and MAI-DxO emitted forced fallback diagnoses.

This validation refuses to run unless `LLM_GATEWAY_URL` and its configured
credential are present. It sends one minimal real request to both required
backbones, then runs each of the five missing cells in two stages:

1. deterministic N=2 probe, requiring both cases to have a valid `ok`
   prediction and zero `agent_error`/`timeout`;
2. resume the same receipt to N=10, requiring all ten cases to be valid, so
   the first two cases are not repeated.

Gateways whose public model IDs differ from the LiteLLM routing IDs may set
`LLM_GATEWAY_GPT5_MODEL` and `LLM_GATEWAY_V4FLASH_MODEL` for the two preflight
requests. The same public IDs are routed through the gateway's
OpenAI-compatible provider for the experiment, while receipts retain the
canonical benchmark backbone IDs.

Set `CELL_FILTER` to one of the five cell IDs to run/resume only that cell.
This supports safe cell-level parallelism because each cell owns a distinct
receipt. Set `RUN_LOG_OVERRIDE` to give each parallel cell its own log.

Run:

```bash
bash tasks/maidxo_n10_postparserfix_20260727/run.sh
```

Receipts are isolated under
`logs/maidxo_n10_postparserfix_20260727/receipts/`. A failed semantic gate stops
the entire sequence immediately. N=100 is not authorized until all five N=10
gates pass and their disease predictions are manually/auditor reviewed.

After all five launchers finish, run the stricter cross-cell audit:

```bash
python3 tasks/maidxo_n10_postparserfix_20260727/audit_n10.py \
  --report logs/maidxo_n10_postparserfix_20260727/audit_n10.json
```

After the audited files are copied to their standard committed filenames,
co-authors can verify that checkout directly:

```bash
python3 tasks/maidxo_n10_postparserfix_20260727/audit_n10.py \
  --phase4a-dir data/round2/phase4a \
  --expected-n 100 \
  --allow-model-abstentions
```

The standard Phase 4a files now contain the completed N=100 run. This verifies
the exact deterministic case sets, 100 unique terminal receipts per cell,
nonempty disease-like predictions or explicit method-level abstentions,
aligned confidence arrays, positive latencies, preserved raw evidence, and
absence of fatal gateway/runtime failures. The receipt `cost_usd` field is
only the harness token-price estimate; it must not be reported as an AIHubMix
billing receipt.

Known invalid attempts are kept outside `receipts/`, under
`failed_attempts/`. They include the direct-OpenRouter 403 run, the
pre-context-compression-routing fix V4-Flash run, and the pre-postmapping noise
filter run. They are audit evidence only and must never be concatenated into
benchmark results.

## N=100 continuation

After the N=10 gate, resume all five standard Phase 4a files with:

```bash
CELL_CONCURRENCY=4 \
  bash tasks/maidxo_n10_postparserfix_20260727/run_n100.sh
```

`run_n100.sh` performs the two-model gateway preflight and skips existing
`ok`, `skipped`, and held `parser_error` receipts. The monitor must classify a
non-`ok` row before any retry: explicit model abstentions remain terminal
misses, while infrastructure failures can be removed and retried within the
bounded attempt policy. Use `monitor_n100.py` during the run and
`compact_terminal_receipts.py` after interrupted supervisor restarts.
