# MAI-DxO N=10 gate handoff

Status: **gate completed; superseded by the audited N=100 run**.

This branch fills the five previously missing MAI-DxO cells with deterministic
N=10 smoke cohorts:

| Dataset | Backbone | Rows | Status |
|---|---|---:|---|
| Phenopacket Store | GPT-5 | 10 | 10 `ok` |
| RareArena RDS | DeepSeek V4-Flash | 10 | 10 `ok` |
| RareArena RDS | GPT-5 | 10 | 10 `ok` |
| RareBench | DeepSeek V4-Flash | 10 | 10 `ok` |
| RareBench | GPT-5 | 10 | 10 `ok` |

The five standard files under `data/round2/phase4a/` have since been expanded
to N=100. Their current scores, hashes, latency, and cost estimates are in
`N100_RESULTS.md` / `N100_RESULTS.json`; the old N=10 hashes are intentionally
not authoritative.

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
  --phase4a-dir data/round2/phase4a \
  --expected-n 100 \
  --allow-model-abstentions
```

The current audit checks exact deterministic N=100 membership, one terminal
receipt per case, disease-like predictions (or an explicit model abstention),
no duplicate predictions, confidence alignment, positive latency, retained
raw final/differential evidence, and no fatal gateway/runtime markers.

The summed `cost_usd` fields are harness-side token-price estimates only, not
AIHubMix billing receipts. Invalid attempts are retained only under ignored
`logs/.../failed_attempts/` and are not part of the files above.
