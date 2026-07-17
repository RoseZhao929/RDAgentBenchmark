# Round 2 Plan — From Mini Pilot to Full Main Experiment

> **基础假设**:Round 1 已完成(8 agent verified, harness ready, PMC候选池 1,433, MIMIC 切片 956, OSF 草稿)。GPT-5 用 `reasoning_effort="minimal"` 可用(2026-05-14 验证)。
>
> **设计原则**:
> 1. **先 Mini 后 Full** — 50 例先验证 8 agent × 1 backbone 端到端,再 expand
> 2. **每个 Phase 之间有"复盘 checkpoint"** — 不堆 bug
> 3. **依赖驱动并行/串行**:无依赖必并行,有依赖才串行
> 4. **Cost-aware**:每个 Phase 标 token + USD 估算
>
> **目标论文**:EMNLP submission,plan.md §8 主实验完整实现

---

## 1. 全局依赖图(决定并行/串行)

```
                        Round 1 ✅
                            │
              ┌──── PMC 人工核验(独立串行,标注员)
              │
              ▼
        ┌───────────┐
        │ Phase 0   │  Mini Pilot — 8 agent × Gemini Flash × 50 case × P2
        │ (1-2 天)  │  目标:验证管线 + 揪 adapter 解析 bug
        └─────┬─────┘
              │ 复盘 ① — bug fix / 阵容调整
              ▼
        ┌───────────┐
        │ Phase 1   │  Bug Fix + Pillar P1 / P5 单 agent 验证
        │ (1-2 天)  │  非依赖:P1 / P5 各自独立
        └─────┬─────┘
              │ 复盘 ②
              ▼
        ┌───────────┐
        │ Phase 2   │  3-backbone expand — × 8 agent × 50 case × P2
        │ (2-3 天)  │  并行:DeepSeek V3.2 / GPT-5 / Gemini Flash 独立 backbone
        └─────┬─────┘
              │ 复盘 ③ — Cost-Pareto 初判
              ▼
        ┌───────────┐
        │ Phase 3   │  Pillar 3 (基因型感知) + Pillar 1 (端到端抽取)
        │ (2-3 天)  │  并行:P1 / P3 互不依赖
        └─────┬─────┘
              │ 复盘 ④
              ▼
        ┌───────────┐
        │ Phase 4   │  Dataset 扩展 — RareArena 大规模 + MIMIC 956 + Phenopacket
        │ (1 周)    │  并行:每个 (agent, backbone, dataset) cell 独立
        └─────┬─────┘
              │ 复盘 ⑤
              ▼
        ┌───────────┐
        │ Phase 5   │  Ablations A1-A12
        │ (1-2 周)  │  绝大多数并行 / 部分用 Phase 4 日志事后重算
        └─────┬─────┘
              │
              │  ← PMC 人工核验 200 例完成 + OSF freeze submit
              ▼
        ┌───────────┐
        │ Phase 6   │  Holdout unblind + final report + leaderboard
        │ (1 周)    │
        └───────────┘
```

**关键依赖**:
- Phase 0 → 1 → 2:**串行**(每个 Phase 验证下一步前提)
- Phase 3 vs Phase 2:Phase 3 strictly 后(P3 用 P2 已 verified adapters)
- Phase 4 → 5:Phase 5 部分 ablation 复用 Phase 4 日志
- Phase 6 ← PMC 人工核验:**外部依赖**,人工核验进度不阻塞 Phase 0-5 主流程

---

## 2. Phase 0 — Mini Pilot(优先级最高,blocker)

### 2.1 Goal

**1-2 天内**回答 3 个核心问题:
1. 8 个 adapter 在 50 个真实 case 上**都能跑通**吗?(不是 1-2 个 smoke case)
2. 它们的 P2 (phenotype DDx) Recall@1 比 Gemini Flash baseline (0.26) **高 / 低 / 持平**?
3. 哪些 adapter 有 parser bug / timeout / format edge case?

### 2.2 Setup

- **Dataset 样本**:复用 sanity-check 的 50 例(25 PP-Store + 25 RareArena RDS,seed=42)— 同一个 sample 可以直接跟 Gemini Flash R@1=0.26 对比
- **Backbone**:**只用 Gemini 3 Flash**(便宜 + 已验证 + 是所有 adapter 测试基准)
  - 例外:LIRICAL 不需要 backbone(Java),VC-RDAgent 默认 offline Stage 1
- **Pillar**:**只 P2(phenotype-only DDx)**
- **Eval mode**:`gold_hpo`(PP-Store 用 case.gold_hpo_terms 直接;RareArena 用 free text 包装)

### 2.3 Step 拆分

```
P0.1 (脚本)    写 scripts/mini_round2_pilot.py — 8 agent × 50 case × Gemini Flash 主循环
P0.2 (验证)    跑 1 例 dry-run 每个 adapter 验证 wire-up
P0.3 (运行)    后台跑全量(~1-3 小时,取决于 DeepRare 速度)
P0.4 (聚合)    aggregate metrics + 写 mini_pilot_REPORT.md
P0.5 (复盘 ①) 跟我 review 报告,讨论 bug + 调整下一步
```

### 2.4 单 case 估时 / 估成本 / 风险

| Agent | 估时/case | 估 cost/case | 风险点 |
|---|---|---|---|
| `llm_control` (Gemini Flash) | 3-5s | $0.0001 | 已 verified ✅ |
| MDAgents (intermediate path) | 2.5min | $0.001 | timeout 设 5min |
| MedAgents (5-stage) | 50s | $0.005 | ~10 LLM call |
| AgentClinic (OSCE) | 35s | $0.005 | dialogue 浅,HPO-only case 可能输出弱 |
| MAI-DxO (instant) | 12s | $0.0005 | instant 模式短路,**用 `no_budget` max_iter=1 替代**(74s, $0.005)|
| DeepRare (no-web + local embed) | 130s | $0.01-0.04 | bge embedding 已 fallback,但 ~20-40 LLM call |
| RDMA (Pillar 1 only) | 5s | $0.0001 | **P2 不支持,本 phase 跳过** |
| VC-RDAgent (Stage 1 offline) | 80s | $0 | 0 LLM call,纯 offline |
| LIRICAL (Java) | 8s | $0 | 0 LLM call |

**总估时**:8 agent × 50 case avg ~60s/case = 4 小时单线程,**实际 4-6 小时**(含 retries)。
**总估 cost**:~$1.5 一轮 mini pilot(8 agent × 50 case @ Gemini Flash)。

### 2.5 Bug 预期 & checkpoint 列表

每个 adapter 在 50 例上**必查**:
- [ ] Parser regex 在 50 例 LLM 输出格式 variance 下 robust 吗?(目前只测过 1-2 例)
- [ ] subprocess timeout(默认 600s)够吗?DeepRare 有可能超
- [ ] Pillar 2 + gold_hpo 模式接收 RareArena 的 free text 时,投影正确吗?
- [ ] Cost / latency 在 PredictionLog.cost 里填对了吗?
- [ ] status="ok" 真的 ok?还是 silently returned empty?
- [ ] 50 例里 fail 率多少?>5% 算 bug

**复盘 ① 必带 5 个数字**:
1. 每个 agent 的 R@1 (PP-Store + RareArena 合)
2. 每个 agent 的 fail rate
3. 每个 agent 的 mean latency
4. 每个 agent 的 total cost
5. Gemini Flash baseline R@1=0.26 — **几个 agent 真的 beat 这个?**

### 2.6 我现在能马上写的脚本

`scripts/mini_round2_pilot.py`(基于 `scripts/sanity_check_pilot.py` 扩展):
- 加 `--agents` 参数指定要跑哪几个
- 加 timeout / fail-fast / 增量 resume
- 输出格式同 sanity_check

确认要写 → 我立即开工。

---

## 3. Phase 1 — Bug Fix + P1/P5 单 agent 验证

### 3.1 Goal

修 Phase 0 暴露的 bug + 验证 Pillar 1 (extraction) 和 Pillar 5 (reasoning/communication) 在**支持的 agent** 上能跑通(只挑代表性 agent 1-2 个,不全量)。

### 3.2 P1 / P5 哪些 agent 支持 / 不支持(参考 RUN_REPORT)

| Agent | P1 支持 | P5 支持 | 备注 |
|---|---|---|---|
| llm_control | ✅(LLM 抽 HPO phrase) | ✅(reasoning_trace) | — |
| MDAgents | — | ✅(recruiter+moderator trace) | P2-focus |
| MedAgents | — | ✅(per-expert + chief MO synthesis) | P2-focus |
| AgentClinic | — | ✅(dialogue trace) | OSCE 风格,trace 长 |
| MAI-DxO | — | ✅(8-role panel trace) | |
| **DeepRare** | ✅(40+ 工具,HPO 抽取是其管线一环)| ✅(full 6-field reasoning JSON)| ⭐ 多 pillar |
| **RDMA** | ✅(**Pillar 1 specialist**) | — | mining 输出 phrases,需 HPO normalization |
| VC-RDAgent | — | — | 只 P2 |
| LIRICAL | — | — | 只 P2 |

**Phase 1 选择跑**:
- **P1**:llm_control + DeepRare + RDMA(3 个)— 跑 50 例 PP-Store(已有 gold HPO 作 ground truth)
- **P5**:llm_control + MDAgents + MAI-DxO + DeepRare(4 个)— 跑 10 例 PP-Store,人工 / LLM-judge 评 reasoning trace 质量

### 3.3 Step

```
P1.1   修 Phase 0 暴露的 adapter bug(具体清单视复盘 ① 而定)
P1.2   写 harness/metrics/hpo_normalization.py — phrase → HP:xxxxxxx
       (用 hp.obo + Orphadata 词典 + Gemini Flash refine — 给 RDMA / llm_control 输出做下游归一化)
P1.3   写 scripts/p1_extraction_pilot.py — 3 agent × 50 PP-Store × Gemini Flash
P1.4   写 scripts/p5_reasoning_pilot.py — 4 agent × 10 PP-Store + LLM-judge rubric
P1.5   复盘 ② — P1 F1 + P5 judge score
```

并行:P1.3 ‖ P1.4(完全独立)。

### 3.4 估时 / 估成本

- P1.1 bug fix:1-2 天(取决于 ①)
- P1.2 normalization:0.5 天(已有 hp.obo + cross_map)
- P1.3 P1 pilot:50 × 3 = 150 LLM call,~$1
- P1.4 P5 pilot:10 × 4 = 40 trace + 40 judge call,~$1

---

## 4. Phase 2 — 3-Backbone Expansion(主实验的"宽度"维度)

### 4.1 Goal

把 Phase 0 的 50 例 × 8 agent **复制到 3 个 backbone**,产出 A3 backbone × scaffolding 2×N 网格的 mini 版数字。

### 4.2 Backbone 阵容(.env 里都已经配好,Phase 0 之后 freeze)

| Backbone alias | OpenRouter ID | 价格(in/out per 1M)| Phase 0 已验证? |
|---|---|---|---|
| `BACKBONE_CHEAP` | `deepseek/deepseek-v3.2-exp` | $0.27 / $1.10 | ✅(sanity-check)|
| `BACKBONE_MID` | `google/gemini-3-flash-preview` | $0.50 / $3.00 | ✅(sanity-check)|
| `BACKBONE_FRONTIER` | `openai/gpt-5` | $1.25 / $10.00 | ✅(GPT-5 fix:reasoning_effort=minimal)|

注意:LIRICAL / VC-RDAgent (offline) 没 backbone,跳过 backbone axis。
**有效阵容**:6 LLM agent × 3 backbone + 2 non-LLM agent = 20 行(symmetric to plan.md §2 的"20 行 leaderboard"格式)

### 4.3 Step

```
P2.1   把 scripts/mini_round2_pilot.py 改成 take --backbone 参数
P2.2   分 3 个 backbone 后台 nohup 跑(并行)
P2.3   aggregate to mini_phase2_REPORT.md
P2.4   复盘 ③:Cost-Pareto 图初判 — 哪个 (agent, backbone) 是 Pareto 前沿?
```

### 4.4 估成本

50 case × 8 agent × 3 backbone = 1,200 runs(去掉 non-LLM 实际 ~900)。

- DeepSeek $0.01/case avg = $9
- Gemini Flash $0.0005/case avg = $0.5
- GPT-5 (reasoning=minimal) $0.02/case avg = $18

**Phase 2 total budget: ~$30-50**

### 4.5 Bug 预期

- **GPT-5 输出格式不一样**(o-style reasoning 模型可能多用 markdown / 序号风格)— parser 要在 GPT-5 上 re-verify
- **DeepSeek V3.2 上 RareArena Chinese / English 差异**?(若有)
- 不同 backbone 的 cost 自动计算 — `_PRICES` 表覆盖全(已 verified)

---

## 5. Phase 3 — Pillar 3 (基因型感知) + Pillar 1 (端到端)

### 5.1 Goal

3 个 pillar 维度都跑通:
- P1(端到端 HPO 抽取)— 验证我们的"双 pass"评估
- P3(基因型感知,需 VCF 或 structured variants)— 这是我们 benchmark 的**头号差异化**

### 5.2 Pillar 3 数据源限制

唯一有 structured variant + ACMG 信息的是 **Phenopacket-Store**(我们 ingest 时已经 parse 进 `case.variants`)。

P3 评估只能在 **PP-Store 子集**上做,自然 limit。其他数据集 P3 fall-back 到 "HPO-only" 评估(等价 P2)。

### 5.3 哪些 agent 支持 P3(参考 RUN_REPORT)

| Agent | P3 支持 |
|---|---|
| DeepRare | ✅(`pillar="P3_genotype_aware"` 已实现,vignette + variant 拼接)|
| llm_control | ⚠️(prompt 加 variant info,but no specialized variant reasoning)|
| LIRICAL | ⚠️(有 VCF 接口但需要 Exomiser bundle,我们当前 LIRICAL install 没装)|
| 其他 5 个 | ❌ |

**Phase 3 P3 阵容**:DeepRare + llm_control(2 个),50 例 PP-Store(预留 30% 有 variant 信息的)

### 5.4 Step

```
P3.1   P1 端到端 pilot:8 agent × 25 RareArena RDS (有 free text, 无 gold HPO)
         — P1 输出 → P2 输入 → 跟 P2 gold_hpo mode 对比,看 P1→P2 端到端 delta
P3.2   P3 pilot:DeepRare + llm_control × 50 PP-Store × 3 backbone
         — 输出:Pillar 3 R@1,比 P2 R@1 高吗?(预期 H2 DeepRare ≥20pp gain)
P3.3   复盘 ④
```

并行:P3.1 ‖ P3.2(独立 pillar + 独立 agent)。

### 5.5 估成本

- P3.1:25 × 8 = 200 calls × Gemini Flash ≈ $0.5
- P3.2:50 × 2 × 3 = 300 calls × Gemini/DS/GPT5 ≈ $5

**Phase 3 total: ~$10**

---

## 6. Phase 4 — Dataset Expansion(staged sampling,2026-05-16 修订)

### 6.1 Goal — 修订后

**先 sample 后扩**:不直接跑全量 ~5K case,先**每个 dataset 100 case mini sample** 看趋势,再 informed decision 决定是否扩到 representative subset / 全量。

### 6.2 三阶段 staged sampling

#### **Phase 4a Mini Sample**(必跑,budget ~$50-80)

| Dataset | Sample 大小 | 抽样方式 | 重点 pillar |
|---|---|---|---|
| RareBench HF(4 splits)| **100**(stratified, 25/split) | 等比例 | P2 |
| Phenopacket-Store | **100**(per-disease cap 1) | seed=42 | P2 + P3 |
| RareArena RDC | **100**(stratified by Orphanet ID) | seed=42 | P2 |
| MIMIC-IV diverse | **100**(stratified) | seed=42 | P2 |

**总 cell**:400 case × 8 agent × 3 backbone = 9,600 calls。混合 backbone 成本估 **$50-80**(DeepRare 20-40 call/case × 100 case × 3 backbone 是大头)。

预计 wall time:~24-36h(可并行 backbone)。

#### **Phase 4b Decision Point**(复盘 ⑤ 触发,no spend)

读 Phase 4a 结果后**user-PI 决策**:
- 如果 Phase 4a 已经支持 H1-H11 多数假设(eg agent ranking 稳定 + per-dataset 差异显著 + prevalence stratification 趋势可见)→ **跳过 Phase 4c**,直接进 Phase 5(ablations)
- 如果 Phase 4a 数字 noisy(eg agent 排名跨 backbone 不一致 / pillar 差异不显著)→ Phase 4c 扩到 500 case/dataset
- 如果发现新 bug → 修 + 再 Phase 4a

#### **Phase 4c Expanded Sample**(decision-driven, optional)

只跑被 Phase 4a 标记为 "需要更大 sample 才能稳定" 的特定 (agent, dataset, pillar) 切片。**不是全量**。

预算情景:
- **Optimistic**(4a 数字稳定,跳过 4c):$0 — Phase 4 总成本 ~$80
- **Median**(4c 扩 2 dataset × 400 case)= 6,400 calls × $0.005 avg = $32 → Phase 4 总成本 ~$110
- **Pessimistic**(4c 全部 dataset × 500 case)= 16,000 calls × $0.005 = $80 → Phase 4 总成本 ~$160

#### **Phase 4d Full Run**(only if camera-ready or specific reviewer 要求)

仅在最终论文 review 阶段,reviewer 明确 push back 时做。**默认不跑**。

### 6.3 Step(revised)

```
P4a.1  写 scripts/phase4a_stratified_sample.py — 4 dataset × 100 case 抽样
P4a.2  scripts/phase4a_main_runner.py(asyncio + per-backbone parallel)
P4a.3  3 backbone × 4 dataset × 8 agent 后台并行,wallclock ~24-36h
P4a.4  aggregate to phase4a_REPORT.md
P4a.5  复盘 ⑤ + 与 user 决策 Phase 4b/4c
```

### 6.4 估成本(修订)

| Sub-phase | Cells | Cost(estimated)|
|---|---|---|
| Phase 4a Mini Sample | 9,600 | **$50-80** |
| Phase 4b Decision Point | 0 | $0 |
| Phase 4c Expanded(optional) | 0-16,000 | $0-$80 |
| Phase 4d Full(only if needed) | up to 120K | up to $1,500(deferred) |
| **Phase 4 total(staged baseline)** | | **$50-160** |

vs 原 $1,100-1,500 → **节省 ~85%**

### 6.5 风险(revised)

- **N=100 太小,假设检验 underpowered** — 但 Phase 4a 不是终点;期望 Phase 4a 揭示哪些 (agent, pillar, dataset) 差异显著,Phase 4c 针对扩
- 其余风险同原版

---

## 7. Phase 5 — Ablations A1-A12

### 7.1 Goal

跑 plan.md §5 列的 12 个 ablation,每个回答一个 reviewer-anticipated 问题。

### 7.2 Ablation 分两类

**A. 新跑 ablation**(需 fresh runs):
- A1 DeepRare 模块 on/off
- A2 multi-agent depth
- A4 rare disease ontology on/off
- A5 reasoning-mode on/off(**GPT-5 minimal vs low vs high**)
- A7 few-shot vs zero-shot
- A8 input format (gold HPO / agent-extracted / free-text)
- A9 genotype channel
- A10 family channel
- A11 cost-cap sweep
- A12 LLM-judge vs exact match

**B. 后处理 ablation**(复用 Phase 4 日志):
- A3 backbone × scaffolding 网格(已经是 Phase 4 副产品)
- A6 pre/post-cutoff split(需 PMC 人工核验 200 例 ready)

### 7.3 Step

```
P5.1   12 个 ablation 各自的脚本:scripts/ablations/A{i}_*.py
P5.2   并行跑 — 大多数 ablation 用 50-200 case 子集
P5.3   复盘 ⑥ —  每个 ablation 一个 forest plot
```

### 7.4 估成本

每个 ablation 100-500 calls 级别 × 12 = ~3000 calls extra ≈ $50.

**Phase 5 total: ~$100**(主要重跑的)

---

## 8. Phase 6 — Holdout Unblind + Final Report

### 8.1 Pre-conditions(blocker)

- [ ] PMC 200 例人工核验完成(`07_curated_holdout.jsonl` 存在)
- [ ] OSF preregistration 已 timestamp submit(在 holdout 跑评估之前)
- [ ] Phase 4 完成 + adapters 稳定

### 8.2 Step

```
P6.1   把 holdout 200 例当 5th dataset layer 加入主 grid(8 agent × 3 backbone × 200 = 4,800 calls)
P6.2   做 A6 pre/post-cutoff 差分分析(用 Phase 4 数据当 "pre",holdout 当 "post")
P6.3   跑统计:Holm-Bonferroni 校正 H1-H11
P6.4   生成 leaderboard static site
P6.5   写论文主结果章节
```

### 8.3 估成本

P6.1:4,800 × mixed = ~$50

---

## 9. 总预算估算 + 时间线(2026-05-16 staged sampling 修订)

| Phase | 工作量 | 估时(墙钟)| 估成本(revised)| 实际 spend |
|---|---|---|---|---|
| 0 Mini Pilot | 6 agent × 50 case × 1 backbone | 1-2 天 | $2 | **$0.45 ✓** |
| 1 Bug + P1/P5 pilot + Opus silver | bug fixes + 2 pillar pilot + silver gold | 1-2 天 | $5-10 | **$6.60 ✓** |
| 2 3-backbone expand | 50 case × 7 agent × 3 backbone | 2-3 天 | $5-30(staged) | TBD |
| 3 P3 + P1 端到端 | 50-100 case 子集 | 1-2 天 | $5-15 | TBD |
| **4 Dataset staged sampling** | **4a Mini 100/dataset → 4b Decision → 4c Targeted(可选)** | **3-5 天** | **$50-160**(was $1,100-1,500)| TBD |
| 5 Ablation 12 项 | small subsets per ablation | 1-2 周 | $30-80 | TBD |
| 6 Holdout + 论文 | 200 holdout case + 写稿 | 1 周 | $20-50 | TBD |
| **总(revised)** | | **4-6 周** | **$120-360**(was $1,300-1,800) | $7 to date |

**节省主因**:Phase 4 staged sampling(原 $1,100-1,500 → $50-160)+ 各 phase 收紧 sample 大小。

**如果实验中段需要扩到 representative subset**(Phase 4c)或 full(Phase 4d),user 在 Phase 4b 决策点判断,可控成本上界。

### 9.1 Cost guardrail

- **每个 phase 开跑前打印 expected cost**(根据 sample × backbone × per-call avg)
- **超 phase budget 1.5x 自动 pause + alert user**
- **Hard cap per phase**:Phase 4a $200(2.5x buffer), Phase 4c $400, Phase 5 $200
- **Hard cap total**:$600(2x 预算上界)

---

## 10. 复盘 Checkpoint 协议

**每个复盘节点必须回答**:

1. **结果**:数字 / 图 / 表 — 哪些假设 / 预期被 confirm / refute?
2. **bug**:哪些 adapter / pipeline issue 暴露了?严重度?
3. **决策**:下一 Phase 阵容是否调整?(裁 agent / 换 backbone / 换 metric)
4. **成本**:实际 spend vs 估计 — overbudget 信号?
5. **风险**:下一 Phase 新增 risk?

**记录位置**:每个 Phase 一个 `data/round2/phase{N}_checkpoint.md` + append 到 `round2_worklog.md`(对应 Round 1 的 worklog)。

---

## 11. 现在要你拍板的 4 件事(让我开始 Phase 0)

1. **Phase 0 阵容确认**:8 agent 都跑,还是先选 4-5 个低风险的(MDAgents / MedAgents / AgentClinic / MAI-DxO / LIRICAL / VC-RDAgent),DeepRare 单独后跑(因为它最慢最贵)?
2. **Phase 0 sample 选择**:复用 sanity-check 同 50 例,还是 100 例(扩到 50 PP-Store + 50 RareArena)?
3. **DeepRare timeout 设多少**:600s / 300s / 不设(让它自己卡死)?
4. **复盘 ① 时间**:Phase 0 跑完我自动写 mini_pilot_REPORT 然后你看,还是你想中途看进度?

确认后我就启动 `scripts/mini_round2_pilot.py`。
