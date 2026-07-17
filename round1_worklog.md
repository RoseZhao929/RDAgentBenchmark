# Round 1 Worklog — Append-Only Status Log

> 实时追踪 — 每个里程碑追加一段。最早的在最上面。

---

## 2026-05-14 — MIMIC 数据到位,启动 final 3 并行 track

### 收到 MIMIC-IV
- 路径:`data/mimic-iv-3.1/`(9.9 GB,hosp + icu 模块全)
- 缺 `discharge.csv.gz`(MIMIC-IV-Note 单独包)→ v1 走 ICD-only 切片,note-based NLP 召回标 v2 future work

### 启动 3 个并行 track
1. **Track A — PMC 候选池 dedup + finalize**(me, foreground)— 给人工核验用的干净 candidate list
2. **Track B — MIMIC-IV rare disease 切片**(`harness/ingest/mimic_iv.py` + 跑全量)— 后台 bash
3. **Track C — Sanity-check pilot**(subagent)— 写 LLM-control 单 backbone adapter + 跑 50 例 stratified 验证 pipeline 端到端

### Track A 完成(2026-05-14)— PMC 候选池 finalized

`harness/pmc_oa/finalize.py` 写完 + 跑完。Stats:

| Metric | Value |
|---|---|
| Total extracted lines | 3,043 |
| Unique PMC IDs in 04 | 2,394 |
| Unique PMC IDs in 05 (mapping) | 2,343 |
| Definitive diagnosis | 2,343 |
| **Passed filter (=candidate pool)** | **1,433** |
| ├ exact_name (Tier 1) | 1,047 |
| └ fuzzy ≥95 (Tier 2) | 386 |
| Filtered: no Orpha | 302 |
| Filtered: fuzzy <95 | 608 |

输出:
- `data/pmc_oa_holdout/06_candidates_for_review.jsonl` — 排序后的候选 list(exact_name 优先)
- `data/pmc_oa_holdout/REVIEW_INSTRUCTIONS.md` — 标注员操作 guide(每例 5-10 min,目标挑 200)

设计要点:
- fuzzy threshold 提到 95(原 90 有 "dengue shock syndrome" → "CK syndrome" 这种 false positive)
- 排序:exact_name > fuzzy(score desc),标注员先做 Tier 1
- per-case fields:pmc_url / hpo_phenotypes / case_excerpt(2k 上限)/ top_candidates(供 reviewer 对比)

### Track B 完成(2026-05-14)— MIMIC-IV rare disease slice

`harness/ingest/mimic_iv.py` + `harness/ingest/mimic_iv_filter.py` 写完跑完。

**v1 raw slice**(`data/mimic_iv_rd_slice/cases.jsonl`,213 MB):
- 6.36M 全 ICD-10 行 → cross-ref Orphadata(2,173 ICD-Orphanet 映射)
- 229K 罕见病行 / 150,033 unique 入院
- 107K Exact / 37K NTBT / 5K BTNT 关系类型

**问题发现**:Orphadata 把 G20 Parkinson 等映射到 `"NON RARE IN EUROPE: Parkinson disease"`(Orphanet 显式标 non-rare)— 直接 ingest 有大量 false positive。

**3 个 filter level**:
| Slice | 例数 | 用途 |
|---|---|---|
| `cases_filtered_lenient.jsonl` | 61,369 | 仅去掉 NON-RARE 标记 |
| `cases_filtered_exact.jsonl` | 18,480 | + 仅 Exact 关系 |
| **`cases_filtered_diverse.jsonl`** | **956 / 239 disease** | + cap 5/disease(主实验用)|

**主实验 canonical slice**:`cases_filtered_diverse.jsonl`(956 / 239 disease)— 接近 plan.md 的 ~1,875 / 355 target,但更严格(只 Exact + 多样性)。

**已知限制**(v1):
- 无 MIMIC-IV-Note(`discharge.csv.gz`)→ 无 free-text vignette,只有 synthetic vignette from ICD titles
- 无 NLP recall step → 找不到 Q87.8 伞码下的 hidden 罕见病
- 这两个标到 INGEST_REPORT 作为 v2 future work

### Track C — Sanity-check pilot
subagent 还在跑,等通知

### GPT-5 batch usability fix(2026-05-14,讨论 Round 2 时复盘发现)

**问题根因诊断**:之前 sanity-check 里 GPT-5 慢/hang/content=null **不是 OpenRouter 路由问题**,是没显式设 `reasoning_effort`。

实测对照:
| Config | Latency | reasoning_tokens | content | finish |
|---|---|---|---|---|
| `reasoning_effort: "minimal"` | **2.4s** | **0** | 完整 134 chars | stop ✅ |
| `reasoning_effort: "low"` | 5.7s | 192 | 完整 107 chars | stop ✅ |
| DEFAULT(没设) | 15.7s | 448 | **0 chars** | **length ❌** |
| `reasoning: {effort: "minimal"}` 对象形式 | 2.2s | 0 | 完整 161 chars | stop ✅ |

**修复**:`harness/logging/openrouter_wrapper.py` 加 `reasoning_effort` 参数(用 OpenRouter normalized `reasoning: {effort}` 形式)。

**对 Round 2 lineup 的含义**:
- GPT-5 完全可用,**显式设 `reasoning_effort="minimal"`** 即可
- H6 reasoning-mode 消融可以正面用 minimal vs low vs high 三档对照
- 不需要换 `gpt-5-mini` 或 `gpt-4o`,GPT-5 frontier 标签保留

### 之前(2026-05-11/12)产出
- 8/8 agent adapter shim verified(3,485 LOC)+ LIRICAL Java 工具自带 JRE
- Harness: canonical schema + 3 ingest adapter + 5 metric module + logging + pmc_oa pipeline + cross-map + HPO ontology + OpenRouter wrapper
- OSF preregistration draft 写完
- PMC 抽取 2,394 unique / 2,317 definitive
- Orphanet mapping 2,898 entries(含重复,待 dedup)
- PhenoBrain dropped → LIRICAL 替换

---

## 2026-05-14 — Sanity-check pilot done

### Deliverables
- `harness/agents/llm_control.py` — `LLMControlAdapter` (P1 / P2 / P5)
  - Direct OpenRouter chat call (no subprocess, no agent venv)
  - Reuses `case_to_question`, `parse_ranked_top5`, `map_names_to_ids` from `_adapter_utils`
  - Auto-fills `CostBreakdown` via `fill_cost(...)` (patches the resolved model id back to our base price-table key so dated previews still get billed correctly)
  - Pillar 1: extracts NL phenotype phrases, returns `HpoTerm(id="HP:0000000", label=...)` for downstream HPO normalization
- `scripts/sanity_check_pilot.py` — stratified 25 PP-Store + 25 RareArena RDS pilot driver with `--resume`, JsonlPredictionLogger output, multi-backbone loop, markdown report writer
- `data/sanity_check/results.jsonl` — 156 PredictionLog rows
- `data/sanity_check/REPORT.md` — comparison table + errors

### Numbers (P2 phenotype DDx, eval_mode=gold_hpo, n=50, seed=42)

| Backbone | R@1 | R@3 | R@5 | R@10 | MRR | Cost ($) | Mean Lat | N OK |
|---|---|---|---|---|---|---|---|---|
| `google/gemini-3-flash-preview` | 0.26 | 0.32 | 0.40 | 0.40 | 0.305 | 0.05 | 3.5s | 50/50 |
| `deepseek/deepseek-v3.2-exp`    | 0.20 | 0.28 | 0.30 | 0.30 | 0.238 | 0.01 | 6.3s | 50/50 |
| `openai/gpt-5`                   | (n=6, partial) — see note below | | | | | 0.30 | 77s | 4/6 |
| `openai/gpt-4o-mini` (placeholder) | 0.08 | 0.16 | 0.18 | 0.18 | 0.111 | 0.01 | 3.9s | 50/50 |

### 已知问题 / 决策
- **gpt-5 unusable for batch sanity**: median 60-90s per call, occasional 5-min hangs; reasoning-token usage frequently consumes all `max_tokens` (=6000) leaving `content=null`. After 6 cases (2 parser_errors, 4 ok) I terminated the gpt-5 run and substituted `openai/gpt-4o-mini` as a 3rd no-scaffolding control per the task's fallback clause. For main experiments we'll need either: (a) extremely large `max_tokens` (>>10k) and accept ~$0.5/case, or (b) a different model (gpt-5-mini / o1-mini) for the "frontier" lineup slot.
- Gemini-3 Flash is the strongest baseline at trivial cost — pretty striking; this is what we compare scaffolded agents against in S7.
- `gpt-4o-mini` was missing from `harness.logging.openrouter_wrapper._PRICES` initially → cost=0; patched the price table + back-filled cost in the JSONL.
- Median rank capped at 6 for misses (= len(top5)+1), so the "6.0" rows mean most cases miss top-5.

### Pipeline status: 端到端 verified
- Adapter → JsonlPredictionLogger → read_logs → cross-map → recall_at_k / MRR / cost aggregation 全跑通
- Resume mode works (`--resume` skipped 104 prior records, only ran missing backbone)
- This unblocks Track A1 (run scaffolded agents on the same 50-case sample and compare)
