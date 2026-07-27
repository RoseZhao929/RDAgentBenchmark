# MAI-DxO N=10 handoff

Status: **complete and audited (50/50 valid receipts)**.

This branch fills the five previously missing MAI-DxO cells with deterministic
N=10 smoke cohorts:

| Dataset | Backbone | Rows | Status |
|---|---|---:|---|
| Phenopacket Store | GPT-5 | 10 | 10 `ok` |
| RareArena RDS | DeepSeek V4-Flash | 10 | 10 `ok` |
| RareArena RDS | GPT-5 | 10 | 10 `ok` |
| RareBench | DeepSeek V4-Flash | 10 | 10 `ok` |
| RareBench | GPT-5 | 10 | 10 `ok` |

The complete receipts are stored under `data/round2/phase4a/` using the normal
Phase 4a prediction filenames. These files are N=10 validation results, not
N=100 benchmark results.

SHA-256:

```text
870689555777dd87182ba6341213e5487ef263c4d9c107c2869ef3003e70e022  predictions_phenopacket_store_maidxo_openai_gpt-5.jsonl
28fd582df5515ab9d9d2b6064aef8462637a5ca36cebefc75568266e2589cbef  predictions_rarearena_rds_maidxo_deepseek_deepseek-v4-flash.jsonl
f9a136d1b0f29156b678f279650be4076a2e00b149aadf7ef99b0a7354db9b0c  predictions_rarearena_rds_maidxo_openai_gpt-5.jsonl
121a02a1236ef7c905411c9b579c2b6f05703f14e1c77b9a022958e5953d06dd  predictions_rarebench_maidxo_deepseek_deepseek-v4-flash.jsonl
adf4d3629447add7eded2868e226c9b65f4b121ca875da3be47bafbfd8005e97  predictions_rarebench_maidxo_openai_gpt-5.jsonl
```

## What differs from main

- Routes the canonical benchmark backbone ID separately from the concrete
  OpenAI-compatible gateway model ID.
- Preserves Swarms structured tool-call envelopes and requires tool use for
  hypothesis/consensus agents.
- Disables Swarms' implicit context compressor for one-loop MAI-DxO agents;
  it bypassed the configured gateway for V4-Flash.
- Rejects swallowed fatal gateway errors and non-disease output fragments.
- Preserves explicit natural-language diagnoses when no safe Orphanet mapping
  exists, while deduplicating accepted ontology IDs.
- Makes RareBench N=2/N=10/N=100 exact-size, stratified and prefix-stable.
- Adds a real two-model gateway preflight, N=2 and N=10 semantic gates, a
  cross-cell auditor, and repair/normalization utilities.

## Verification

Run:

```bash
python3 tasks/maidxo_n10_postparserfix_20260727/audit_n10.py \
  --phase4a-dir data/round2/phase4a
```

The completed audit checked exact deterministic case membership, ten unique
`ok` rows per cell, disease-like/nonempty predictions, no duplicate
predictions, confidence alignment, positive latency, retained raw
final/differential evidence, and no recorded fatal gateway/runtime markers.

The summed `cost_usd` fields are harness-side token-price estimates only, not
AIHubMix billing receipts. Invalid attempts are retained only under ignored
`logs/.../failed_attempts/` and are not part of the files above.
