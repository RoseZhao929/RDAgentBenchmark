# H2 full-N — variant-channel lift (paired, PP-Store)

llm_control, Gemini Flash, N=500 paired variant cases (both modes ok).

| Mode | R@1 | hits |
|---|---|---|
| P2 (HPO only) | 0.296 | 148/500 |
| P3 (HPO + variants) | 0.494 | 247/500 |
| **Lift** | **+0.198** | — |

- Paired McNemar discordant: P3-win=106, P2-win=7; χ²(cc)=84.99
- 2-prop z (one-sided P3>P2): z=6.40
- Pre-registered H2: lift ≥ +10 pp → SUPPORTED