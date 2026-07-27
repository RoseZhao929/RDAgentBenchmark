# RareAgentBench 冻结审计 · 综合报告

- 生成时间 (UTC): 2026-07-24T01:40:08Z
- 冻结 commit（本报告核实时的 HEAD）: `e85cb3ca7d5b58e5296c8d589d1deaa8cfe4e6f6`
- 工作目录: `/home/research/RDAgentBenchmark`（含完整 785M 数据）
- 通用约束: 只做审计与重新汇总；**未修改论文文字，未调用任何 LLM，未输出受限 MIMIC 原文**。
- 度量口径同主审计: R@1 = hits / n_attempted（failures/timeout/empty/parser 全部保留在分母），variant-aware 为 primary，ontology-normalized。

本文件汇总四项审计：① Temporal-holdout v2-final；② MIMIC-IV slice；③ 四数据集数据泄漏；④ 主体图 figM1 / figM5 核查。各项详细产物见对应子目录。

---

## 一、Temporal-Holdout v2-final ✅ 完成

**结论**：移除对 identifier-bearing development 源（RareArena PMCID + Phenopacket PMID）的 exact-ID overlap 后，**四个系统均未出现统计上可检测的 post-cutoff 退化**。

- overlap union / clean N：pre 14 → **206**，post 18 → **180**（非预设 207/181；两源 overlap 不相交）。
- per-system ΔR@1（clean，post−pre），**Holm 校正后无一显著**（最小 p_holm=0.117）：
  agentclinic +2.6pp / llm_control +8.9pp / mdagents +9.0pp / medagents +11.0pp。
- case-level macro（去 pseudo-replication，cluster bootstrap + permutation）：clean +7.9pp，95% CI [−0.2, +15.6]，permutation **p=0.0506（不显著）** —— 印证 v1 pooled p=0.0018 是伪重复产物。
- difficulty-matched（prevalence-tier 标签统一后重算，retained 167/167）：agentclinic **−1.2pp** / llm_control +10.2pp / mdagents +8.4pp / medagents +9.6pp；macro +6.7pp，p=0.125。**方向并非全部非负（AgentClinic 为负）。**

**允许的论文表述**：
> "After removing exact-identifier overlaps with identifier-bearing development sources, we found no statistically detectable post-cutoff degradation across the four evaluated systems."

**禁用**：contamination-free、guaranteed unseen、memorization is not the driver。时间措辞用 "published after the prespecified cutoff"。
**覆盖限制**：RareBench 出厂数据无出版物 ID，无法 ID 交集 → 只能声明"已移除对 RareArena+Phenopacket 的 overlap"，**不能声明与全部 dev 层 disjoint**。

产物：`audit_frozen/temporal_v2_final/`（脚本、summary JSON、报告 MD、clean/matched case-id、case×system 长表、overlap 审计）。`results_snapshot.json` 已从备份重建，旧伪重复 pooled p 已彻底抹除，写入 `temporal_holdout_v2`。6 条自动断言全过。

---

## 二、MIMIC-IV rare-disease slice — 状态 `NOT_REPRODUCIBLE`

**结论**：MIMIC 在当前冻结库中**不可核实、不可复现**；设计上是数据层，但无任何证据支撑一个"已评测"的结果。

### 硬证据（均从原始文件树核实）
- **无任何 MIMIC prediction receipts**（其余 5 个数据集共 83 个 receipts，MIMIC 为 0）。
- **无 cohort 文件、无原始数据**：`cases_filtered_diverse.jsonl`、`data/mimic-iv-3.1/` 全缺（`data/` 被 gitignore，`find /` 全机器找不到）。
- **Gold 已剥离**（`load_gold()` 硬编码 `mimic_diverse n_gold_cases=0, not recomputable`）。
- **`frozen_main_manifest.csv` 中 0 行 MIMIC**。
- 仅存的 legacy aggregate 表**彼此矛盾**（llm_control/DS-Pro：956@0.248 vs 402/395@0.264），receipts 已丢无法对账。

### git 溯源（关键新证据）
- 整个 `data/` 目录始终被 `.gitignore` 屏蔽 → "git 里查不到 MIMIC receipts" **推不出** "没跑过"（所有数据集 receipts 本就不进 git）。
- commit `43efa1e5` 标题即 **"add slim recompute set for paper §4-§7 (excl. MIMIC & weights)"** —— 制作复算数据集时**主动、显式排除 MIMIC**。
- 综合判断：**MIMIC 很可能真的跑过某种版本**（否则 22 行带精细差异的 aggregate 无从而来），**但原始 receipts 被有意排除在公开冻结集之外**，存在于此 checkout 之外（原作者本地/内部环境）。

### n=956 的含义
按 build log 是**去重、每病 cap 5 的 cohort 规模（约 956 例/239 病）**，即 attempted 分母的意图值 —— **但从冻结证据无法核实**（cohort 文件缺失，无 artifact 能复现）。且多数 legacy cell 实际 attempted 并未达 956（很多 100–500），故 956 是 cohort-size 声明，非多数 cell 的评测 N。

### 三层问题（性质不同，别混）
| 问题 | 性质 | 能否修复 |
|---|---|---|
| ① synthetic vignette 把 ICD 长标题渲染进输入（gold 词面泄漏给模型） | 实验**设计 bug** | ✅ 可修（分支已重设计，见下；需重跑才有干净数字） |
| ② 无 MIMIC-IV-Note（本地仅 hosp/+icu/，无 note/、discharge、radiology） | **数据可得性** | ⚠️ 需另申请 MIMIC-IV-Note（全新实验，v2 future work） |
| ③ gold 是 code-derived（ICD→Orphanet 机械映射，非独立临床裁定） | **构念效度**边界 | ❗ 修不掉，只能诚实降级为 structured-EHR probe 单独 report |

### 论文处理建议
从主诊断矩阵**下架**，降级为"已描述但未发布的数据资源"：自建 MIMIC-IV-3.1 结构化 rare-disease identification slice（synthetic vignettes from ICD titles；**无 discharge notes**；gold 为 code-derived）。Abstract、主 heatmap `[956]` cell、能力雷达、成本表、§7（0.39/0.56）中的 MIMIC 数字全部删除或改为"legacy, not reproducible"。

### 与同事分支 `experiment/mimic-structured-ehr-best-design` 的关系
该分支**正是本审计结论的落地修复**，方向一致且更进一步：
- abstract 改为 "separately reported MIMIC-IV structured-EHR probe (956 code-supervised admissions; no clinical notes)"；
- §6 主 heatmap **删除 MIMIC 列**，明写 "not a column in this diagnostic matrix … reported separately"；
- 新增 `scripts/mimic_structured_ehr_ablation.py`：**title / code / context_only 三臂配对**，context_only 为负对照量化泄漏（含单元测试）；
- 新增 limitation **L8** 诚实定性（structured & code-supervised，gold code-derived，DUA 限制）。
- **注意**：分支目前是"设计 + 论文文字修复"（commit "Design"/"paper repair"），新的 structured-EHR probe **结果尚未真正跑出**（`data/` 仍 gitignore，未见新 receipts）。补齐仍需数据 + 补跑模型（需另行授权）。

### 若要恢复为可用结果，所需最小文件（无需 raw 9.9GB）
1. `data/mimic_iv_rd_slice/cases_filtered_diverse.jsonl`（956 cohort，含 gold）；
2. `data/round2/phase4a/predictions_mimic_diverse_*.jsonl`（各 system×backbone receipts）。
有此两者即可离线打分（复用 `recompute_engine.py`，同口径），无需重跑模型。**优先向原作者 `yutianzhao` 索取**。

产物：`audit_frozen/mimic_frozen_audit/`（`mimic_frozen_audit.md`、`mimic_evidence_inventory.csv`、`mimic_paper_patch.md`；`mimic_frozen_manifest.csv` / `mimic_case_level_results.csv` 因无 receipts/gold **有意未生成**）。

---

## 三、四数据集数据泄漏审计 — 正式层无实质泄漏

**结论**：四个正式数据集（Phenopacket / RareBench / RareArena / PMC holdout）**均无实质数据泄漏，且均无 masking（也大多不需要）**。

### 模型实际输入（从代码核实）
主 runner（`phase4a_runner.py:208`）硬编码 `eval_mode="gold_hpo"`，输入优先级 `gold_hpo_terms → synthetic_vignette → free_text_vignette`：Phenopacket/RareBench 喂 **HPO 术语/ID 列表**（非诊断散文）；RareArena 落到 **`case_report` 全文**；PMC holdout 落到 Opus 生成的表型术语列表。

### 泄漏率表
| dataset (split) | n | exact-name | synonym(≥5) | identifier | title | masked? |
|---|---|---|---|---|---|---|
| phenopacket_store | 10,051 全量 | 0.68% | 0.33%（2,816 n/a） | 0.00% | n/a | 否 |
| rarebench | 1,122 全量 | 0.00% | 0.00% | 0.09%(1) | n/a | 否 |
| rarearena_rds | 2,000 抽样（全量独立复算 0.070%，6/8562） | 0.00% | 0.00% | 0.00% | 0.00% | 否 |
| pmc_oa_holdout | 198 全量 | 2.02% | 0.00% | 0.00% | n/a | 否 |
| pmc_precutoff | 220 全量 | 5.45% | 0.91% | 0.00% | n/a | 否 |

### 要点
- **无 masking/redaction**（唯一 `mask` grep 命中是 `finalize.py` 给审稿人的说明字符串，非输入脱敏）。
- **RareArena 关键（好消息）**：虽喂真实病例报告全文，但报告是"呈现式 vignette"写法，**几乎不写出最终诊断**（全量 0.07%，已独立复算确认）→ 其 R@1 反映**真 DDx，非阅读理解**。
- **PMC holdout（2–5%）** 是唯一轻度自泄漏：Opus 偶尔把诊断级术语折进表型（真泄漏，如 "Anaplastic astrocytoma"）+ 短名子串误报（如 "Noma" ⊂ "schwannoma"），真实率是**上界**，量太小不影响 aggregate。precutoff 5.45% > holdout 2.02%，方向上**不会夸大 post-cutoff 退化**，对 temporal v2 "无退化"结论无害。
- **phenopacket 0.68%** 是良性本体重叠（病名恰为某 HPO label，如 "Galactosemia"）。

### caveat
率在 `gold_hpo` 主矩阵模式下计算，其他 bespoke runner 未穷尽追踪（**部分验证**）；短病名（≤4 字符）高估子串匹配，短名/acronym 同义词单列为上界；2,816 个 OMIM-only phenopacket 病例无 in-repo ORPHA crossmap → synonym 通道**诚实标 n/a，非 0**。

**对论文的意义**：可加一句干净对照叙事 —— **四个正式层实测无实质泄漏、无需 mask；唯一有过泄漏的是 MIMIC（synthetic-vignette 设计 bug），这正是它被移出主矩阵的原因之一。**

产物：`audit_frozen/leakage_audit/`（`leakage_summary.md`、`leakage_case_level.csv` 13,591 行、`leakage_audit.py`、`_summary.json`）。

---

## 四、主体图核查（分支 `experiment/mimic-structured-ehr-best-design`）

### figM1 `figM1_llm_vs_classical.png`
- **只画 3 个 dataset（Phenopacket / RareBench / RareArena）— 正确**。§6 表 caption 明确定义主诊断矩阵为"three diagnostic datasets"；MIMIC 与 PMC holdout **有意排除**（前者 structured-EHR probe、后者 temporal-holdout 专项，各自单独 report）。
- **RareArena 只有 1 根柱（无 classical）— 逻辑正确**：LIRICAL/VC-RDAgent 需 HPO 输入，RareArena 是 free-text，classical 无法跑（真实 n/a）。
- ⚠️ **问题 1（高）**：标题 "Classical/offline baselines beat the best scaffolded LLM **on HPO input**" 被自己图内 **RareBench 反例**证伪（该 HPO 层 LLM 0.30 > classical 0.28）。只有 Phenopacket 一个 curated-HPO 层 classical 才胜。建议改为 "On **curated**-HPO input (Phenopacket-Store)…"。
- ⚠️ **问题 2（中）**："no HPO input (classical n/a)" 注释位置（`ax.text(2, 0.02, …)`）贴在 RareArena 蓝柱下方，易被误读为标注蓝柱，建议移到柱上方空白。
- ⚠️ **问题 3（中，术语一致性）**：Abstract 平铺 5 个 dataset 名（含 PMC holdout），figM1 只画 3 个，中间缺衔接说明。建议在 abstract/§4 加一句：主矩阵为三个横向诊断数据集，PMC holdout 与 MIMIC probe 各自单独分析。

### figM5 `figM5_selfpref.png`
- **对比 Gemini(family) vs Claude(non-family) 作为 judge — 合理且方法论扎实**：x 轴是 **judge 身份**（非 agent 输出），测 self-preference bias（同家族 judge 偏袒自家 agent）；有文献支撑（Panickssery et al. 2024）。
- ⚠️ **问题（高，与正文不一致）**：图画了 llm_control / mdagents / deeprare 三条线，但正文 §7.5 Corollary 已承认**只有 llm_control 和 deeprare 是干净的 judge-swap**；**mdagents 那条线被 confound** —— v2 换 judge 的同时还修复了它的 trace（337 → 20,034 字），变化混淆了两个因素。而图副标题偏偏点名 "mdagents overtakes on depth" 用被污染的线当卖点。建议：把 mdagents 线标虚线 / 加 "(trace also repaired)" 注释，或副标题改用 llm_control 的干净收缩作主结论。

### 图核查汇总
| 图 | 问题 | 严重度 |
|---|---|---|
| figM1 | 标题 "beat … on HPO input" 被自身 RareBench 反例证伪 | 高 |
| figM1 | "no HPO input" 注释位置易误读 | 中 |
| figM1 / abstract | 3 vs 5 数据集术语不一致，缺衔接说明 | 中 |
| figM1 | 只画 3 dataset / RareArena 单柱 | ✅ 正确 |
| figM5 | mdagents 线 confounded 却与干净线并列、被副标题主推 | 高 |
| figM5 | Gemini vs Claude 作为 judge-family 对比 | ✅ 合理 |

---

## 五、遗留披露 / 待决事项
1. **`results_snapshot.json` 属主为 `yutianzhao`**；为写入 temporal_holdout_v2，此前用 sudo 授予 group-write 才修改。原始版本备份于 `results_snapshot.json.pre_temporal_v2.bak`（可回滚）。正式合入前建议由文件属主确认。MIMIC 的 `NOT_REPRODUCIBLE` 结论目前**未**写入 snapshot（待你决定是否加 `mimic_slice_audit` 键）。
2. **PMC holdout 的 gold 是 Opus（LLM）抽取的**（`holdout_gold_opus.jsonl`），非人工裁定 —— 与 MIMIC 的 code-derived 性质不同，但同属"非独立临床裁定"，建议在 limitation 诚实标注。
3. **MIMIC 补齐**与 **figM1/figM5 图修订**均涉及在 `experiment/mimic-structured-ehr-best-design` 分支上动脚本并重跑；图修订需重跑 `scripts/paper_main_figures.py`，MIMIC 补齐需数据 + 补跑模型（需另行授权）。尚**未执行**任何图/脚本修改，等待指示。

---

## 附：各审计产物路径（均在 `/home/research/RDAgentBenchmark/audit_frozen/`）
- `temporal_v2_final/` — temporal-holdout v2-final 全部产物
- `mimic_frozen_audit/` — MIMIC 审计（md / evidence csv / paper patch）
- `leakage_audit/` — 四数据集泄漏审计（summary / case-level csv / 脚本 / json）
- `AUDIT_BRIEF_2026-07-23.md` — 前一版（temporal + MIMIC）简报
- `AUDIT_CONSOLIDATED_2026-07-24.md` — 本综合报告
- `results_snapshot.json` — 已更新（temporal_holdout_v2）；`.pre_temporal_v2.bak` 为原始备份
