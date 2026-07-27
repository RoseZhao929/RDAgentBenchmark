# MAI-DxO N=100 final results

All rates use the fixed attempted denominator of 100 cases per cell; explicit model abstentions count as misses.

| Dataset | Backbone | Terminal | Abstain | R@1 variant | R@5 variant | Median latency | Receipt cost estimate |
|---|---|---:|---:|---:|---:|---:|---:|
| Phenopacket Store | GPT-5 | 100/100 | 0 | 0.150 | 0.240 | 261.7s | $0.5000 |
| RareArena RDS | DeepSeek V4-Flash | 100/100 | 0 | 0.160 | 0.310 | 303.1s | $0.0431 |
| RareArena RDS | GPT-5 | 100/100 | 1 | 0.160 | 0.280 | 268.7s | $0.6329 |
| RareBench | DeepSeek V4-Flash | 100/100 | 1 | 0.010 | 0.040 | 307.0s | $0.0255 |
| RareBench | GPT-5 | 100/100 | 0 | 0.000 | 0.000 | 265.9s | $0.4506 |

- Total terminal receipts: **500/500**
- Normal predictions: **498**
- Explicit model abstentions: **2**
- N=100 extension wall clock: **2.38 h**
- Aggregate per-case latency: **39.85 h**
- Summed receipt-side cost estimate: **$1.6521**
- MAI-DxO simulated clinical-resource cost: **$669,490**

The cost estimate is not an AIHubMix invoice and may omit internal panel calls because MAI-DxO does not expose complete LiteLLM usage. The simulated clinical cost is also not API spend.

## Receipt hashes

```text
40fdf9d89f525a0729356c2f9f3d08d655280999d60b5758b3a6ee0846f00784  predictions_phenopacket_store_maidxo_openai_gpt-5.jsonl
975345e389f27ac72bd888d92a9480b6043b78c191c6bc9c02afc370335cab36  predictions_rarearena_rds_maidxo_deepseek_deepseek-v4-flash.jsonl
6ae7d1df1936ba0816067d1d68206dddb0bc6626c9c9d8f1ac15971161899577  predictions_rarearena_rds_maidxo_openai_gpt-5.jsonl
68740239870f930623aaad6d9fb17d68abadd0761645addcff77213584f828d8  predictions_rarebench_maidxo_deepseek_deepseek-v4-flash.jsonl
345950efda179b02eeef060c2aa336785ac3329ad9de1c101b038a9b1ab6e43c  predictions_rarebench_maidxo_openai_gpt-5.jsonl
```
