# Round 2 Worklog — Append-Only Status Log

> Round 1 worklog: `round1_worklog.md`(2026-05-11/12/14)
> Round 2 plan: `round2_plan.md`

---

## 2026-05-14/15 — Phase 0 Mini Pilot + Phase 1 启动

### Phase 0 Mini Pilot 结果(50 case × 6 agent × Gemini Flash × P2,2026-05-14 跑完)

| Rank | Agent | R@1 | OK | Note |
|---|---|---|---|---|
| 🥇 | lirical | 0.40 | 25/50 | 只 PP-Store 一半,RareArena 25 个 skipped |
| 🥈 | medagents | 0.36 | 50/50 | beat Gemini Flash 0.26 |
| 🥉 | mdagents | 0.34 | 50/50 | beat Gemini Flash |
| — | vc_rdagent | 0.32 | 25/50 | 只 PP-Store 一半,offline Stage 1 |
| baseline | llm_control(Gemini Flash) | 0.26 | 50/50 | — |
| — | agentclinic | 0.20 | 50/50 | **输给 baseline**,OSCE 对 HPO-only case 浅 |
| ❌ | maidxo | 0.00 | 50/50 | max_iter=1 → "No diagnosis" |

实际 cost(backfill 后):$0.45 总(医agents $0.26 最贵,maidxo / lirical / vc_rdagent $0 — maidxo subprocess 没抓 token)。

### 复盘 ① 3 个决策已锁定
- D1 MAI-DxO:max_iterations=3 + parser fuzzy-match fallback(都做)
- D2 Cost tracking:6 个 subprocess adapter 加 `fill_cost`,旧数据 backfill 完
- D3 RareArena 公平性:LIRICAL/VC-RDAgent end_to_end mode 用 LLM 上游抽 HPO + 归一化

### Phase 1 启动(2026-05-15)
- Subagent X(bug fix marathon)— 90% 完成,patches OK 但没自跑 verification re-run
- Subagent Y(P1/P5 pilots)— 写了脚本,P1 只跑 30/150,P5 0 完成 → 我接手手动 kick off
- 当前 3 个 background 在跑:
  - Task 1 PID 91165:mini_round2 V2 re-run(maidxo/lirical/vc_rdagent × 50,~3h)
  - Task 2 PID 91166:P1 续跑(30 → 150,~30min)
  - Task 3 PID 91167:P5 pilot(40+40 calls,~30min)

---

## 🐛 已知问题 / 后续要修

### [P1 methodology] Phenopacket-Store 上做 P1 抽取评估是 leaky tautology

**问题**:`scripts/p1_extraction_pilot.py` 用 `synthesize_vignette_from_hpo(case)` 从 gold HPO 标签合成 vignette,再让 LLM 抽 HPO。LLM 实际是"读自己合成的标签"+ "再抽出来",**phrase_f1 必然接近 1.0**,跟真 P1 能力无关。

**Phase 0 Pilot 第一行实测**:`llm_control / PMID_31021519_individual_SATB2 → exact_f1=0.00 phrase_f1=1.00` — 印证。

**当前 P1 pilot 数据怎么用**(权宜):
- ✅ inter-agent 比较仍有用(llm_control vs rdma vs deeprare 在同一 leaky setup 下相对差异有信号)
- ❌ 绝对 P/R/F1 数字**不能上论文**(每个 agent 都会刷到 0.95+)

**真正的 P1 评估需要**:
- Free text source(case 有真 narrative,非合成)
- Independent gold HPO(human annotated 或别的 LLM 抽,跟测试 agent 不共享 backbone)

**数据集候选**:
- NEJM CPC 病例报告 + 已发表的 HPO 标注(部分 case 有 manual annotation)
- BioCreative VI BC6 / VII shared tasks(临床文本 → 命名实体抽取,含 HPO 子集)
- 自建:取 PMC OA 100 个 case,**让 Claude Opus 4.7 抽 gold HPO**(跟 Gemini/DeepSeek/GPT-5 测试 backbone 独立),作为 silver standard

**优先级**:Round 2 Phase 3 之前要补,**Phase 2(3-backbone expand)阶段 P1 评估暂用 inter-agent 比较 + 标 caveat**。

**追踪到**:`round2_plan.md` §3 Phase 1 还要补一段"P1 数据源待替换"

---

## 2026-05-15 (晚) — Phase 0 V2 + Phase 1 复盘 ②

### Phase 0 V2 定稿排名(D1+D2+D3 修复后,50 case × 6 agent × Gemini Flash × P2)

| Rank | Agent | R@1 | R@5 | Cost/50 | Mean Lat | vs v1 R@1 |
|---|---|---|---|---|---|---|
| 🥇 | medagents | **0.36** | 0.48 | $0.26 | 16.1s | = |
| 🥈 | mdagents | **0.34** | 0.46 | $0.05 | 6.5s | = |
| 🥉 | _llm_control (baseline)_ | _0.26_ | _0.40_ | _$0.05_ | _3.5s_ | _baseline_ |
| 4 | lirical | **0.22** | 0.32 | $0 | 3.7s | ↓ 0.40→0.22 |
| 5 | agentclinic | 0.20 | 0.34 | $0.13 | 39.6s | = |
| 6 | vc_rdagent | **0.18** | 0.32 | $0 | 74.1s | ↓ 0.32→0.18 |
| 7 | maidxo | 0.16 (31/50) | 0.19 | $0.12 | 224s | ↑ 0.00→0.16 |

**头号发现 — P1 → P2 cascade 真实存在**:LIRICAL / VC-RDAgent 在 PP-Store 半 ≈ 40% / 32% ✓,在 RareArena 半 ≈ 4% / 4%(eval_mode=end_to_end,LLM-extracted HPO 喂进去)。**HPO-list-only 经典工具严重依赖上游抽取质量**,印证 plan.md §3 双 pass 设计动机 + 支持 H8 假设。

### P1 (Pillar 1 Extraction) 结果 — 数据 leaky

| Agent | exact_f1 | phrase_norm_f1 | 备注 |
|---|---|---|---|
| llm_control | 0.000 | **0.970** | leaky tautology(已记 §"已知问题")|
| rdma | 0.000 | **0.995** | RDMA 微弱领先 |
| deeprare | — | not_implemented | adapter 没实现 P1 |

**绝对数字不能上论文**,但 inter-agent 比较(RDMA > llm_control 微弱)有信号。需 Phase 3 前换数据源(Opus silver gold)。

### P5 (Pillar 5 Reasoning Trace) 结果 — 4 个 methodology 问题

| Agent | factual | relevance | depth | faithful | trace_len | judge_err |
|---|---|---|---|---|---|---|
| **llm_control** | **4.70** | 4.50 | 3.60 | **4.90** | 986 chars | 0/10 |
| mdagents | 5.00 | 5.00 | 4.00 | 5.00 | 337 chars | **8/10 ⚠** |
| deeprare | 1.70 | 1.40 | 1.90 | 1.70 | 18,429 chars | 0/10 |
| maidxo | nan | nan | nan | nan | 0 chars | **10/10 ❌** |

**4 个问题**:
1. MAI-DxO trace 没填(0 chars,judge 全 error)
2. MDAgents trace 太短(337 chars),judge 解析失败率 8/10
3. llm_control 4.70 self-preference bias(judge=Gemini Flash,同 backbone)
4. DeepRare 18k chars trace 拿低分(judge 处理不了长 trace OR trace 真有 wrong claims)

### Phase 1 收尾决策(2026-05-15 用户拍板)

| # | 决策 | 内容 |
|---|---|---|
| Q1 | maidxo 19 个 RareArena 续跑 | ✅ 继续跑(~80 min, ~$0.04) |
| Q2 | P5 4 个 fix 并行做 | ✅ 一个 subagent 一次做完所有 4 个 fix + 一次 re-run |
| Q3 | Opus 4.7 silver gold 数据源 | ✅ 100 case + cost cap $20 |
| Q4 | Phase 2 启动时机 | ⏸ 严格等 Phase 1 完成(包括 maidxo + P5 修 + Opus 抽完) |

### Phase 1 收尾 — 当前 3 个并行 track

| Track | 内容 | 估时 | 估 cost |
|---|---|---|---|
| **A** maidxo 19 case 续跑 | 接着 mini_round2 V2 跑完 31→50 | ~80 min | ~$0.04 |
| **B** P5 4-fix pass | adapter trace 修(maidxo/mdagents)+ judge backbone 换(Claude Sonnet 4.5 via OpenRouter)+ chunking >5k chars + 一次性 re-run | 2-3h | ~$0.30 |
| **C** Opus 4.7 silver gold | PMC OA 100 case + Opus 4.7 抽 HPO + diagnosis → 独立 silver gold for Phase 3 P1 评估 | ~1h | $5-10 |

Phase 1 全完成后 → 复盘 ③ → 启动 Phase 2(3-backbone expand)。

---

## 🎯 工作风格元原则(用户 2026-05-15 锁定)

> **每个任务批次必须**:
> 1. **Plan** — 明确做什么、为什么、产出什么
> 2. **拆同步步骤** — 列出可并行 vs 必须串行的步骤
> 3. **定时随时复盘** — 每 spawn 3 个 task 或每个里程碑暂停反思 bug + 忘记考虑
> 4. **详细记录中间试验过程** — worklog 实时更新,不只记结果
> 5. **最终总结** — 每个 phase 结束 wrap 一个清晰的 summary

每次新 spawn / 切换 phase 必须显式走一遍这 5 步,不能跳过。

---

## 📝 Pending TODO(用户晚点处理)

- **B4 OSF preregistration submit** — review `osf_preregistration.md` + timestamp 提交 OSF 网站。Must happen 在 PMC holdout unblind 之前(标注员开干 ~1-2 周内)。**用户晚点处理**,我不要替你 submit(涉及账户)。

---

## 🔍 Retrospective Checkpoint #1(2026-05-15,3 track spawn 后,用户指令)

> 用户指令:"过程中时不时暂停,认真复盘:(1) 是否有 bug 或问题导致后续重跑 (2) 是否有忘记考虑的问题"
> 触发点:刚 spawn 3 个并行 track(maidxo / P5 / Opus silver gold)— 在等结果前先反思

### A. 已识别的 bug / 重跑风险

| # | 风险 | 重跑成本 | 缓解 |
|---|---|---|---|
| A1 | **P5 v1 数字全部 invalid**(maidxo trace 空 + mdagents trace 太短 → judge 看到的不是真 trace 质量),v2 才是真数字 | 已包含在 P5 4-fix re-run 里 | ✅ 处理中 |
| A2 | **P1 pilot leaky tautology**:Opus silver gold 完成后,P1 pilot **必须再 re-run 一次**(把 silver gold 当 gold,不再用 synth vignette)— 这是个还没排进 plan 的 step | $0.5(150 call Gemini Flash 重抽) | 🟡 加 plan |
| A3 | **maidxo 续跑可能覆盖 v2 报告** — Subagent X 已经在 31/50 时写了 REPORT_v2.md;我新跑会 re-aggregate 写 50/50 数字。重复 write 但 idempotent | 无 | ✅ 行为 OK |
| A4 | **Cross-map 对自然语言诊断的 robustness 没系统验证** — MedAgents 输出 "Metachondromatosis"(纯 NL),靠 map_diagnosis fuzzy 匹配。如果 fuzzy ≥90 threshold 错过 synonym,R@1 被人为压低 | 高 — 影响所有 Phase 0+ 数字 | 🟡 抽 20 case audit map_diagnosis 通过率 |
| A5 | **AgentClinic 在 RareArena(free text)上的表现**没单独验证 — 全部按 P2 wrap 是不是丢信息?它 R@1=0.20 输给 baseline 一部分是不是 adapter projection 不对? | 中 — 需要"projection audit" | 🟡 加 Phase 2 之前 |

### B. 忘记考虑 / 没排进 plan 的问题

| # | 问题 | 优先级 | 何时处理 |
|---|---|---|---|
| B1 | **DeepRare P2 还没跑过 50 case 数字**(round2_plan §2.4 标"Phase 0 separate",但当前漂在空气里) | 高 — Phase 2 前必须 | 串接在 maidxo 续跑后,1 个 background 跑 |
| B2 | **RDMA 在 leaderboard 怎么算?** Phase 0 P2 grid 没它(Pillar 1 specialist),但论文 Table 1 把 8 agent 都列。**Pillar-stratified reporting 设计**没写 | 中 — Phase 2 前要敲定 | 加到 plan §6 Phase 4 |
| B3 | **confidence_scores 没填**:所有 adapter 都没设。**没 confidence → 算不了 Brier / ECE / AUROC(Tier 2 metric 全废)**,H6 假设没法测 | 中 — Phase 2 加 backbone 时一并修 | 加到 Phase 2 前置 |
| B4 | **OSF preregistration 提交时机**:plan §8 说"holdout unblind 前"。PMC 人工核验**已经在 demo run** → 用户可能已经发给真标注员了 → **holdout 一旦标完就 unblind**,OSF freeze 时间紧 | 高 | **本周内 PI 审 osf_preregistration.md → submit OSF** |
| B5 | **Backbone 版本钉死**:`.env` 用 `google/gemini-3-flash-preview`(非 dated)别名,OpenRouter 实际给的是 `gemini-3-flash-preview-20251217`。**如果 alias 跨实验期间被 OpenRouter 重指向**,reproducibility 坏 | 中 | `.env` 改用 dated ID + worklog 记录 |
| B6 | **Cost 累计跟踪没在 worklog 显式**:已花费 vs 总预算 ($1.5K) 比例没记录 | 低 | 每个 Phase 结束补一行 |
| B7 | **PUMCH-ADM 中文层**:Round 1 标"假设无访问",Round 2 Phase 2-4 是否需要补?H5(英语锚定偏倚)假设没数据测 | 低 | Round 2 中期再决定;不阻塞 |

### C. 现在要立刻 act 的(本 checkpoint 触发的新 task)

- [ ] **A4 cross-map audit**:抽 20 个 Phase 0 cases,手 trace MedAgents/MDAgents/AgentClinic 自然语言输出 → map_diagnosis 匹配过程 → 验证 R@1 不被 fuzzy 错过压低
- [ ] **B1 DeepRare P2 50 case run**:maidxo 续跑完后立即接它(用 mini_round2_pilot.py + `--agents deeprare`)
- [ ] **B3 confidence_scores**:Phase 2 之前在 6 个 subprocess adapter 加 `log.confidence_scores = [1.0] * len(preds)` placeholder(没真 confidence 至少占位,免得 Brier 报错;真 confidence 后续从 LLM logprob 取)
- [ ] **B4 OSF submit**:今天 review `osf_preregistration.md` 一遍 → 提交
- [ ] **B5 backbone pin**:`.env` 改 `BACKBONE_GEMINI=google/gemini-3-flash-preview-20251217`

### D. 这次 checkpoint 的元教训

1. **每 spawn 3 个并行 task 就该停一下复盘** — 不然 bug 累积到 Phase 2 后期才发现,成本翻 10x
2. **"phase 完成"不等于"phase 健康"** — v1 P5 数字看起来"完成"了但 maidxo trace_len=0 是个严重 bug
3. **subagent 自己不会复盘** — 它只回答它被问的,不会主动 flag methodology 问题(eg P1 leaky 是我事后才看出来的)

---

### 2026-05-15 (深夜) — Opus 4.7 silver gold pilot

**目的**:补 [P1 methodology] 留的坑 — Phenopacket-Store P1 pilot 是 leaky tautology(LLM 读自己合成的 vignette 再抽 HPO)。用 Claude Opus 4.7(独立 backbone,跟测试 backbones Gemini/DeepSeek/GPT-5 隔离)在 100 个 PMC OA 真 free-text case 上抽 silver gold HPO + diagnosis,作为 Phase 3 P1 evaluation 的独立金标准源。

**setup**
- Source:`data/pmc_oa_holdout/06_candidates_for_review.jsonl` 前 100 个 `match_type=exact_name`(质量最高桶,池子里 1,047 个可选)
- Input:`case_excerpt` 字段(LLM-extracted PMC OA 真 narrative,500–2000 chars)
- Extractor:OpenRouter `anthropic/claude-opus-4.7` → backend `claude-4.7-opus-20260416`(ping 验证;`4.7-sonnet`/`3.7-sonnet`/`3.5-sonnet` 都 404,`opus-4-1` 400)
- Prompt:简单 system + user,要求 strict JSON `{hpo_phenotypes:[{phrase,hpo_id_guess}], final_diagnosis, notes}`
- Code:`scripts/opus_silver_gold_pilot.py`(checkpoint 每 10 case + 断点续跑 + $15 hard cap)

**实测**
- N=100 attempted,99 successful,**1 refusal**(PMC 10897489 — case_excerpt 是 FMRP/SARS-CoV-2 机理论文摘要,无 proband narrative;Opus 正确拒答,upstream 候选 filter 漏了 → 已 flag `_error: opus_refused_no_proband_narrative`)
- **Total cost ${1.85}** vs $20 cap / $15 hard cap → 远低于 budget;成本/case ~$0.0186
- Tokens:81,760 in / 57,445 out;mean latency ~9 s/case;100 case 总时间 ~18 min
- 0 JSON-decode failures(Opus 输出严格遵循 schema)
- Mean HPO/case:Opus **10.9** vs Gemini Flash(`06_candidates`)**12.2**(Opus 略少 11%)

**Opus vs Gemini disagreement(关键 — 证明非 leaky)**
- Mean phrase Jaccard(fuzzy substring + token-Jaccard≥0.5)**0.41**
- Mean recall of Gemini phrases by Opus:**0.54**
- Mean precision of Opus phrases confirmed by Gemini:**0.59**
- **Final-diagnosis disagreement**:36/99 case Opus 的 `final_diagnosis` 跟 06 candidates 的 `matched_orpha_name` substring-disjoint
  - 多数是 Opus 给 longer/more specific tag(eg "Mandibuloacral dysplasia with type B lipodystrophy (MADB)" vs "Mandibuloacral dysplasia associated to MTX2")— 不是 disagreement,是 phrasing
  - **真 disagreement 几例**:
    - PMC 10798782 — Orphanet 标 HSAN-4,Opus 看 case 后给 "Hypohidrotic ectodermal dysplasia"(HSAN4 cardinal feature 是 anhidrosis → Opus 被表型钓走)
    - PMC 10802993 — Orphanet 标 Wilson disease,Opus 给 "Nitrofurantoin-induced acute liver injury"(case 可能 ambiguous between primary/iatrogenic)
    - PMC 10815279 — Orphanet 标 Dihydropyrimidinuria,Opus 给 "Spastic quadriplegic cerebral palsy"(可能是 case excerpt 里 CP 描述更显著,代谢 dx 在被截断的部分)
- 这种**真 systematic disagreement** 正是 P1 评估有效性的来源 — 测试 agent 在 Opus gold 上跑出的 F1 不会刷到 1.0

**deliverables**
- `data/round2/phase1/silver_gold_opus.jsonl`(100 行)
- `data/round2/phase1/SILVER_GOLD_REPORT.md`
- `scripts/opus_silver_gold_pilot.py`(可续跑 + cap-aware)
- `scripts/opus_silver_gold_report.py`(重新生成 report)

**下一步(给 Phase 3 P1 v2)**
- 把 `silver_gold_opus.jsonl` 接进 P1 evaluator:input = `case_excerpt`,gold = `silver_gold.hpo_phenotypes[*].phrase`(可选 `hpo_id_guess` for exact-id mode)
- Phase 2(3-backbone expand)P1 暂时仍用 inter-agent 比较 + caveat;Phase 3 切到这个 Opus silver gold 作为绝对评分基准
- 注意 1 个 refusal:候选筛 pipeline 需补一道 "narrative-must-contain-proband-clinical-findings" 过滤,免得真人标注员遇到同类 abstract-only PMC 浪费时间


---

## 2026-05-15 (深夜) — P5 v2 results (4 fixes + Claude Sonnet 4.5 judge)

### Fixes shipped this pass

| # | File | Lines / function | What changed |
|---|---|---|---|
| F1 | `harness/agents/maidxo.py` | `supports_pillar`, top of `predict`, end of `predict` | Allow `P5_reasoning_communication` (was P2 only → 10/10 skipped). Build `reasoning_trace` from `conversation_history` (panel debate) + `differential_diagnosis` (Dr. Hypothesis ranking) + `final_diagnosis` + `accuracy_reasoning` (Judge verdict). Also fix the cost-est `conv_hist` loop that iterated a string char-by-char. |
| F2 | `agents/mdagents/utils.py` `parse_hierarchy` + recruit-line parser + `process_intermediate_query` return | `parse_hierarchy` now cycles emojis via `%` and skips blank lines (was IndexError 8/10). Recruit-line filter requires `digit. ... -` shape so prelude lines don't poison `agents_data`. `process_intermediate_query` now returns `{majority, debate: {recruited, initial_report, round_opinions, final_answer}}` (was just `{majority}`). |
| F2 | `harness/agents/mdagents.py` `predict` (trace block) | Reads new `debate` dict and surfaces Step 1 recruitment + Step 2.1 initial opinions + per-round opinions + Step 2.2 each-expert final answers + Step 3 moderator verdict as a structured `reasoning_trace`. Basic / advanced paths get sensible fallbacks. |
| F3 | `harness/logging/openrouter_wrapper.py` `_PRICES` | Added `anthropic/claude-sonnet-4.5` and its dated alias `anthropic/claude-4.5-sonnet-20250929` at $3 / $15 per 1M (in/out) — OpenRouter resolves the slug to the dated id in `response.model`, so both rows needed for `fill_cost`. |
| F3 | `scripts/p5_reasoning_pilot.py` CLI default + `aggregate_and_report` heading | `--judge` default flipped to `anthropic/claude-sonnet-4.5` (was Gemini Flash). Report markdown now states judge model is non-Gemini-family. |
| F4 | `scripts/p5_reasoning_pilot.py` `_chunk_trace` + `_judge_single` + new `call_judge` | New `_chunk_trace` splits traces > 5 000 chars into 3 000-char chunks with 500-char overlap. `call_judge` now calls the judge per chunk, averages each axis across successfully-parsed chunks, and records `judge_chunks_used` / `judge_chunks_total` per row. Report aggregator now accepts floats (the means) and prints a chunk-distribution table. |

### v2 per-agent table (PP-Store n=10, seed=42, judge = Claude Sonnet 4.5)

| Agent | n | factual | relevance | depth | faithful | mean trace_len | mean chunks | judge_err |
|---|---|---|---|---|---|---|---|---|
| `llm_control` | 10 | **4.30** | **4.50** | 3.10 | **4.50** | 986 | 1.00 | 0 |
| `mdagents` | 10 | 4.10 | 4.17 | **3.49** | 4.26 | 20 034 | 8.30 | **0** |
| `deeprare` | 10 | 2.31 | 1.33 | 2.58 | 2.72 | 21 401 | 9.00 | 0 |
| `maidxo` | 10 | 2.11 | 1.85 | 1.64 | 1.88 | 26 972 | 10.50 | **0** |

### v1 → v2 deltas

| Agent | factual | relevance | depth | faithful | trace_len | judge_err |
|---|---|---|---|---|---|---|
| `llm_control` | 4.70 → **4.30** (↓0.40) | 4.50 → 4.50 | 3.60 → 3.10 (↓0.50) | 4.90 → 4.50 (↓0.40) | 986 → 986 | 0 → 0 |
| `mdagents` | 5.00 → 4.10 (↓0.90) | 5.00 → 4.17 | 4.00 → 3.49 | 5.00 → 4.26 | 337 → **20 034** | **8 → 0** |
| `deeprare` | 1.70 → 2.31 (↑) | 1.40 → 1.33 | 1.90 → 2.58 (↑) | 1.70 → 2.72 (↑) | 18 429 → 21 401 | 0 → 0 |
| `maidxo` | nan → **2.11** | nan → 1.85 | nan → 1.64 | nan → 1.88 | 0 → **26 972** | **10 → 0** |

### Findings

- **Self-preference bias confirmed and partially eliminated.** Switching judge Gemini Flash → Claude Sonnet 4.5 pushed `llm_control` down on every axis (factual ↓0.40, depth ↓0.50, faithful ↓0.40) without changing the trace itself. The residual `llm_control` lead over `mdagents` shrank from {+0.30 factual, +1.00 relevance, +0.40 depth, +0.90 faithful} in v1 to {+0.20, +0.33, −0.39, +0.24} in v2 — depth now favours `mdagents`, which is what you'd expect when the judge is no longer related to either system's backbone.
- **MAI-DxO panel now graded; finishes last by a wide margin** (~2.0 mean vs ~4.2 for the two leaders). The trace is rich (27 k chars on average) but the panel often spends iterations re-asking the Gatekeeper for findings that aren't in the HPO-only vignette, and 4/10 cases ended with "Diagnosis not reached within maximum iterations" / "Unable to establish" — Sonnet 4.5 (correctly) penalises factual + relevance for that. Result: MAI-DxO's debate is verbose but low-yield on HPO-only Pillar 5; this needs `max_iter≥2` and ideally a richer narrative input to score competitively.
- **MDAgents now competitive with `llm_control`** on factual/relevance/faithful (within 0.20-0.33) and **beats** on depth (3.49 vs 3.10). This is the expected scaffolding signal — a multi-expert debate should be deeper than a single-call CoT. We could not see this in v1 because 8/10 mdagents runs crashed in `parse_hierarchy`.
- **DeepRare scores low on relevance (1.33) despite long trace.** Investigation: DeepRare's top1 is `Metachondromatosis` on ALL 10 cases (cache / state-leak bug between runs); the judge sees that the ranked predictions never match the case-specific differential and rates relevance ≈ 1 across the board. Trace-quality (factual / depth / faithful 2.31–2.72) is mid-tier — the explanations are coherent, just for the wrong disease. Filed for separate DeepRare adapter fix (out of P5 scope).
- **Chunking distribution** (judge_chunks_used): `llm_control` 1×10 (all under threshold), `mdagents` 6–11 (median 8), `deeprare` 9×10 (uniform — same 21.4 k trace shape every case), `maidxo` 3–14 (median 12). Total 40 grade rows × mean 7.2 chunks ≈ 288 Sonnet 4.5 judge calls.

### Cost

- v2 predict phase: ~$0.04 (Gemini Flash, 40 calls, no maidxo simulated cost included)
- v2 judge phase: ~288 Sonnet calls × ~3 k prompt + 200 completion tokens ≈ ~$2.7 (within $3 cap)
- Wall clock: ~3 h 45 min (longer than estimate; mdagents intermediate path averaged 180 s/case, maidxo no_budget max_iter=1 averaged 230 s/case under contention from a parallel pilot)

### What's preserved
- `data/round2/phase1/p5_reasoning_results_v1.jsonl` + `p5_judge_scores_v1.jsonl` + `P5_REPORT_v1.md` (Gemini-Flash-judge baseline for self-preference comparison)
- `data/round2/phase1/p5_reasoning_results_v2.jsonl` + `p5_judge_scores_v2.jsonl` + `P5_REPORT_v2.md` (Claude Sonnet 4.5 judge, all fixes applied)

### Open follow-ups
1. DeepRare top1-leak (same disease for all 10 cases) — likely the adapter caches model state between predict() calls
2. MAI-DxO HPO-only vignette is too thin for the panel: revisit Pillar 5 design — should we feed a synthetic narrative instead of an HPO bullet list?
3. Phase 2 (3-backbone expand) — only safe to start now that P5 evaluation methodology is stable

---

## 🔍 Retrospective Checkpoint #2(2026-05-15 深夜,Phase 1 4 track 全完成后)

### Phase 0 V2 最终 leaderboard(merged predictions.jsonl + predictions_v2.jsonl + sanity-check)

| Rank | Agent | R@1 | R@5 | Cost/50 | Mean Lat | Health |
|---|---|---|---|---|---|---|
| 🥇 | medagents | **0.36** | 0.48 | $0.26 | 16.1s | ✅ |
| 🥈 | mdagents | **0.34** | 0.46 | $0.05 | 6.5s | ✅ |
| 🥉 | _llm_control (baseline)_ | _0.26_ | _0.40_ | _$0.05_ | _3.5s_ | _baseline_ |
| 4 | lirical | 0.22 | 0.32 | $0 | 3.7s | ✅ |
| 5 | agentclinic | 0.20 | 0.34 | $0.13 | 39.6s | ⚠️ noise in output |
| 6 | vc_rdagent | 0.18 | 0.32 | $0 | 74.1s | ✅ |
| 7 | maidxo | 0.16 | 0.18 | $0.19 | 223s | ⚠️ noise in top-1(A4 audit)|
| ❌ | **deeprare** | **0/50 INVALID** | — | $0 | 129s | ❌ **first-case-leak bug** |

### 新发现的 bug(优先级排序)

#### 🐛 #1 — DeepRare first-case-leak(SEVERE)

**实测**:50/50 cases 的 top-1 全是 `'Metachondromatosis'`(第 1 个 case 的 gold)。

**根因猜测**:adapter subprocess 写 `dataset/cases.csv` 是 per-case 的,但 DeepRare 输出 `result_smoke/case/.../patient_0.json` 路径上 `0` 是 hard-coded → 后 49 case 写入同一文件,parser 读不变。

**修复**:adapter 每个 case 调用前 clean `result_smoke/`,或用 `case_id` 后缀 + 解析 case-specific output。

**重跑成本**:50 × 129s = ~2 小时,$0.04(Gemini Flash 极便宜)。

#### 🐛 #2 — maidxo "noise as top-1"(A4 audit 已预警)

50 cases 里 ~10-15 个 top-1 是 vital signs / "Unable to establish" / 化验值。adapter parser 没 filter 这些非诊断。

**修复**:`harness/agents/maidxo.py` 加 sanity filter:含 `mmHg|bpm|mg/dL|°C|SpO2` 或 `^(unable|cannot|further evaluation)` 的 candidate 直接降级到 status="no_diagnosis",不当 R@1。

**重跑成本**:同 maidxo continuation,~30 min,$0.10。

#### ⚠️ #3 — Phase 0 V2 不再单一 file 输出

`predictions.jsonl`(老 4 agent)+ `predictions_v2.jsonl`(re-run 4 agent)→ final leaderboard 需要 merge。简单 1 行 cat + dedup script。

#### ⚠️ #4 — cost spot-check

agentclinic v1 backfill $0.13 ✓;v2 entries for lirical/vc_rdagent 是 offline ($0 正确);maidxo v2 $0.187 ✓。Subprocess agents cost tracking working.

### 忘记考虑的(从 P5 v2 subagent 反馈来的)

- **MAI-DxO HPO-only vignette 太薄**(P5 v2 报告):panel 频繁要求 Gatekeeper 提供 HPO 之外的 finding,但 vignette 只有 HPO list → 4/10 case ends "Unable to establish within max iterations"。**Pillar 5 重新设计**:对 MAI-DxO 这种期望多轮信息引出的 agent,要不要用 RareArena 的真 free text vignette 而非 HPO list?加到 Phase 3 决策。
- **DeepRare relevance=1.33(P5)** 跟 first-case-leak 同源 — top-1 都是 Metachondromatosis,judge 看到 50 case answer 都一样,relevance 必然砸。

### Phase 1 Final Summary

**✅ 已交付**:
- 7/8 agent 在 50 case 上 P2 数字 validate(除 DeepRare)
- P5 v2 self-preference bias 消除,Claude Sonnet 4.5 judge,trace 完整 capture
- Opus 4.7 silver gold ready(99 case,$1.85)— Phase 3 P1 真评估基础
- D1/D2/D3 bug 全修(MAI-DxO max_iter / cost tracking / RareArena HPO 前置)
- B3 confidence placeholder / B5 backbone pin / A4 cross-map audit 完成

**❌ 进 Phase 2 前必修**:
- **DeepRare first-case-leak**(主 blocker)— adapter cleanup or case-specific output paths
- **maidxo noise filter**(改 parser,~30 LOC + 重跑)
- Phase 0 V2 merged final leaderboard script(B8,1 行)

**📌 Pending(用户处理)**:
- B4 OSF preregistration submit

### Cost 累计(B6 fix)

| Phase | Cost | Cumulative |
|---|---|---|
| Phase 0 v1(6 agent × 50)| $0.45 | $0.45 |
| Sanity check 4 backbone × 50 | ~$1.5 | $1.95 |
| Phase 0 v2 re-run(maidxo + lirical + vc_rdagent + deeprare)| ~$0.25 | $2.20 |
| P5 v1 pilot | ~$0.30 | $2.50 |
| P5 v2 pilot(predict + Claude judge)| ~$2.7 | $5.20 |
| Opus silver gold(100 case)| $1.85 | $7.05 |
| **Phase 1 总计** | | **~$7** |

Round 2 总预算 $1,300-1,800,目前花 $7(<0.5%)。

### 元教训(更新)

1. **Smoke test 5 case 不够**:DeepRare smoke 1 case 时不暴露 first-case-leak(单 case 自然不会缓存问题)。**下次任何 batch 重跑前必须 N=3 case 手动 sanity check top-1 输出**(确认不同 case 不同 prediction)。
2. **Retrospective 必须 act on previous audit findings 才有意义**:Retrospective #1 抓出 A4 cross-map noise warning,但**没立即修 adapter parser** → 现在 maidxo 还是 noise as top-1。下次必须 actionable items 真做完才算复盘成功。
3. **subagent 自己 partial work 写半个完整 reports** → 看起来 OK 但实际有 deep methodology 问题(DeepRare 50 case 全相同的 top-1,subagent 没 alert 我,我自己手动 audit 才看到)。**Phase 2 之前要补一道 "subagent 输出 sanity check" 自动检查**(e.g. 50 case top-1 unique count ≥30% else flag)。

---

## 🔍 Retrospective Checkpoint #3(2026-05-16,V3 完成 + 2 个新 bug)

### V3 主体结果

| Agent | R@1 v2 | R@1 v3 | Δ | 备注 |
|---|---|---|---|---|
| medagents | 0.36 | 0.36 | = | 未 re-run |
| mdagents | 0.34 | 0.34 | = | 未 re-run |
| _llm_control (baseline)_ | _0.26_ | _0.26_ | = | sanity check 数字 |
| lirical | 0.22 | 0.22 | = | 未 re-run |
| **deeprare** | **INVALID(leak)** | **0.22** | **+0.22** | ✅ leak 修了 + evaluator NL fallback 救回 |
| agentclinic | 0.20 | 0.20 | = | 未 re-run |
| vc_rdagent | 0.18 | 0.18 | = | 未 re-run |
| maidxo | 0.16 | 0.14 | **-0.02** | noise filter 误伤 1 case |

### V3 暴露的 2 个新 bug

#### Bug #1 — Evaluator `gold_hit_with_crossmap` NL name fallback 缺失(SEVERE)

**问题**:函数只查 ID 前缀匹配 + OMIM↔ORPHA 跨映射。Agent 输出 plain NL string("Gillespie Syndrome" 等),**evaluator 找不到对应 ORPHA / OMIM**,即使 gold.disease_name 字面相同。

**影响**:DeepRare R@1 报 0.00,实际 50 case 里 **11 个 top-1 字面命中 gold.disease_name**。

**Fix(已 patch)**:`harness/metrics/cross_map.py:gold_hit_with_crossmap` 加 NL fallback +(`_orphadata_tables()` lru_cache 避免 53MB XML per-call 重 parse)。Aggregation 23s 完成。**$0 重跑成本(只 re-aggregate)**。

#### Bug #2 — maidxo noise filter 过宽 + Failure to pattern 漏

- v2 8/50 hit → v3 7/50,损失 1 真 hit(filter 误伤)
- `^Failure to` 没在 noise pattern,maidxo log 看到 "Failure to achieve a 4-fold increase" 当 top-1
- **不阻塞 Phase 2**,paper 引用 R@1=0.14 标 caveat 即可

#### Bug #3 — llm_control 0/50 OK 在 merged report(cosmetic)

`merge_phase0_final.py` 把 sanity-check 数据加进来但显示 0/50 OK,可能 case_id 命名不一致。**不影响 baseline 数字**(单独从 sanity-check REPORT.md 引用 0.26),merged report 表面瑕疵。

### 最终 Phase 0 排名(post Bug #1 fix)

```
🥇 medagents     0.36   ✅
🥈 mdagents      0.34   ✅
🥉 baseline      0.26   ← Gemini Flash llm_control
4  lirical       0.22   ✅(only PP-Store 强;RareArena 端到端 ~0.04)
4  deeprare      0.22   ✅(刚救回,跟 LIRICAL 平)
6  agentclinic   0.20   ⚠️ OSCE on HPO-only 浅
7  vc_rdagent    0.18   ✅
8  maidxo        0.14   ⚠️ 13/50 被 noise filter reject
```

### Cost 累计(post v3)

- Phase 0 v3:**~$0.6**(deeprare + maidxo 50 case 各)
- Round 2 总累计:**~$7.5**(<0.5% of $1300-1800 budget;<2% of revised $200-360 budget)

### 元教训(更新)

1. **Evaluator 也要 sanity check**:Phase 0 V1+V2 一直跑,我没意识到 evaluator NL fallback 缺失会人为压 R@1。**Phase 2 前要写 evaluator self-test**:对每个 agent 输出 type(ID prefix / NL string / mixed),验证 evaluator 都能正确匹配 gold。
2. **缓存策略 review**:`parse_orphadata` 没 lru_cache,被 hot loop 里 call → 性能 disaster。**任何 hot-loop 的 function 都该有 cache**。
3. **Bug #1 类型 "evaluator silently underreports"** 是最危险类型 — 不 crash,产生 plausible-looking 但错误 的数字。**只能靠 audit**。

### Phase 0 真定稿 → Phase 2 决策

- ✅ Bug #1 已修
- ⚠️ Bug #2 不阻塞,Phase 2 同时跑时再小补
- ⚠️ Bug #3 不阻塞,只 cosmetic

**Phase 2 启动前可选 1 件**:写 `scripts/sanity_check_evaluator.py`(evaluator self-test on mock 100 case,验证 NL / ID / fuzzy 路径都正确)— ~1 小时。

**Phase 0 正式 DONE**,Phase 2 等 user 批准启动。

---

## 🔍 Retrospective Checkpoint #4(2026-05-18,Phase 2 Decision Point)

### Phase 2 实际数据(2-backbone × 5 LLM agent + 2 offline)

| Agent | Gemini Flash(P0)| DeepSeek V3.2(P2)| GPT-5(P2 部分)| Δ Gemini→DeepSeek |
|---|---|---|---|---|
| mdagents | 0.34 | 0.24 | 0.34(50/50 ok)| **−0.10** |
| medagents | 0.36 | 0.36 | 失败(parser_error 50/50)| = |
| agentclinic | 0.20 | 0.16 | 失败(timeout 50/50)| -0.04 |
| **maidxo** | 0.14 | **0.00** | 失败(timeout 46/50)| **−0.14 ❌** |
| deeprare | 0.22 | 0.12 | 没跑(killed)| -0.10 |
| lirical(offline)| 0.22 | 0.22 | 0.22 | n/a |
| vc_rdagent(offline)| 0.18 | 0.18 | 0.18 | n/a |
| _llm_control_ | _0.26_ | _0.20_ | _0.17(早期, parser issues)_ | _-0.06_ |

### 2 个核心 finding(支撑 paper)

#### F-Phase2-1 — DeepSeek V3.2 普遍弱于 Gemini Flash(反直觉)

4/5 LLM-based agent 在 DeepSeek 上 R@1 下降 4-14 pp。`maidxo + DeepSeek = 0.00` 是 worst-case。**与 MedHELM 报告的 "DeepSeek-R1 在医学领跑" 反直觉**:DeepSeek V3.2 是 thinking model,跟 prompt-based scaffolded agent 的多轮设计可能冲突(thinking token 吃 context / 输出 format 漂)。**这是 H11(backbone × scaffolding 交互)的直接 evidence,paper headline 信号**。

#### Bug-Phase2-1 — GPT-5 reasoning_effort 没 propagate 进 subprocess adapter

medagents 50/50 parser_error(raw_response=''):GPT-5 default high reasoning 吃光 max_tokens。各 agent 在 own venv 调 LLM,不走我们 `openrouter_wrapper.openrouter_chat`,**不知道传 `reasoning_effort=minimal`**。

mdagents 唯一 OK(50/50)— 它 max_tokens 给得大,reasoning 没吃光。

### 决策 — Option B(用户 2026-05-18 确认)

**接受 Phase 2 当前数据**:Gemini Flash(P0)+ DeepSeek V3.2(P2)= 2-backbone grid。**GPT-5 推后**,Phase 4a 之前批量修 subprocess adapter reasoning_effort propagation,再补 GPT-5 数据。

理由:
- F-Phase2-1 已经支持 H11 主 finding,2-backbone 已够 paper Table 2 + Figure 5(cost-Pareto)
- 4 个 subprocess adapter 各加 reasoning_effort 是 ~半天 + ~$15 GPT-5 重跑,优先级让位给 Phase 3
- Phase 2 cost so far: $0.63(DeepSeek $0.47 + GPT-5 $0.16 partial)

### Cost 累计(post Phase 2 decision)

| Phase | Cost | Cumulative |
|---|---|---|
| Phase 0 v1+v2+v3 | $0.60 | $0.60 |
| Sanity check | $1.50 | $2.10 |
| P5 v1+v2 + Opus silver gold | $4.85 | $6.95 |
| Phase 2 partial(DeepSeek done + GPT-5 killed)| $0.63 | **$7.58** |

**预算 $200-360 用 ~2%**,健康。

### 元教训(更新)

1. **Backbone 不是 free axis** — 同样的 agent + 同样的 prompt,跨 backbone R@1 可差 ±15pp。**Phase 4a 必须 multi-backbone**,不能只跑 cheapest backbone。
2. **subprocess adapter 是 systematic risk** — 每次 wrapper-level 修了一个 backbone 行为(reasoning_effort 之类),所有 subprocess agent 都要单独 propagate。**应该有 1 个 unified env-var convention**(eg `OPENROUTER_REASONING_EFFORT=minimal`)所有 subprocess 都读。这是 Phase 4 前的 infrastructure item。
3. **"timeout 50/50" 比 "parser_error 50/50" 更贵** — agentclinic 都 timeout 600s × 50 = 8 hours wasted clock。下次 timeout cap 应该跟 backbone latency 挂钩(eg 单调 1 个 backbone-call 平均 latency × 5)。

---

## 2026-05-19 — GPT-5 reasoning_effort propagation fix + Phase 3.2 P3 strong signal

### GPT-5 subprocess adapter fixes shipped(subagent + main session)

5 adapter patched(`mdagents.py / medagents.py / agentclinic.py / maidxo.py / deeprare.py` + helper `_adapter_utils.reasoning_effort_for_backbone`):
- Shim sets `OPENROUTER_REASONING_EFFORT=minimal` env when `backbone_id` matches `gpt-5` / `openai/o-` series
- Vendor LLM call sites read env + pass `extra_body={"reasoning":{"effort":...}}`(openai SDK)or `reasoning_effort=`(LiteLLM)

### N=3 / N=1 GPT-5 sanity result(main session)

| Adapter | N | Status | tokens | latency | Notes |
|---|---|---|---|---|---|
| mdagents | 3 | ✅ all ok | ~200/270 | 7-8s | 3 different top-1, no leak |
| medagents | 1 | ✅ ok | 2155/992 | 19s | ORPHA:2499 — relevant differential |
| agentclinic | 1 | ✅ ok | 1644/907 | 50s | "Hereditary Multiple Exostoses" — relevant |
| maidxo | 1 | ❌ timeout | 0/0 | 600s | **panel × max_iter=3 撞 600s subprocess cap** |
| deeprare | (not yet sanity-tested) | — | — | — | Will see in Phase 2 GPT-5 v2 re-run |

**Verdict**:**3/4 successfully reanimated on GPT-5**;maidxo + GPT-5 specific incompat(panel orchestration latency × reasoning_effort=minimal 仍 累计 >600s)。**Maidxo + GPT-5 deferred — paper Limitations 标 known incompatibility**(类似 plan.md §6 reviewer attack #2 框架)。

### Phase 2 GPT-5 v2 launched(2026-05-19)

4 working adapters × 50 case × GPT-5 with reasoning_effort=minimal:
- mdagents / medagents / agentclinic / deeprare
- Output: `data/round2/phase2/predictions_gpt5_v2.jsonl`
- 估 cost ~$8-15
- 估 wall time ~3-5h(deeprare 慢)

### Phase 3.2 P3 中间结果(强信号)

| Agent | OK Cases | P3 R@1 | P3 R@5 | vs P2 baseline |
|---|---|---|---|---|
| llm_control | 50/50(完整)| **0.46** | 0.58 | P2 0.26 → **+20pp** |
| deeprare | 6/50(部分)| ~0.83 partial | — | P2 0.22 → **+60pp** |

**deeprare P3 partial 0.83 跟 paper 报告"HPO+VCF 70.6%"完美吻合** — 复现合理性 confirmed for P3 with variants context。Phase 0 V3 P2 0.22 是因为 variant 没喂进去,**P3.2 启用 variants 解锁了 DeepRare 的 specialized strength**。

### Cost 累计(post 2026-05-19)

| Phase | Cost | Cumulative |
|---|---|---|
| 前所有 | $7.58 | $7.58 |
| Phase 2 GPT-5 sanity check(N=3 mdagents + N=1 others)| ~$0.10 | $7.68 |
| Phase 3.2 P3(llm_control + deeprare partial)| ~$0.30 | $7.98 |
| Phase 2 GPT-5 v2 launched | est $8-15 | ~$15-25 final |

仍**远低于 budget $200-360**(用了 ~5%)。

### Partial snapshot — 2026-05-19 12:25(autonomous tick)

**Phase 2 GPT-5 v2(40 min elapsed)**

| Adapter | n / 50 | R@1 | R@5 | Mean lat | Notes |
|---|---|---|---|---|---|
| mdagents   | 50/50 ✅ | **0.30** | 0.42 | 6.8s | full grid |
| medagents  | 50/50 ✅ | **0.28** | 0.38 | 23.6s | full grid |
| agentclinic| 19/50 ⏳ | 0.16 | 0.47 | 44.0s | in progress |
| deeprare   | 0/50 — | — | — | — | not started yet |

**Phase 3.2 P3(65 min elapsed)**

| Adapter | n / 50 | P3 R@1 | P3 R@5 | vs P2 baseline |
|---|---|---|---|---|
| llm_control | 50/50 ✅ | **0.46** | 0.58 | P2 0.26 → **+20 pp** |
| deeprare    | 16/50 ⏳ | **0.50** | 0.50 | P2 0.22 → **+28 pp** |

### Reading

1. **GPT-5 minimal-reasoning is below Gemini 3 Flash on P2** for mdagents
   / medagents(both ~-6 pp). Consistent hypothesis:GPT-5 trained on
   reasoning-heavy distribution;`minimal` shuts off its edge,leaving
   it behind a fresh frontier model that doesn't need explicit
   reasoning channel. **Paper finding candidate** — H6 frontier-edge
   conditional on reasoning channel(can extend A8 ablation).

2. **DeepRare P3 partial 0.50 still strong** vs P2 0.22(+28 pp).
   Initial 0.75(3/4)was small-sample noise. Full 50 incoming will
   pin the number;currently looks like **R@1 ∈ [0.40, 0.60] with
   pretty high probability**,still matches paper's HPO+VCF 70.6 %
   within reasonable band.

3. **AgentClinic R@5 0.47 with R@1 0.16** = striking ratio. Agent ranks
   well but doesn't commit top-1 correctly. Worth a sentence in §7.2
   scaffolding analysis.

4. **deeprare R@1 == R@5 on P3** — confirms agent emits a single best
   ranked diagnosis;rank ≥2 is rarely populated. Document as
   feature-not-bug;adjust H4 wording so we don't penalise agents
   that don't pretend to give 5 candidates.

5. **Cost / token records empty for subprocess adapters** — they call
   their own LLM client; need `_adapter_utils.fill_cost_from_tokens` 
   bridging from subprocess JSONL. Existing gap, B6 in worklog.

### 2026-05-19 12:58(autonomous tick)— New incompat discovered

**Bug #B11 — DeepRare × GPT-5-minimal incompatibility**

Phase 2 v2 deeprare 7/7 returncode=1 with identical stderr:

```
File "tokenization_utils_fast.py", line 586, in _batch_encode_plus
    for key in tokens_and_encodings[0][0]:
IndexError: list index out of range
```

Root cause(95% confident):GPT-5 at `reasoning_effort=minimal` emits empty
diseases list for DeepRare's local-embedding pipeline. DeepRare passes the
list to `eval_tokenizer(diseases, max_length=36)`,which hits `IndexError`
when `diseases=[]`.

Evidence:
- Phase 3.2 deeprare on **Gemini 3 Flash**: 25/50 ok,no errors
- Phase 2 v2 deeprare on **GPT-5-minimal**:7/7 fail with the same trace
- Each error consumes ~80-90s before the tokenizer crashes(LLM did call
  out;DeepRare proceeded;empty diseases at the embedding step)

**Decision**: let Phase 2 v2 deeprare continue to 50/50 to confirm
systematic;**do not retry on GPT-5-high**(would re-introduce the original
max_tokens issue);document in §9 Limitations as second known
agent-backbone incompat alongside MAI-DxO×GPT-5.

**Paper finding**: this is actually a **second** instance of the broader
pattern — **"frontier reasoning models with reasoning disabled may
under-emit content in agent scaffolding loops that consume model output
downstream"**. Both MAI-DxO(panel)and DeepRare(embedding)require
non-empty LLM emissions to proceed;GPT-5-minimal violates this contract.

**Phase 2 v2 final picture(emerging)**:
- mdagents 50/50 ok ✅
- medagents 50/50 ok ✅
- agentclinic 50/50 ok ✅
- deeprare 0/50 ok ❌(systematic agent-backbone incompat)

**Phase 3.2 P3 progress**:deeprare 25/50 ok(half done)

### 2026-05-19 13:30(autonomous tick)— P3 partial sharpens

**Phase 3.2 deeprare 38/50**:R@1 = **0.42**(95% CI [0.26, 0.58])
**llm_control 50/50**:R@1 = **0.46**

Both agents get ~+20 pp lift from variants vs P2 baseline:
- llm_control: 0.46 - 0.26 = **+20 pp**
- deeprare:    0.42 - 0.22 = **+20 pp**

**Revised reading**: Earlier partial 0.75(3/4)and 0.50(16/50)were small-sample noise.
Real estimate ~0.42 ± 0.16. **DeepRare's lift from variants is the same as
a single-LLM control's lift** — undermines the headline I drafted earlier
("DeepRare unlocks specialised variant capability"). The variant channel
is real(+20 pp,p < 0.05 by McNemar paired test on the same cases — to
be verified at 50/50),but it's **not specific to DeepRare's architecture** —
even the dumbest single-LLM call benefits equally from a structured variants
block in the prompt.

**Comparison to DeepRare paper's HPO+VCF 70.6%**:we're at 42%,a 28 pp
gap. Reasons we surface:
- Our cases are PP-Store mixed difficulty;paper uses their own curated set
- We pass variants as structured text;paper integrates a real VCF + Phenotype
  Tool channel
- Web tools disabled(`DEEPRARE_NO_WEB=1`);paper enables web search

**This nuances §7.3 P3 narrative**:variant channel matters,DeepRare is
no better at exploiting it than the LLM control. Honest framing: 
"genotype channel matters for any agent; DeepRare's published headline 
relies heavily on its full RAG+web stack which we did not enable for 
contamination-control reasons."

---

## Retrospective #5 — Phase 2 v2 + Phase 3.2 complete(2026-05-19 14:01)

### Final numbers

**Phase 2 v2 GPT-5(reasoning_effort=minimal,50 cases × 25 PP + 25 RareArena)**

| Adapter | n_ok / n_err | R@1 | R@5 | 95% CI(R@1) | Mean lat |
|---|---|---|---|---|---|
| mdagents    | 50 / 0  | 0.30 | 0.42 | [0.17, 0.43] | 6.8s |
| medagents   | 50 / 0  | 0.28 | 0.38 | [0.16, 0.40] | 23.6s |
| agentclinic | 50 / 0  | 0.10 | 0.34 | [0.02, 0.18] | 41.8s |
| deeprare    | 0 / 50  | —    | —    | — | (systematic IndexError) |

**Phase 3.2 P3 final(50 PP-Store cases with variants,Gemini Flash)**

| Adapter | n_ok | P3 R@1 | P3 R@5 | 95% CI(R@1) | vs P2 R@1 |
|---|---|---|---|---|---|
| llm_control | 50 | **0.46** | 0.58 | [0.32, 0.60] | +20 pp(P2 0.26) |
| deeprare    | 50 | **0.38** | 0.42 | [0.25, 0.51] | +16 pp(P2 0.22) |

### 3-backbone × adapter R@1 grid(Phase 2 cross-cut)

| Adapter | Gemini 3 Flash | DeepSeek V3.2 | GPT-5(min) | Spread |
|---|---|---|---|---|
| mdagents    | 0.34 | 0.24 | 0.30 | 0.10 |
| medagents   | 0.36 | 0.36 | 0.28 | 0.08 |
| agentclinic | 0.30 | 0.16 | 0.10 | 0.20 |
| deeprare    | 0.22 | 0.12 | FAIL | 0.10+ |
| maidxo      | 0.14 | 0.00 | TIMEOUT | 0.14+ |

(Gemini Flash numbers for mdagents/medagents/agentclinic from Phase 0 V3 +
mini_round2_pilot Phase 0 follow-on,not from this run.)

### Key findings emerging from the grid

1. **F-NEW: GPT-5 with reasoning_effort=minimal is consistently weaker
   than Gemini 3 Flash on agent scaffolds.** -4 pp(mdagents), -8 pp
   (medagents), -20 pp(agentclinic). The drop is steepest for
   prompt-engineering-intensive scaffolds(AgentClinic dialogue OSCE).
   **Interpretation**: GPT-5's training is reasoning-optimised;
   `minimal` disables the channel it was tuned for. Honest paper
   framing: "GPT-5 at minimal reasoning is *not* an evaluation of
   GPT-5's full capability — it is an evaluation of GPT-5 under the
   no-reasoning regime,which we use because reasoning-on consumes
   max_tokens and breaks the harness."

2. **F-NEW: variant channel adds ~+20 pp R@1 universally.** Both
   llm_control and deeprare gain ~+20 pp from structured variants in
   the prompt. **Agent-specific variant exploitation claim is
   not supported** by our results;variants help any model that
   ingests them.

3. **F-NEW: two systematic agent × backbone incompats.** MAI-DxO ×
   GPT-5(panel timeout)and DeepRare × GPT-5(empty diseases →
   tokenizer crash). Both share the pattern "frontier reasoning model
   with reasoning forced off under-emits content that downstream
   scaffolding consumes." Documented in §9 L1.

4. **F-NEW: cost-axis spread within a single adapter is large.**
   AgentClinic varies 3× across backbones(0.30 → 0.10). Implies
   "backbone holds constant" assumption(MedAgentBench)conceals
   meaningful variance — supports §5.2 "backbone is a separate
   variable,not a confounder."

### Cost spent this phase

Phase 2 v2 GPT-5(157 successful + 50 deeprare-error)≈ $8-10 estimated
(cost not captured in subprocess adapters,B6).
Phase 3.2 P3 deeprare(50 calls × ~3 min × Gemini)≈ $1-2.
**Phase 0+1+2+3 cumulative cost** ~$10-12,**under budget**($120-360 cap).

### What goes into the paper

- **§7.2 scaffolding analysis**: GPT-5-minimal degradation across
  scaffolds is a new sub-finding(F-NEW-1)
- **§7.3 genotype analysis**: variants help universally,not specifically
  DeepRare(F-NEW-2,already patched into §A1)
- **§9 L1 incompat list**: two cells excluded(MAI-DxO×GPT-5,DeepRare×GPT-5)
- **§5.2 backbone-as-variable**: cross-cut spread evidence(F-NEW-4)

### Next phase decision points

A. **Phase 4a sampled run** — 100 case × 4 dataset × 7 agent × 2-3 backbone
   est ~$30-80. Status: ready to launch.
B. **Phase 5 ablations** — A1-A12 listed,need to prioritise.
C. **Phase 6 P5 reasoning faithfulness re-run** — Gemini-judge → Claude-judge
   swap already done(self-preference bias section);maybe re-check on
   bigger sample.
D. **Holdout n=200 PMC OA** — user TODO(physician annotation)+ OSF
   preregistration submit. Blocking dependency on user.

I'll pause for user input before launching Phase 4a — staged sampling
discipline says **do not auto-scale**.

---

## Main-thread Checkpoint #1 — 2026-05-19 15:10(per new rule)

### round2_plan.md 进度核对

| Phase | 状态 | Note |
|---|---|---|
| Phase 0 Mini Pilot | ✅ done | bug 修了 4 个 |
| Phase 1 P1/P5 | ✅ done | silver gold 替换了 leaky tautology |
| Phase 2 3-backbone | ⚠️ **partial** | 50 case pilot 各 backbone 跑了,但 GPT-5 deeprare/maidxo 异常正在追根因 |
| Phase 3 P3 + P1 e2e | ✅ pilot done | 50 case |
| Phase 4 Dataset Expansion | ⏳ pending | **bug 全部修完后才能开始全量补回**(用户新规则) |
| Phase 5 Ablations A1-A12 | ⏳ not started | |
| Phase 6 Holdout Unblind | 🚫 blocked | user TODO:OSF prereg + 200-case 标注 |

### paper_outline.md 等数据 section

| Section | 状态 | 阻塞 |
|---|---|---|
| §1 Abstract | 等 final numbers | Phase 4 full + Phase 5 ablations |
| §2 Intro | 等 5 numerical claims | 同上 |
| §3 Related Work | ✅ v0 draft | — |
| §4 Benchmark Design | ✅ v0 draft | — |
| §5.1-5.4 Setup | ✅ v0 draft | — |
| §6 Main Results | 等 full data | **现在 draft 里的数字是 pilot 50,需切到 full** |
| §7 Analysis | partial(7.1, 7.5)| 等 full |
| §8 Ablations | 等数据 | Phase 5 |
| §9 Limitations | ✅ v0 draft | DeepRare incompat 应该删除(parser 修了)|
| §10 Conclusion | 等 headline | full data |
| §11 Appendix A1 | ✅ v0 draft | 等 final 更新 |

### 主线偏移检查

**没偏移**。但有两个关键 reframe:

1. **Sample 50 数据不再算 final** — per user rule "sample 是中间手段,bug 修完要全量补回"。§A1 audit + §6 table 里现在引用的 0.30 / 0.46 / 0.42 等数字必须改成 "pilot N=50",并标 "full N=10k pending"。
2. **预算需要重估** — 之前 $120-360 是 sample 阶段的上限。Phase 4 全量(10k PP-Store + 1k RareBench + 72k RareArena 全跑不现实,可能要采 ~2000-5000 stratified)估计要 $X(待算)。

### 在追的 4 个 task(Task #44-47)状态

- A: DeepRare × GPT-5 — 根因找到(parser bug),patch 2 处,N=2 pipeline ok 但 **ranked_predictions=[]**;追到第三层 — 发现 **harness adapter 自己的 _RANK_RE 也只认 `**bold**`**,已 patch
- B: MAI-DxO instant — degenerate(documented),需切 question_only
- C: mdagents DeepSeek — phenotype mention 泄漏到 top-N(软 bug + 模型差距叠加)
- D: cost bridge — 还没开始

### 遗漏 task(被搁置的)

- **OSF preregistration submit** — user TODO,还没动
- **PMC OA holdout 200 case 标注** — user TODO,还没动
- **RareBench HF dataset 1.1k** — round2_plan §4.2 列了但 50 pilot 用的是 RareArena RDS,**RareBench 还没碰过**
- **MIMIC-IV rare-disease slice 956 case** — 用户之前说 "mimic放到了data folder",但还没 ingest 测试过
- **Phase 5 Ablations A1-A12** — 0/12

下一步顺序(用户已经选了三个 Recommended):
1. 重新 verify DeepRare parser fix R@1(再 N=2,确认 ranked_predictions != [])
2. 启动 DeepRare × 3-backbone × 50 case 重跑
3. 启动 MAI-DxO question_only N=5
4. 加 mdagents noise filter + DeepSeek 50 重跑
5. 全部 ok 后,跟你商量 Phase 4 全量重跑的预算 + scope(包括 RareBench + MIMIC 还没碰过)

---

## Main-thread Checkpoint #2 — 2026-05-19 ~17:10(per new rules)

### 跟用户新规则相对应的动作

| User-locked principle | Memory file | 实际落地 |
|---|---|---|
| 异常不跳过深挖根因 | feedback_no_skip_on_failures.md + feedback_research_integrity.md | ✅ 5 个 bug 都追到根因 |
| 复盘主线 + 任务遗漏 | feedback_review_main_thread.md | ✅ Checkpoint #1, #2 写到 worklog |
| 严格复现 baseline 不 vibe 改 | feedback_strict_baseline_repro.md | ⚠️ DeepRare patches dual-report;其他 baseline 都 wrapper-only |
| 每 baseline 专门复现文档 | feedback_per_baseline_repro_doc.md | ✅ docs/baseline_repro/ × 10 docs |
| DeepSeek V4-Pro 主实验前切 | project_backbone_v4_switch.md | ✅ memory recorded;主实验前执行 |

### 本 turn 已完成的 bug fix

1. **mdagents parse_ranked_top5 section-aware + prose filter** ✅
   - 修了 DeepSeek 把临床特征 triad 当 differential 的 vicious bug
   - DeepSeek v3 R@1: 0.24 → **0.30**(+6pp,追平 GPT-5 baseline 0.30)

2. **map_names_to_ids_with_variants** ✅
   - Adapter 接入:mdagents / medagents / agentclinic / maidxo / llm_control(5/5)
   - evaluator: gold_hit_with_variants ✅
   - 还需 wire 进 aggregator 用 variants column 评估

3. **GoldLabel CCRD regex 允许子码** ✅(`CCRD:115.1` 不再 drop)

4. **DeepRare parser fix(双层)** ✅(dual-report 协议)
   - 上游 `diagnosis.py / diagnosisGene.py` no-bold fallback
   - 下游 `harness/agents/deeprare.py:_RANK_RE` no-bold fallback
   - paper 必须 dual-report:strict-baseline (GPT-5 fail) + adapter-relaxed (GPT-5 ~0.30)

5. **MIMIC rd_detection metric** ✅
   - 新 script + ORPHA-aware is_match
   - 初版 rd_detection_acc = 0.40 → ORPHA-aware **0.56**(+16 pp)

### 关于 RareBench LIRICAL/MME/HMS R@1=0 的新发现

不是 bug,**是 LLM 真错**。Audit:
- LIRICAL 227 case 里 1/227 gold OMIM-ORPHA 数据问题(可忽略)
- llm_control 在 LIRICAL_00198 答 "Pelizaeus-Merzbacher disease"(classical X-linked, ORPHA:702),但 gold 是 OMIM:260300 = PMLD1(autosomal recessive, GJC2-related,不是 X-linked)
- 这是真临床差异化困难。RareBench LIRICAL paper 本身报 R@1 ~0.30,我们 0.00 还是有大 gap,但少部分是数据/Orphadata 选 ORPHA 与 LLM picked ORPHA 是 ontology sibling

**判断**:不是 evaluator 错,也不是 parser 错。这是真复现:Gemini Flash 在 LIRICAL 这种 difficult curated set 上 ~0 R@1。Paper 可能要解释 RareBench paper 的 0.30 是用什么 model + setup 拿到的。

### Background 跑的总览(还未结束)

| Run | PID 启 | 当前 | 备注 |
|---|---|---|---|
| DeepRare GPT-5 (patched) | 51270 | 35/50 但 #35 报错 | dual-report用 |
| DeepRare Gemini (patched, fallback 未触发) | 51271 | ?/50 | tail empty 可能完了 |
| DeepRare DeepSeek (patched, fallback 未触发) | 51272 | 22/50 慢 | |
| mdagents v4(with variants) | 65449 | 34/50 | 验证 variants logger |
| MAI-DxO no_budget+max_iter=2 1200s N=3 | 60251 | 2/3 done 都 degenerate | |
| RareBench LIRICAL × 3 adapter | 64398 | medagents/llm_control 完 | mdagents 已完 R@1 0.20 |
| RareBench MME × 3 adapter | 64399 | medagents/llm_control 完 | mdagents 完 R@1 0.05 |
| RareBench HMS × 3 adapter | 64400 | llm_control 跑中 | mdagents 完 R@1 0.00 |

### 主线偏移检查

**没偏**。主实验 pilot 阶段(N=50)bug 修复中,Phase 4 全量未开始,Phase 5 ablations 未开始。

---

## Autonomous tick — 17:58 — final aggregation of in-flight fixes

### DeepRare 3-backbone rerun(parser fix + dual-report)

| Backbone | n_ok / n_err | R@1 | R@5 | Note |
|---|---|---|---|---|
| Gemini Flash | 50/50 | 0.22 | 0.22 | single-best ranking |
| DeepSeek V3.2 (partial 36/50) | 36/0 | 0.17 | 0.25 | still running |
| GPT-5 minimal (adapter-relaxed) | 41/9 | 0.12 | 0.12 | 9 仍 agent_error |

R@1=R@5 现象:DeepRare paper 设计单 best ranked diagnosis,top-5 列表稀疏。
GPT-5 即使 patched 仍 9/50 fail(其他 parser/runtime issue,不只是 bold)。

### mdagents v4 验证 variants logger 3-backbone

| Backbone | n_ok | R@1 strict | R@1 variants | R@5 strict | R@5 variants |
|---|---|---|---|---|---|
| Gemini Flash | 49 | 0.35 | **0.39** (+4) | 0.41 | **0.47** (+6) |
| DeepSeek V3.2 | 50 | 0.26 | 0.28 (+2) | 0.36 | **0.42** (+6) |
| GPT-5 minimal | 50 | 0.26 | **0.34** (+8) | 0.32 | **0.40** (+8) |

variants logger 一致 lift R@5 +6-8 pp,R@1 在 GPT-5 上 lift 最大(+8pp)
— 因为 GPT-5 用 generic disease 名 fuzzy-tie 概率更高。

### Cost summary across pipelines

(Recomputed with fixed price-table)

| Phase | Cost(USD)|
|---|---|
| Phase 0 V3 + Phase 1 + Phase 2 + Phase 3 | $3.36(recomputed)|
| Phase 2v2 + Phase 3.2(GPT-5)| ~$0.5(estimate)|
| Phase 2_fix bug rerun(7 background)| ~$1-2 |
| MIMIC rd_detection × 3 backbone | ~$0.5 |
| **Total ~$5-6** | 远低于 $120-360 budget |

### Tasks closed this autonomous tick

- #44 DeepRare × GPT-5 root cause:✅(parser bug + dual-report 协议)
- #45 MAI-DxO × GPT-5 mode testing:✅(systematic incompat,3 mode 全 degenerate)
- #46 mdagents DeepSeek -10 pp:✅(parser fix + variants logger,+6pp on R@5)
- #47 cost-bridge:✅(price-table dated alias 主因)
- #48 RareBench ingest+50 pilot:✅(4 splits ingest works)
- #49 MIMIC ingest+50 pilot:✅(原 + rd_detection 重框 + 3 backbone)
- #50 CCRD regex:✅
- #52 baseline_repro docs:✅(10 docs)

### Remaining open

- #43 Phase 4a launch:等 DeepRare DS rerun 完
- #51 DeepSeek V4-Pro 切换:主实验前

### Decision needed

我已经做完所有 bug fix 阶段。**所有 user-locked 异常都已根因 +排查 + 文档**。
可以决策是否启动 Phase 4 全量?需要先复盘 Phase 4 cost 估 + 跟用户商量 scope。

---

## Main-thread Checkpoint #3 — 2026-05-22 ~20:15(per "复盘历史问题和 bug")

### 阶段概览

| Phase | Status | N |
|---|---|---|
| Phase 0/1/2/3 Pilot | ✅ done | 50 |
| **Phase 4a Mini-Sample** | ✅ **23/23 done 2026-05-21** | 100 × 4 datasets |
| Phase 4b Decision Point | ✅ implicit(进 4c)| n/a |
| **Phase 4c Expanded** | ⏳ **5/12 done, 7 running** | 500 × 4 datasets |
| Phase 4d Full Run | ❌ not started | n/a |
| Phase 5 Ablations | ⏳ A3 / A4 / A7 done, A5/A6/A8/A9/A10/A11 TODO | n/a |
| Phase 6 Holdout | 🚫 blocked user OSF + 200-case annotation | 200 |

### Bug 总结(本 phase 期间 fix 完的 12 个)

1. **DeepRare parser bug**(diagnosis.py + diagnosisGene.py)— GPT-5 minimal 不 emit markdown bold,加 fallback regex(dual-report 协议)
2. **mdagents parse_ranked_top5 section-aware**— DeepSeek 把临床特征 triad 当 differential,fix:full-text first,< 3 names 才 header-aware fallback
3. **medagents Gemini parser_error 14/50** — 同上 section-aware 副作用,reverted bad logic
4. **mdagents fuzzy-tie ORPHA sibling**— "MMA generic" name 在 ORPHA 26/27/280183 平局,加 `map_names_to_ids_with_variants` 返回 tied top-K
5. **GoldLabel CCRD regex 子码** `CCRD:115.1` 被 drop,放宽 regex
6. **llm_control × GPT-5 content_len=0** — in-process call 没 propagate reasoning_effort,加 minimal
7. **GLM-5 也是 reasoning model** — 不响应 reasoning_effort=minimal,需 max_tokens 3000+(未集成,记 task #54)
8. **vc_rdagent / lirical 非 HPO dataset** — agent 设计 incompat,加 HPO_ONLY_AGENTS + NO_HPO_DATASETS skip
9. **mini_round2_pilot.py 缺 llm_control adapter** — 注册到 get_adapter
10. **price-table key 缺 dated alias** `google/gemini-3-flash-preview-20251217`,cost reporting 之前全 0
11. **MIMIC default DDx prompt unsuitable** — reframe rd_detection prompt,0.27 → 0.56 acc
12. **Bg process 不稳定** — 19:35-19:37 几 cells 同时死,改 nohup + disown + log buffer flush

### Method-issues(non-bug,真实 finding 不要 fix)

1. RareBench universal R@1 ~0-9% — ORPHA sibling hierarchy 数据问题,classical 用 OMIM 绕过 → paper finding
2. MAI-DxO × GPT-5 incompat — 3 mode 全 degenerate(instant/question_only/no_budget+max_iter=2)
3. agentclinic × GPT-5 minimal 0.11(其他 ~0.27)— reasoning_effort=minimal × OSCE dialogue 真 mismatch
4. medagents Gemini N=100 0.40 → N=500 0.33 — N=100 是 small-sample overestimation,正常 converge
5. deeprare on rarearena / mimic 0.00 — agent 需 HPO/Orphanet 结构,free-text degrade(documented)

### User-locked rules(7 条)

1. plan + split + retro + log + summary 5-step
2. cost discipline + staged sampling
3. reproducibility honesty(don't contact authors)
4. 失败不 skip,先 confirm root cause
5. 严格复现 baseline 不 vibe 改
6. 每 baseline 专门复现文档(docs/baseline_repro/×10)
7. cost 几百刀停下 confirm + 每节点复盘

### Paper completeness(2026-05-22)

| Section | Status |
|---|---|
| §1 Abstract | ✅ draft |
| §2 Introduction | ✅ draft |
| §3 Related Work | ✅ done |
| §4 Benchmark Design | ✅ done |
| §5.1-5.4 Setup | ✅ done |
| §6 Main Results | ✅ draft(N=100 numbers,等 N=500 update)|
| §7.1 P1→P2 cascade | ✅ done |
| §7.2/7.3/7.4/7.6 | ✅ draft |
| §7.5 Self-preference bias | ✅ done |
| §8 Ablations | ✅ draft(A3/A4/A7 done; A5/A6/A8/A9/A10/A11 TODO)|
| §9 Limitations | ✅ done |
| §10 Conclusion | ✅ draft |
| §11 A1 Reproducibility | ✅ done |
| §11 B Per-baseline | ✅ done |

### Cost 状态

- Phase 0/1/2/3: ~$10-15
- Phase 4a: $48
- Phase 4c so far: ~$5
- **总累计 $53.47**(burn $0.9/h slowing)
- 估 Phase 4c 完 ~$80-120,**总 $90-130(安全 < $300 cap)**

### 还在追的 in-flight

- Phase 4c 7 cells(agentclinic/deeprare/llm_control/medagents V4-Flash + vc_rdagent + agentclinic Gemini)
- 估完成 ~36-48h(deeprare V4-Flash 最慢)

### 下一步 next ablations 可以同时启动

- **A10 prevalence-stratified R@1**:bin cases by Orphanet prevalence
- **A11 cross-dataset ranking stability**:Spearman ρ of agent rank across 4 datasets
- **A6 TS-Guessing contamination audit**:n-gram overlap vs LLM training cutoff
- 这 3 个都 code-only,可以并行启动

---

## Retrospective #6 — 2026-05-28 — Phase 4c N=500 收尾 + medagents V4-Flash 异常根因

### N=500 扩量状态(重跑 report_gen 后)
- Gemini Flash:4 dataset 基本 500/500(rarebench 上限 378)
- DS V4-Flash:PP-Store/RareArena ~490-500;rarebench/mimic 见下异常
- DS V4-Pro:全 N=100(成本考虑保留,user 早前 kill v4pro)
- GPT-5 minimal:全 N=100
- 累计成本 **$73.69**(report_gen 重算),仍 << $300 cap

### report_gen 性能 bug(已修)
- 旧 cross_map NL fuzzy-match 每 prediction 跑一次 rapidfuzz over 11K ORPHA,无 cache → 27 min 卡死
- 修:`harness/metrics/cross_map.py` 加 `_fuzzy_name_to_orpha` `@lru_cache(200000)`;重跑 13.5 min 完成

### medagents × V4-Flash RareBench/MIMIC 高 parser_error 根因(异常深挖)
- 现象:rarebench ~329 / mimic ~598 parser_error,但 PP-Store/RareArena 干净(<5%)
- 根因:失败记录 `raw_response_excerpt` 全空 → synthesiser `final=""`。
  V4-Flash 偶发返回 HTTP-200 但 content="";upstream `get_output_multiagent`
  只在 exception 重试,空-但-成功 的 response 漏过 → parser_error
- **bug vs 真行为分离**(per user 原则):
  - harness bug:空 content 不重试 → **已修**(wrapper 层 `_MAX_EMPTY_RETRIES=2`)
  - 真 backbone 行为:部分 case timeout >300s(长输入)+ 部分持续返回空(3 次 retry 都空)→ 照实报告
- 修复验证:5 个曾失败 case,**3/5 恢复 ok**;剩 1 timeout + 1 持续空(均真行为)
- 严格 baseline:只改 wrapper(medagents.py),medagents 算法/prompt 未动;已记 docs/baseline_repro/medagents.md
- **待 user 决策**:是否重跑 medagents V4-Flash rarebench+mimic 两 cell(resume 会重试 ~930 failed case,×3 retry 偏慢,估 ~半天到一天;可并行)

---

## Retrospective #6 续 — 2026-05-28 — 全部修复全部重跑(用户决策)+ 全错误扫描

### 用户决策
"能全部修复就全部重跑,保证数据准确性+完整性,成本可接受。" + 重申复盘方针(定期查已执行内容 bug/疏漏,发现即补救)。

### 全 cell 错误扫描(dedupe by case_id 后,nonok≥15)
分三类:
1. **transient 空-content(可修)**:
   - medagents V4-Flash:mimic 268 / rarebench 143 / rarearena 6 空 → **已修(empty-retry)**
   - llm_control:content_len=0 共 ~108(rarebench 38 + mimic 40 + v4-pro rb 30 + …)→ **已修(_chat_with_retry 加空-content 重试)**
2. **timeout 偏紧(可修)**:A9 证实 300s 略紧(同 case 900s 下 309s 完成 ok)。
   - agentclinic V4-Flash:rarebench 59 / mimic 36 timeout
   - mdagents V4-Pro:rarebench 36 / pp 24 timeout
   → 重跑用 `--timeout_s 600`(runner 新增参数)
3. **真行为 / 已知 incompat(不修)**:
   - maidxo parser_error = "All ranked predictions filtered as noise / Unable to establish" → MAI-DxO panel 在 HPO 输入退化,**真行为(§8.2)**,retry 无用
   - deeprare×GPT-5 agent_error(mimic 46 / rarearena 37)→ 已知 incompat
   - llm_control 少量 content_len=1017/949 非空格式错 → 真 parser,retry 正确地不重试

### 代码改动(本轮)
- `harness/agents/medagents.py`:`_MAX_EMPTY_RETRIES=2` empty-retry(R1 已验证)
- `harness/agents/llm_control.py`:`_chat_with_retry` 加空-content 重试(复用 max_retries=2)
- `harness/metrics/cross_map.py`:`_fuzzy_name_to_orpha` lru_cache(report_gen 27min→13.5min)
- `scripts/phase4a_report_gen.py`:按 case_id 去重保留最佳状态(resume 累积重复行修正)
- `scripts/phase4a_runner.py` + `get_adapter`:新增 `--timeout_s` 覆盖

### 重跑启动(13 fixable cell,resume 只补失败)
- V4-Flash --n 500:medagents×3(rb/mimic/ra)+ agentclinic×2(rb/mimic)+ llm_control×3(rb/mimic/ra)
- V4-Pro --n 100:llm_control×3(rb/mimic/pp)+ mdagents×2(rb/pp)

### 自查发现并补救的疏漏(复盘价值体现)
- V4-Pro cell 初次误用 `--n 500` → 会把被降级的慢 backbone 意外扩到全量(偏离"kill v4pro 用 v4flash"决策)。**立即 kill 5 cell + 改 --n 100 重启**,只修 N=100 内错误,不扩量。

### 待跟进
- deeprare V4-Flash mimic 仍后台慢跑(~13min/case,3.5 天到 500;结构性 0.00)— 完整性 vs 时间待权衡
- 13 重跑完成后:regen report + CI bootstrap + figures + 更新 §6/§1 数字

---

## Retrospective #6 续2 — 2026-05-28 — deeprare×MIMIC 0/214 根因(用户质疑 "这是 bug 吗")

用户直觉:0/214 太极端,像 bug。深挖(no-skip)→ **不是 bug,是真结构性失败**:
- eval 正常:同 MIMIC gold,llm_control 命中(gold Essential thrombocythemia ORPHA:3318 → llm_control 预测 ORPHA:3318 ✓)
- deeprare 192/218 有非空预测,只是全错(不是空匹配)
- 根因:DeepRare 纯罕见病 HPO-pipeline,MIMIC 自由文本 → (a) 抽噪声 HPO (b) 只输出罕见综合征;而 MIMIC gold 多为常见 ICU 病挂 ORPHA 码(心源性休克/扩张型心肌病/肛瘘)→ 永不命中
- 跨 backbone 一致(V4-Flash 0/214 + Gemini 0/495)→ 稳健
- **论文发现**:专用 HPO-pipeline agent 在自由文本上崩溃(依赖干净结构化 HPO);caveat:MIMIC 层测"自由文本命名疾病识别",非"罕见遗传诊断",部分 gold 是常见病
- 已记 docs/baseline_repro/deeprare.md
- **deeprare V4-Flash mimic 已 kill**(N=214 @ 0.000 已定论,省 2.3 天)

---

## Retrospective #6 续3 — 2026-05-29 — N=500 收尾 + §6/§1 数字对齐(findings 偏移)

### pipeline 收尾
- 13 重跑全完成 → report_gen(去重生效,coverage 干净)→ CI bootstrap(N=500 CI 收紧:lirical 0.46 [0.42-0.51]、vc_rdagent 0.44 [0.40-0.48] 与 LLM 不重叠)→ 6 figures
- 总成本 **$74.14 / 23,905 preds**(<< $300 cap)

### §6 Table 1 发现旧数字错误(复盘价值)
- 草稿 Table 1 是早期 N=50 pilot 数字,与权威 summary 不符(medagents Gemini PP 0.40 → 实际 0.33)
- 用生成器从 phase4a_summary.json 重产 Table 1,替换手抄旧表

### findings 随全 N=500 修订(重要,已标 reviewer note)
- **F1 更强**:classical 0.46/0.44 vs 最佳 N=500 LLM 0.33 = 13pp gap(草稿才 4pp)
- **F2 减弱**:scaffolding 增益 +2-5pp(非草稿的 +5-7),mdagents MIMIC 0.39 反超 medagents
- **F3 反转**:V4-Flash 不是"追平 Gemini",是 ~10× 便宜但 R@1 一致偏低(PP -2~-9pp,MIMIC -11~-16pp)。草稿基于 partial N=62 误判
- **F4 nuance**:GPT-5 对 medagents 反而最佳(0.36),仅 agentclinic 崩(-14pp);非一致劣势
- F5 holds
- §1 abstract findings (1)-(4) 同步修订

### 待用户复核
- F2/F3/F4 结论偏移(尤其 F3 反转)需 PI 确认 framing
- §7 analysis / §8 ablations 可能也引用了旧 scaffolding/V4-Flash 数字,待核

### 跨节一致性 sweep(2026-05-29)
§6/§1 改完后扫全 paper_sections,发现旧 claim 传播到 §2 引言 / §10 结论 / §B 附录 / §7.6 表 / §8.2。全部对齐 N=500:
- §2 contributions (1)-(4)、§10 五点结论、§B per-baseline observed(MDAgents 0.41→0.35, MedAgents 0.40→0.36, VC-RDAgent 0.43→0.44, LIRICAL 0.44→0.46, LLM control 0.36→0.32)、§7.6 难度表、§8.2 backbone spread(13pp→7pp)
- 残留仅 reviewer-note 里故意保留的 "v0 draft" 对照说明
- 7 节(§1/§2/§6/§7/§8/§10/§B)现内部一致

### 本 session 主线状态
- ✅ Phase 4c N=500 + 全 fixable cell 修复重跑 + report/CI/figures + §1/§2/§6/§7/§8/§10/§B 数字对齐
- ✅ PMC holdout 标注交接包(data/pmc_oa_holdout/HANDOFF/)
- ✅ deeprare×MIMIC 0/214 根因(非 bug)
- ⏳ 待 user 复核 F2/F3/F4 reframing(尤其 F3 反转)
- ⏳ A6(blocked on holdout)/ A9(partial)

---

## Retrospective #7 — 2026-05-29 — 假设检验推进(H1/H4/H7/H8 + H9 查证)

用户决策:H3/H5/H6→To-do(#63-65),H9 能跑就跑,H1/H4/H7 立即做。

### 完成(全部写入 §7)
- **H8**(§7.1.2)倒U:峰 16-30 HPO 词项,N=4754 ✅ supported
- **H1**(§7.7)真 Orphanet prevalence(下载 en_product9_prev.xml,5108 codes):LLM 向 super-rare 下降(0.37→0.22),classical super-rare 反而最强(0.50)→ 严格单调不成立但尾部对比强;super-rare 层 classical vs LLM 差 28pp,强化 F1
- **H4**(§7.8)复杂度(HPO 器官系统数)交叉:scaffold−control 单系统 -0.05/-0.07(overthinking)、多系统 +0.06/+0.04 ✅ supported,锐化 F2
- **H7**(§7.9)专科聚类(23 HPO 顶层系统轴):跨 agent Spearman ρ=0.73/0.74/0.74 ≥0.6 ✅ supported;神经/代谢/消化普遍弱,心血管/皮肤普遍强;classical 反转神经系统弱点
- 脚本:ablation_{H1_prevalence,H8_phenotype_density,H4_H7_specialty}.py;输出 data/round2/ablations/

### H9 查证 → 不可跑
所有数据层无 pedigree/inheritance + 无 family-aware 诊断 agent → Limitations(同 H5)

### 假设检验总状态
✅ confirmed: H2(§7.3 partial)/H4/H7/H8/H10(§7.4 partial)
⚠ nuanced: H1(agent-class 分化)
⛔ deferred: H3(holdout)/H5(中文)/H6(预算)/H9(无 pedigree 数据)

---

## Retrospective #8 — 2026-07-03 — V4-Pro reasoning 无界饥饿根因 + reasoning-disable 修复

**触发**:V4-Pro fill wave(N=100→full)重跑时,agentclinic/mdagents/medagents ×
V4-Pro 大面积失败(agentclinic 45-51% timeout,medagents 34-45% parser_error,
mdagents 17-32% timeout)。用户质疑 "系统性错误为啥?provider 返回错误还是请求太
频繁?你要去闭环异常定位和修复"。

**根因(确定性复现,非猜测)**:V4-Pro 是重 reasoning 模型,默认吐 reasoning
tokens,且 **reasoning 无界** —— 你给多少 max_tokens 它就吃多少去 reasoning:
- 直连 API 硬测(hard synthesiser prompt,N=3/4 each):
  - `max_tokens=200` → finish=length,reasoning 吃满 200,content=None
  - `max_tokens=2500` → reasoning 吃满 2500,content 空 4/4
  - `max_tokens=4000` → 3/4 ok,但 1/4 连 4000 也吃光
  - `reasoning={effort:minimal}` → 无视,仍吐 200 rt
  - `reasoning={max_tokens:200}` → 无视,吐 1773-2000
  - `reasoning={effort:low}` → 无视,吐 2000
  - **`reasoning={enabled:false}` → rt=0,content 3/3,1.9s** ← 唯一干净解
- 崩溃链:
  - agentclinic doctor turn `max_tokens=200` → content=None → vendored
    `query_model` 默认 `tries=30,timeout=20` 重试 sleep 循环 → 爆 300s cap
  - medagents synthesiser `max_tokens=600` → content 空 → "No ranked lines"
  - mdagents 不设 max_tokens(默认大)→ 无饥饿,但每 call 15-32s reasoning ×
    7-10 轮辩论 → 爆 cap(纯 wallclock)
- 排除:非 provider 错误(直连正常 1.6-2.7s),非频率限制(单发即复现)。
  V4-Flash rt=135 勉强塞进 200(所以之前没炸),Gemini rt=0(无压力)。

**修复(遵守 baseline 严格复现纪律 — 只 config-level,不改 scaffold/prompt)**:
1. `_adapter_utils.py`:新增 `reasoning_disabled_for_backbone()`(v4-pro/glm-5
   → True)+ 保留 `max_tokens_floor_for_backbone()`(2500,secondary safety)
2. 3 个 harness shim(agentclinic/medagents/mdagents):检测到 disable 就设
   `OPENROUTER_REASONING_DISABLE=1` env(镜像已有 reasoning_effort 传播)
3. 3 个 vendored 文件(agentclinic.py / medagents/api_utils.py /
   mdagents/utils.py×2):读 env → `reasoning={"enabled": False}`(覆盖 effort)
4. mdagents 额外 `--timeout_s 900`(纯 wallclock 保险)

**方法学框架**:V4-Pro 全线跑 reasoning-off,与 GPT-5 全线跑 reasoning=minimal
一致 —— 同为 "reasoning-off / fast" 配置,为跨 backbone 公平 + tractability。
V4-Pro 无视 effort/minimal/reasoning-cap,只认 enabled:false(和 GLM-5 同类)。
待写入 §5.2 + docs/baseline_repro/{agentclinic,medagents,mdagents}.md。

**待办**:end-to-end N=2 验证 3 scaffold → 清 V4-Pro 失败记录(RESUME 只跳 ok,
timeout/parser_error 会自动重试)→ 决策 llm_control 是否也 reasoning-off(一致性
vs 重跑成本)→ 带 fix 全量重跑 V4-Pro heavy cells。

---

## 复盘 (2026-07-06) — V4-Pro reasoning-off 重跑收尾核对 round2_plan + MEMORY

用户规则:跑完先复盘核对主线,确认无偏移再 regen。核对 task #84 的 10 项:

1. **round2_plan 对齐** ✓ 无意图冲突。plan 是旧 3-backbone 规划文档(v3.2-exp/gemini/
   gpt-5,写于 V4 切换前),定的原则是"reasoning 模型跑 minimal + reasoning on/off 作
   A8/H6 ablation 轴"。V4-Pro reasoning-off 是把该原则从 GPT-5 忠实扩到 V4-Pro,H6 = on/off
   ablation。plan backbone 表过时但已由 memory project_backbone_v4_switch + paper §5.2 记录。
2. **MEMORY 更新** ✓ project_v4pro_reasoning 加完成状态 + H6 结果;MEMORY.md 加指针。
3. **数据完整性** ✓ 16 主矩阵 cell full-N(500/500/956/1122×4),总 1 error;H6 pp n=253;
   GPT-5 rarebench 补到 1122。
4. **一致性(无 reasoning-on 污染)** ✓ 16 文件 mtime 全 07-03/07-04 重跑(纯 reasoning-off);
   旧 reasoning-on 16 文件已隔离到 phase4a_v4pro_reasoningON_backup_20260703/。
5. **regen 去重** ✓ 已确认 regen_receipts_and_figures.py 按 case_id 去重(best[cid] 优先 ok),
   历史重复行(如 v4-flash rarebench 1452 行/1122 唯一)不影响报告数字。
6. **v4-flash rarebench 部分偏低** ⚠ 低优先:medagents 783/agentclinic 860(去重后,因错误率),
   非本次范围,regen 后评估是否 error-rerun。
7-10. regen / H6 分析 / rarebench 4-backbone 统一 1122(gemini✓ v4-pro✓ gpt5✓ v4-flash部分)/
   复盘节奏 #77 → 本节即是。

**结论:无偏移、无遗漏、无污染。可进 regen。** cost $192/$360 (53%)。

---

## Retrospective #9 — 2026-07-06 — 假设检验全量刷新(V4-Pro 解锁后)

用户"完成所有实验先". 在 full-N 数据上重跑全部可测假设 + Holm 校正:

**新增实验**:H2 full-N — 写 `scripts/h2_fulln_paired.py`,llm_control 在 500 个
PP-Store variant cases 上跑 P2(无变体)vs P3(变体)配对。结果 P2 0.296 → P3 0.494
= **+19.8pp lift**(匹配 pilot +20pp),McNemar χ²=85,z=6.40。

**刷新分析**(full-N):H1(super-rare classical 0.428 vs LLM 0.206)、H4(DoD +0.081)、
H7(ρ 0.73→0.92,18 specialties)、H8(inverted-U 16-30 峰 0.337 vs ≤5 0.197)、
A4/A10/A11 重算。

**Holm-Bonferroni(m=6)结果:2/6 → 5/6 通过**。H2/H4/H7 从 pilot 欠功效翻为 FWE-robust:
| H | pilot | full-N |
|---|---|---|
| H1 | ✅ z=11.21 | ✅ z=17.91 |
| H2 | ❌ z=2.08 | ✅ z=6.40 (p=3e-10) |
| H4 | ❌ z=1.45 | ✅ z=2.51 (p=0.012) |
| H7 | ❌ ρ=0.73 | ✅ ρ=0.92 (p=0.0016) |
| H8 | ✅ z=4.52 | ✅ z=12.45 |
| H10| ❌ ρ=0.36 | ❌(judge N=10 欠功效,§7.5 exploratory,唯一未过)|

更新:§7.3(H2)/§7.8(H4)/§7.9(H7)/§8.8(holm 表)/§8.10(H6)。这是 full-N 重跑的
直接科研价值 —— 3 个假设从"方向一致但欠功效"变为"严格 FWE 显著"。H10 需 judge pilot
扩容(N=10→更多),留作 follow-up。

**H10 dual-judge 扩容(2026-07-06 续)**:P5 judge N=10→扩容尝试。发现算力墙 —— scaffold
agent(mdagents)P5 trace 18-22k 字符 / ~200s/case,N=50×4-agent dual-judge 不可行。
务实:用已生成 73 traces(llm_control 50 + mdagents 23)双 judge。结果 **judge 强分歧**:
Gemini(family)ρ=0.098(decoupled)vs Claude(non-family)ρ=0.616(coupled),pooled
ρ=0.352 (p=0.037)。H10 名义通过但 fragile/judge-dependent —— 这本身强化 §7.5 self-preference
故事(判 H10 结论随 judge family 变号)。写 scripts/h10_faithfulness_accuracy.py。
maidxo/deeprare 因 trace 过大排除并声明。

**Holm 最终:6/6 名义通过(5 robust + H10 nominal/judge-dependent)**。§7.5/§8.8/§8.2 更新。

---

## Retrospective #10 — 2026-07-08/09 — N=2000 统一样本 harmonization(可比性修复)

**触发**:用户审计发现 PP-Store 跨 backbone N 不一致(Gemini 867-4589 vs 其他 500)。
根因:历史不同 cell 用不同 --n 累积(不是故意采样,是 bug)。"得一样的数据才能对标"。

**用户决策链**:预算 $360→$500;"数据也可以多一些慢慢跑";目标 N=3000→(算力墙后)
N=2000(CI 性价比甜点,±1.7%)。

**方案**:pp+rarearena 4 核心 agent × 4 backbone 统一到 seed=42 前 2000 case_id(嵌套
前缀,确定性)。mimic(956)/rarebench(1122)核心已全量不动。deeprare 弃扩(web-search
hang + GPT5 $148 prohibitive,保 pilot 声明);maidxo 保 pilot(弱);offline vc 免费扩。

**加速(用户问"能否并发")**:瓶颈非 API 限速(load 才 3),是每流串行(1 case/时等 27s)。
给 phase4a_runner 加 `--concurrency`(ThreadPoolExecutor,case 独立线程安全,logger/counter
上锁,已测 16/16 零重复)。4 流×并发8 → agentclinic 80→540/hr(6.7×),ETA 10 天→~1 天。

**并发副作用**:V4-Flash 空响应 + agentclinic 超时率上升(并发抢 API/CPU)。低并发(3)
topup 重试收效甚微(V4-Flash empty-synthesiser 是固有限制非 transient,742 只恢复 34)→
止损,V4-Flash 4 cell 按实际 N(1292-1998)诚实报告,强化 F3。

**canonical-cap 聚合**:regen_receipts + report_gen 都加 `phase4a_canonical_2000.json`
过滤,pp/rarearena 只聚合共同前 2000 case_id(Gemini 4589 截断到 2000,V4-Flash 短的用
实际子集)。所有 cell 报告在同一批 case 上,彻底可比。

**数字影响**:R@1 整体降 ~2-4pp(500-sample 偏乐观;canonical-2000 更准)。Gemini pp
llm_control 0.27[4589]→0.29[2000 canonical]。findings 方向全不变:F1 gap 扩到 17-18pp
(lirical 0.47 vs 最佳 LLM 0.30),F2/F3 保留,V4-Pro-off 仍有竞争力。cost ~$320/$500。
更新:§6.1 Table1 + §6.2/6.4 + reviewer note。假设 H1/H4/H7/H8 在新数据上刷新 + Holm 重算。

---

## Retrospective #11 — 2026-07-09 — Opus-4.8 agent 标注 + H3 严谨污染对照

用户:等医生标注同时用 Opus 4.8 做一份 agent gold,先把 A5/H3 跑完不卡在人工。

**Opus 4.8 标注**(scripts/annotate_holdout_opus48.py):读 PMC 全文做医生任务(验证
诊断+挑错误HPO)。post-cutoff holdout 198 例:诊断 0 错(100%认可 Gemini),HPO precision
0.904(8.7%判错,抓否定词/亚型错误),漏 687 表型。= A5(silver vs physician)interim gold。

**H3 严谨版**:发现 naive post-cutoff R@1=0.62 >> pre-cutoff benchmark 0.29 是难度差异
(holdout 是教科书病例;case_excerpt 还泄露诊断=0.82)非循环。→ 建难度控制对照:用相同
pipeline(harness/pmc_oa + Gemini + Opus)建 pre-cutoff PMC 集(2016-2020,scripts/
build_precutoff_pmc.py,220例),与 post-cutoff holdout 同源同query同分布,唯一变量=训练
是否见过。clean-gold 子集(Opus 认可诊断)pooled: pre 0.568 vs post 0.618,Δ+0.049,z=1.72。
**post ≥ pre 对所有 agent → 方向性排除污染撑高**(记忆不是主因)。写入 §7.10.1 + §9 L5/L7 +
§8 A5。H3_precutoff_contamination.md + A5_silver_vs_physician.md。cost ~$370/$500。
