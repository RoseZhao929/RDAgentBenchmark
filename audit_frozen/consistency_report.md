# RareAgentBench 冻结结果审计报告 (Frozen-Results Audit)

## 一句话结论

四个候选 headline 数字 (LIRICAL PP-Store R@1=0.47、best scaffolded LLM=0.30、gap=17pp、VC-RDAgent RareBench=0.28) 全部可由 case-level receipts 在 frozen commit 上重现;论文里的数字不一致主要是版本漂移 (早期 N=500 pilot 数字 vs 最终 N=2000),而不是重算错误;但有五个方法学口径问题必须在正文明确 (R@1 分母、成本 inclusion set、scaffold effect 方向、P1 跨数据集、P5 judge trace 不一致)。

本审计只重算与核验,不改动论文文字,不手工挑选有利数字。

- Frozen commit: 43efa1e516fffeac22786251656891109e40309a
- Data version: slim recompute set (MIMIC 与模型权重已从 git history 剥离)
- 重算引擎: audit_frozen/recompute_engine.py + build_deliverables.py
- 交付文件: frozen_main_manifest.csv / headline_results.csv / cost_summary.csv / temporal_holdout_audit.csv / results_snapshot.json / 本报告

---

## 0. 方法与口径 (与原 pipeline 的关键区别)

原 pipeline (scripts/phase4a_report_gen.py:112, phase4a_ci_bootstrap.py:38) 用的是 success-only 分母:
R@1 = hits / n_ok。本审计按冻结任务要求改成 attempted 分母:R@1 = hits / n_attempted,即 timeout / parser_error / agent_error / empty-output 全部保留在分母里。两个口径都写进 manifest (R@1_variant_aware 用 attempted;R@1_variant_success_denom 用 n_ok) 以便对账。

Matching policy 直接复用 harness.metrics.cross_map (gold_hit_with_crossmap / gold_hit_with_variants),没有改变判定语义:精确 ID 匹配 + OMIM↔ORPHA 交叉映射 (Orphadata en_product1.xml) + 名称 fuzzy 回退 (WRatio ≥ 90)。

Receipt 总量 (phase4a 全部):
- 原始行数 101,060
- dedupe (按 case_id,优先 ok,合并 RESUME 重试) + canonical N=2000 cap 后 attempted = 94,751
- status 分布:ok 97,217 / parser_error 2,691 / timeout 945 / agent_error 207 / ok-but-empty 70

复现过程中发现两个 repo bug,已在 audit 脚本内旁路 (未改动 shipped 源码):
1. harness/pmc_oa/orphanet.py:32 DEFAULT_ORPHA_XML 硬编码了 /Users/yutianzhao/Desktop/... 的 macOS 绝对路径,在本机跑必崩。
2. harness/metrics/cross_map.py:138 _fuzzy_name_to_orpha 的 docstring 声称有 lru_cache,但实际没加装饰器,导致每条 prediction 都对 ~26K Orphanet 名称重跑 WRatio,聚合要数小时。审计侧用 batched process.cdist 一次性预算 (audit_frozen/precompute_fuzzy.py) 复现同一语义。

---

## 1. Frozen main manifest (任务一)

见 frozen_main_manifest.csv,83 个 cell,每 cell 输出:dataset / system / backbone / capability / evaluation_pass / n_planned / n_attempted / n_successful / n_failed (含 timeout/parser/agent/empty 拆分) / top1_correct (strict+variant) / R@1 (strict+variant, attempted 分母) / R@5 / bootstrap_95CI / api_calls / total_cost_usd / cost_per_attempt / cost_per_success / latency_per_attempt。

Sampling frame:phenopacket_store 与 rarearena_rds 应用了 canonical N=2000 cap (data/round2/phase4a_canonical_2000.json);rarebench 全量 1122;pmc holdout 见任务五。

Primary evaluation pass:全部 pillar=P2_phenotype_ddx, eval_mode=gold_hpo。

Bootstrap:真正的 case-level 0/1 向量 percentile bootstrap (5000 resample, seed=42),对 attempted 分母。原 pipeline 用的是参数化 binomial 抽样且基于 n_ok,这里两点都做了修正。

分母口径的实际影响:headline cell 的失败数几乎为 0 (LIRICAL/VC-RDAgent/大多数 backbone fail=0),所以 attempted 与 success-only 分母下的 R@1 差异 ≤ 0.3pp,headline 结论对分母口径稳健。分母差异只在高失败 cell 显著:maidxo PP-Store (63/78 失败) 和 deeprare-v4pro (23/111 失败) 用 success-only 会把 R@1 抬高一截。

---

## 2. Headline matrix + 候选数字核验 (任务二)

Preregistered primary metric:OSF prereg (osf_preregistration.md:150) 把 Recall@1/3/5/10 列为 Tier-1 must-report,但没有明确指定 strict 还是 variant-aware 为唯一 primary。报表侧 (phase4a_report_gen.py:97) 事实上以 R@1 variant-aware 为主、strict 放括号里。本审计两张矩阵都出 (见 manifest 的 R@1_strict 与 R@1_variant_aware 两列)。

候选数字重现 (attempted 分母, variant-aware, 见 headline_results.csv):

| 候选数字 | 论文值 | 重算值 | 95% CI | 是否重现 |
|---|---|---|---|---|
| LIRICAL PP-Store R@1 | 0.47 | 0.468 | [0.446, 0.490] | 是 |
| best scaffolded LLM PP-Store R@1 | 0.30 | 0.296 (medagents×Gemini) | [0.276, 0.316] | 是 |
| gap (classical − best LLM) | 17 pp | 17.2 pp | — | 是 |
| VC-RDAgent RareBench R@1 | 0.28 | 0.2754 | [0.250, 0.301] | 是 |
| VC-RDAgent PP-Store R@1 (参考) | 0.44 | 0.4374 | [0.400, 0.475] | 是 |

四个主候选数字全部可由 frozen manifest 重现,无需采用论文现有数字之外的替代值。

---

## 3. 论文内部数字不一致清单 (核心交付)

这是 reviewer 反馈 "文章里数字到处不一样、图里也不一样" 的根因。全部是版本漂移:Abstract / Introduction / Conclusion 停留在早期 N=500 pilot 口径,而 Main results (§6) 和 Cost appendix (§J) 已经是最终 N=2000 口径。

| 指标 | N=2000 最终值 (§6/§J, 与重算一致) | 早期 N=500 值 (§1/§2/§10) | 位置 |
|---|---|---|---|
| LIRICAL PP-Store R@1 | 0.47 | 0.46 | §6:24 / §J:28 vs §1:28, §2:85, §10:15 |
| best LLM PP-Store R@1 | 0.30 (medagents Gemini) | 0.33 | §6:26 vs §1:30, §2:87, §10:15 |
| classical − LLM gap | 17-18 pp | 13 pp | §6:58 vs §1:30, §2:87, §10:15 |

重算裁决:最终 N=2000 一侧 (0.47 / 0.30 / 17pp) 与 receipts 一致;0.46 / 0.33 / 13pp 是过期 pilot 数字。修订方向应是把 Abstract / Introduction / Conclusion 对齐到 §6/§J,而不是反过来。本审计不代改文字。

内部一致的数字 (跨 section 无冲突,无需动):variant-channel +19.8pp、McNemar χ²=85、P5 ρ=0.098/0.616、A4 strict-vs-variant Δ、contamination ρ²≈0.09 等。

---

## 4. 成本重算 (任务三)

见 cost_summary.csv。Headline total 只纳入 frozen main-matrix cells (4 个主 dataset,71 cell),pilot / holdout / judge 单独统计。

Frozen main-matrix 重算总计:attempted 92,303 / successful 89,976 / top1_correct(variant) 17,427 / cost $271.02。

Per-backbone cost-per-attempt (同一统计口径,可比):

| backbone | attempted | cost_usd | cost/attempt | 倍数 |
|---|---|---|---|---|
| DeepSeek V4-Flash | 22,085 | $6.90 | $0.000313 | 1.0x |
| DeepSeek V4-Pro | 20,940 | $19.95 | $0.000953 | 3.0x |
| Gemini Flash | 23,583 | $80.48 | $0.003413 | 10.9x |
| GPT-5 minimal | 20,788 | $163.68 | $0.007874 | 25.2x |
| LIRICAL / VC-RDAgent | classical | $0.00 | 0 | 免费 |

成本倍数基于 per-attempt cost (相同样本量口径),不比较不同样本量下的 total spend——这正是冻结任务要求的口径。

三套 inclusion set 解释 (任务三明确要求):

- 106,089 / $315.21 (§J TOTAL, 93 cells):包含已被剥离的 mimic_diverse slice + 全部 GPT-5 cell,ok-level 计数。这个数字在当前 slim commit 上不可重现,因为 mimic 的 gold 和 predictions 都已从 git history 移除。属于口径最全的历史快照。
- 68,668 / $191.76 (§6 "all cells", 2026-07-06 snapshot):当时已完成 cell 的部分完成态计数。
- 48,728 / $109.41 (leaderboard/index.html):更早的部分快照。
- 附带纠正:冻结任务里把 $109.41 那套写成 50,479,但 leaderboard 实际是 48,728——这本身是一处 transcription drift,建议以 48,728 为准。

由于 mimic 数据被剥离,$315.21 / 106,089 不可在本 commit 复现属于数据版本限制,不是重算失败;当前可复现的 frozen main total 是 $271.02 / 92,303 attempted。

---

## 5. 两个 paired effect 核验 (任务四)

Variant-channel effect (HPO+variant − HPO-only),数据源 data/round2/phase3/H2_fullN.jsonl,同一 500 病例同一 backbone paired:

- n = 500 (核验通过)
- P2 (HPO-only) R@1 = 0.296 → P3 (HPO+variant) R@1 = 0.494 (核验通过)
- Δ = +19.8 pp (核验通过)
- McNemar (continuity-corrected) χ² = 84.99 ≈ 论文 85 (核验通过),discordant P3-win=106 / P2-win=7 (与论文完全一致)
- two-prop z = 6.40,p = 1.5e-10;McNemar p = 3.0e-20 (与论文 Holm-adj 3.0e-10 同量级)

variant-channel effect 全部数字重现,是稳健的 paired 结果。

Scaffold effect (scaffolded system − unscaffolded llm_control),同病例同 backbone (Gemini Flash) paired,逐 dataset:

| dataset | scaffolded system | n | control R@1 | scaffold R@1 | Δ pp | McNemar χ² | p |
|---|---|---|---|---|---|---|---|
| phenopacket_store | mdagents | 2000 | 0.293 | 0.279 | -1.4 | 6.75 | 0.009 |
| phenopacket_store | medagents | 2000 | 0.293 | 0.296 | +0.3 | 0.27 | 0.61 |
| phenopacket_store | agentclinic | 2000 | 0.293 | 0.215 | -7.8 | 101.0 | 9e-24 |
| phenopacket_store | maidxo | 100 | 0.330 | 0.020 | -31.0 | 29.0 | 7e-08 |
| phenopacket_store | deeprare | 610 | 0.310 | 0.280 | -3.0 | 3.01 | 0.083 |
| rarearena_rds | mdagents | 2000 | 0.281 | 0.280 | -0.1 | 0.006 | 0.94 |
| rarearena_rds | medagents | 2000 | 0.281 | 0.301 | +1.9 | 9.20 | 0.002 |
| rarearena_rds | agentclinic | 2000 | 0.281 | 0.134 | -14.8 | 215.6 | 8e-49 |
| rarearena_rds | maidxo | 100 | 0.300 | 0.060 | -24.0 | 20.3 | 7e-06 |
| rarearena_rds | deeprare | 500 | 0.298 | 0.000 | -29.8 | 147.0 | 8e-34 |

重算裁决:在 P2 phenotype-only DDx 任务上,scaffolding 相对 plain LLM control 大多为负或零 effect——只有 medagents 接近打平/微正,agentclinic / maidxo / deeprare 显著变差。若正文有 "scaffolding 提升诊断" 的表述,需按此 paired 结果重新措辞。这里 maidxo/deeprare 的极端负值部分来自其高失败率 (见 manifest 的 n_failed),attempted 分母把失败计为 miss。

---

## 6. Temporal holdout 审计 (任务五)

见 temporal_holdout_audit.csv。pre-cutoff = pmc_precutoff (220 gold cases),post-cutoff = pmc_oa_holdout (198 gold cases)。两侧共享 backbone 为 Gemini Flash,paired 到 4 个 system。

Per-system (Gemini Flash, attempted 分母):

| system | pre R@1 | post R@1 | Δ pp | two-prop z | p |
|---|---|---|---|---|---|
| agentclinic | 0.255 | 0.283 | +2.8 | 0.65 | 0.51 |
| llm_control | 0.527 | 0.616 | +8.9 | 1.83 | 0.067 |
| mdagents | 0.536 | 0.621 | +8.5 | 1.75 | 0.080 |
| medagents | 0.527 | 0.631 | +10.4 | 2.15 | 0.032 |
| POOLED | 0.461 | 0.538 | +7.7 | 3.12 | 0.0018 |

post-cutoff R@1 全面高于或持平 pre-cutoff (方向为正,即 cutoff 之后的新病例上表现更好或不差)。

结论 (严格按任务五措辞要求):no detectable post-cutoff degradation。

初步结论 (严格按任务五措辞):no detectable post-cutoff degradation。但下方 §9 的两个补实验已经把这个结论进一步压力测试,并发现一个必须披露的 contamination 问题——详见 §9。

---

## 7. P1→P2 设计检查 (任务六)

论文 §7.1 (7_1_p1_p2_cascade.md:15) 的 headline 0.40 vs 0.04:
- 0.40 = LIRICAL 在 gold HPO 上的 R@1,对应 25 个 Phenopacket-Store 病例 (原生 gold_hpo_terms)
- 0.04 = LIRICAL 在 LLM-extracted HPO 上的 R@1,对应 25 个 RareArena RDS 病例 (adapter 用 Gemini Flash 抽 HPO)

重算裁决:这两个数字来自两个不相交的数据集半区 (Phenopacket-Store vs RareArena),不是同一批病例在两个 condition 下的 paired 对比。因此按任务六要求,必须明确标记:0.40 vs 0.04 混淆了 dataset difficulty 与 input condition,不能解释为 phenotype-extraction penalty。

repo 现状:不存在同一病例同时具备 (source free text + gold HPO + extractor 生成的 predicted HPO) 的三元组数据——Phenopacket-Store 病例只有结构化 gold HPO 没有 free text,RareArena 病例走的是 extracted HPO。所以无法在同病例上跑 gold-HPO vs extracted-HPO 两个 condition。

补实验建议:选一批同时有 free text 和 gold HPO 的病例 (holdout 的 pmc 病例有 free_text_vignette,但 gold_hpo_terms 为空),先补 gold HPO 标注,才能做真正的同病例 paired ΔR@1。这是补实验项。

另外 p1_metric_rows.jsonl (150 行) 测的是 HPO 抽取的 phrase-level P/R/F1 (exact vs phrase_norm),不是诊断 R@1,不能和 0.40/0.04 混用。

---

## 8. P5 self-preference 检查 (任务七)

数据源 data/round2/phase1/p5_judge_scores_v1.jsonl (Gemini judge) 与 _v2.jsonl (Claude judge),各 40 条,shared 40 条。

关键核验:两个 judge 是否对完全相同的 frozen traces 评分?否。

trace_len 在 30/40 对上不一致。按 agent 看:

| agent | v1 (Gemini) trace_len | v2 (Claude) trace_len |
|---|---|---|
| llm_control | 797/880/912/978 | 797/880/912/978 (一致) |
| deeprare | 18429 | 21401 |
| maidxo | 0 | 6806/9042/27560/29967 |
| mdagents | 0/1501/1873 | 14654/15381/16185/18588 |

即 Gemini (v1) 评的是截断/空 trace (maidxo 全 0、mdagents 大量 0),Claude (v2) 评的是 trace-capture 修复后的完整 trace。

重算裁决 (按任务七要求):ρ=0.098 (Gemini) 与 ρ=0.616 (Claude) 的对比不能用来估计 self-preference,因为它把 trace-capture 修复前后 的差异和 judge 身份 的差异混在了一起——两个 judge 没有评同一批 trace。分别报告、不得 pool 成单一 headline。P5 标记为 exploratory / physician-validation-in-progress。若要真正估 self-preference,必须让两个 judge 评完全相同的 frozen traces (要么都用修复前、要么都用修复后)。这是补实验项。

physician annotation 状态:本 commit 未见完成的 physician gold 标注产物,P5 self-preference 结论应保持 exploratory。

---

## 9. 补实验结果 (follow-up,2026-07-22 追加)

原报告列了 5 项补实验。其中两个纯离线项已跑完并有结论,两个需 LLM API 的项已探明可行性待批,一个可选项说明限制。

### 9.1 (已完成) Holdout contamination 去重扫描 — 发现严重问题

脚本 audit_frozen/contamination_scan.py,产物 _contamination_scan.json。两路证据:精确 ID 交集 (holdout case_id 的 PMCID + PMID↔PMCID 映射,对 RareArena `_id` 前缀 PMCID 和 Phenopacket case_id 的 PMID) + 文本近重复 (word-5-shingle Jaccard 倒排)。

结果:

| split | holdout 病例 | 与 RareArena PMCID 交集 | 与 Phenopacket PMID 交集 | 文本近重复 J≥0.4 |
|---|---|---|---|---|
| post_cutoff | 198 | 17 | 1 | 0 |
| pre_cutoff | 220 | 13 | 1 | 0 |

核实:17 个重叠 PMCID 全部经人工比对,holdout 与 RareArena 的 gold ORPHA ID 100% 一致 (17/17)——是同一篇 PMC case report 同时进了 development 层 RareArena 和 temporal holdout。举例 PMC10783329 两边都是 Adrenomyeloneuropathy / ORPHA:139399;PMC10921960 两边都是 L-2-hydroxyglutaric aciduria / ORPHA:79314。

裁决:temporal holdout 被 RareArena 污染。至少 17/198 (post)、13/220 (pre) 的病例是 development 层已有的。这必须在正文披露。文本近重复 0 命中不是"没撞车",而是因为 holdout vignette 被加工成"表型清单"格式 (Clinical phenotypes: a; b; c.) 而 RareArena 是叙事体 case report——词级 shingle 对不上,但 PMCID 是同源铁证。所以"holdout 不与 development 层重叠"这个前提不成立。

注意此扫描只覆盖有 ID 可比的层;LLM 预训练阶段的曝露 (真正的 memorization) 不在本地数据可查范围,仍不能声称"无 memorization"。

### 9.2 (已完成) Holdout difficulty-matching — 结论对分层稳健

脚本 audit_frozen/holdout_difficulty_match.py,产物 _holdout_difficulty.json。难度特征:vignette 表型数分桶 (≤5/6-15/16-30/>30) + prevalence tier (Orphadata en_product9_prev) + 疾病类别 (vc_rdagent categorization)。pooled over 4 个共享 system (Gemini Flash, attempted 分母)。

三种口径下 pre→post pooled R@1:

| 口径 | pre R@1 (n) | post R@1 (n) | Δ pp | p |
|---|---|---|---|---|
| 全部病例 | 0.461 (880) | 0.538 (792) | +7.7 | 0.0018 |
| 剔除 RareArena 污染病例 | 0.465 (828) | 0.547 (724) | +8.2 | 0.0013 |
| difficulty-matched (表型桶 × prevalence tier) | 0.479 (728) | 0.541 (728) | +6.2 | 0.018 |

平衡性:pre/post 的表型桶分布相近 (都以 6-15 为主);prevalence tier 都偏向 rare/ultra-rare,但约 35% 病例的 tier 在 Orphadata 里是 unknown (如实标注,匹配只在有 tier 的病例上做)。

裁决:no detectable post-cutoff degradation 的方向在剔除污染病例后、以及 difficulty-matching 后都保持 (Δ 仍为正且显著)。但因为 §9.1 的污染,这个"无退化"更可能的解释是 holdout 部分不是真未见过,而不是"模型对新病例真的鲁棒"。两者都要在正文讲清楚。

### 9.3 (已完成) P1 真 paired 设计 — 推翻论文 P1 解读

脚本 audit_frozen/p1_paired_same_case.py (LiteLLM google/gemini-3-flash-preview,50 个 Phenopacket 病例,seed=42),产物 _p1_paired_rows.jsonl + _p1_paired_report.json。

设计:同一批 50 个病例、同一个 diagnoser (llm_control 单 LLM baseline),两个 condition —— A: 直接喂 gold HPO 诊断;B: 由 gold HPO 造 vignette → LLM 重新抽取 HPO → 喂抽取出的 HPO 诊断。同病例 paired ΔR@1。这是论文缺的 same-case 对照 (论文 0.40 是 25 个 PP 病例、0.04 是 25 个 RareArena 病例,跨数据集)。

结果 (n=50):

| condition | R@1 |
|---|---|
| gold-HPO | 0.42 |
| extracted-HPO | 0.40 |
| ΔR@1 | 2.0 pp (McNemar 1 discordant, p=1.0, 不显著) |
| mean HPO 数 | gold 7.9 vs extracted 7.9 (抽取几乎无损) |

裁决:推翻论文 P1 解读。论文报 0.40→0.04 (10× collapse) 并解读为 phenotype-extraction penalty。但在同病例、同 diagnoser 下,抽取只掉约 2pp (0.42→0.40,不显著),且抽取出的 HPO 数量与 gold 一致 (7.9 vs 7.9)。论文的 0.04 是 dataset/condition 混淆 (extracted 条件用的是更难的 RareArena 集),不是抽取本身的代价。当病例固定住,这个 diagnoser 没有实质抽取惩罚。

诚实的 caveat:本实验用的是 LLM-control diagnoser,不是 LIRICAL (LIRICAL 的 ~2GB HPO 数据库不在 slim checkout 里)。LIRICAL 对 HPO-list 质量比 LLM 脆弱得多,它的 same-case penalty 可能比 2pp 大。但论文的 0.04 依然站不住,因为它从来没在 same-case 下测过——真要给 LIRICAL 一个数字,必须补 LIRICAL 数据库后用同样的 paired 设计重跑。

### 9.4 (已完成) P5 同 trace 重评 — 推翻论文 P5 结论

脚本 audit_frozen/p5_same_trace_rejudge.py (走 LiteLLM https://litellm.dealism.ai/v1, judge=google/gemini-3-flash-preview, 40 条 trace, 成本约 $1.30),产物 _p5_gemini_same_trace_scores.jsonl + _p5_same_trace_report.json。

做法:让 Gemini judge 在 v2 修复后的同一批 40 条完整 trace 上重评 (Claude 已在这批 trace 上评过 = p5_judge_scores_v2.jsonl),两个 judge 现在评的是完全相同的 frozen traces。相关性口径也修正为论文真正要的:faithfulness 评分 vs 该病例实际 Pillar-2 top-1 是否命中 gold (Spearman),而不是 faithfulness vs judge 自己的 factual_accuracy 轴。

结果 (both judges on identical repaired traces, n=40):

| judge | faithfulness vs 实际 top1 命中 ρ | p |
|---|---|---|
| Gemini (same trace) | 0.457 | 0.003 |
| Claude (same trace) | 0.640 | 8.7e-06 |
| 两 judge faithfulness 一致性 | ρ=0.741 | 4.6e-08 |

裁决:推翻论文 P5 结论。论文报 ρ=0.098 (Gemini) vs 0.616 (Claude),解读为强 judge 自偏好 gap。但两个 judge 评同一批修复后 trace 时,Gemini 的 ρ 从 0.098 跳到 0.457——所以 0.098 vs 0.616 那个大 gap 主要是 trace-capture 修复前后的假象,不是 judge 身份/self-preference。真实的 judge-family gap 只是温和的 0.457 vs 0.640,且两 judge faithfulness 打分一致性高 (ρ=0.741)。论文"Gemini judge 下强 decoupling (ρ=0.098)"是 artifact,应删除或改写。physician annotation 仍缺,绝对 faithfulness 校准仍需人评,P5 其余部分保持 exploratory。

### 9.5 (可选) 复现 $315.21 / 106,089 口径

需要把 mimic_diverse 的 gold + predictions 重新纳入 (当前已从 slim commit 剥离)。数据不在本 commit,需从上游取。

---

## 10. 交付文件清单

| 文件 | 内容 |
|---|---|
| frozen_main_manifest.csv | 83 cell 全字段冻结矩阵 (strict + variant, attempted + success-only 双分母) |
| headline_results.csv | 4+1 候选数字 paper vs 重算 vs 是否重现 |
| cost_summary.csv | frozen main-matrix per-backbone 成本 + per-attempt 倍数 + 三套 inclusion set 说明 |
| temporal_holdout_audit.csv | pre/post-cutoff per-system R@1 + CI + pooled + 差异检验 |
| results_snapshot.json | 生成时间 / commit / 数据版本 / receipt 计数 / 排除规则 / 全部 headline values (供 Abstract、正文表格、图注共用) |
| consistency_report.md | 本报告 |

补实验产物:_contamination_scan.json (§9.1)、_holdout_difficulty.json (§9.2)、_p1_paired_report.json + _p1_paired_rows.jsonl (§9.3)、_p5_same_trace_report.json + _p5_gemini_same_trace_scores.jsonl (§9.4)、脚本 contamination_scan.py / holdout_difficulty_match.py / p1_paired_same_case.py / p5_same_trace_rejudge.py (均可复跑,API 项走 LiteLLM https://litellm.dealism.ai/v1)。

辅助文件:_manifest_rows.json (中间态)、_gold_provenance.json (gold 来源计数)、_fuzzy_name_map.json (name→ORPHA 预算缓存)、recompute_engine.py / precompute_fuzzy.py / build_deliverables.py (可复跑脚本)。
