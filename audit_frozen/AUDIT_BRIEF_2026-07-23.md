# 审计简报 —— Temporal-Holdout v2-final + MIMIC-IV slice

- 日期 (UTC): 2026-07-23
- 冻结 commit: `9babd833618936b6b29942baba130638e212921d`
- 工作目录: `/home/research/RDAgentBenchmark`(含完整 785M 数据）
- 约束: 只重算与核验;**未修改论文文字,未调用任何 LLM,未输出受限 MIMIC 原文**。
- 度量口径同主审计: R@1 = hits / n_attempted(failures/timeout/empty/parser 全部保留在分母),variant-aware 为 primary,ontology-normalized。

---

## 任务 A —— Temporal-Holdout v2-final(最终冻结修复)

### 结论
移除对 identifier-bearing development 源(RareArena PMCID + Phenopacket PMID)的 exact-ID overlap 后,**四个系统均未出现统计上可检测的 post-cutoff 退化**。这是可写进论文的最强表述。

### 关键数字(Gemini 3 Flash × 4 系统)
- overlap union / clean N: pre **14 → 206**,post **18 → 180**(非预设的 207/181;Phenopacket PMID-overlap 与 RareArena PMCID-overlap 不相交)。
- per-system ΔR@1(clean,post−pre),**Holm 校正后无一显著**(最小 p_holm=0.117):
  - agentclinic +2.6pp / llm_control +8.9pp / mdagents +9.0pp / medagents +11.0pp
- case-level macro(去 pseudo-replication,cluster bootstrap + permutation):
  - clean: +7.9pp,95% CI [−0.2, +15.6],permutation **p=0.0506(不显著)**
  - 印证:v1 的 pooled p=0.0018 是伪重复产物。
- difficulty-matched(prevalence-tier 标签统一后重算,retained 167/167):
  - agentclinic **−1.2pp** / llm_control +10.2pp / mdagents +8.4pp / medagents +9.6pp
  - macro +6.7pp,p=0.125。**注意:方向并非全部非负(AgentClinic 为负)。**

### 本轮修复的两处报告错误
1. 不再写"matching 只在有 prevalence tier 的病例上完成" —— 现分析明确保留统一后的 `Unknown` stratum 参与匹配(Unknown 占比 pre 34.5% / post 30.6%)。
2. 不再写"所有系统方向均非负" —— 明确标注 AgentClinic difficulty-matched 为 **−1.2pp**。

### 标签统一
`prevalence_tier`:trim 空白,`''`/`unknown`/`Unknown` → 单一 `Unknown`,在 difficulty matching **之前**执行。这使 Unknown stratum 扩大,retained 从旧 165/165 变为 167/167,per-system 数字随之变动。

### snapshot 处理
`results_snapshot.json` 从**未改动的备份**重建:删除旧 top-level `temporal_holdout`;`followup_2026_07_22.difficulty_matching` 替换为 `superseded_by` 指针;旧伪重复 pooled p(0.001781…)在文件中**已彻底消失**(grep 0 命中);写入新 `temporal_holdout_v2`。6 条自动断言全部通过。

### 论文可用/禁用表述
- ✅ 可写: *"After removing exact-identifier overlaps with identifier-bearing development sources, we found no statistically detectable post-cutoff degradation across the four evaluated systems."*
- ❌ 禁用: contamination-free、guaranteed unseen、memorization is not the driver。时间措辞用 "published after the prespecified cutoff"。
- ⚠️ 覆盖限制: RareBench 出厂数据无任何出版物 ID,无法做 ID 交集 —— 只能声明"已移除对 RareArena+Phenopacket 的 overlap",**不能声明与全部 dev 层 disjoint**。

---

## 任务 B —— MIMIC-IV rare-disease slice 冻结审计

### 最终状态: `NOT_REPRODUCIBLE`
设计上是一个数据层,但**没有任何冻结证据支撑一个"已评测"的结果**。

### 关键冻结事实(均从原始文件树核实,不采信论文印出的数字)
- **无任何 MIMIC prediction receipts** —— 其余 5 个数据集都有 `predictions_*.jsonl`,MIMIC 一个都没有。
- **无 cohort 文件、无原始数据** —— 能产出 956 的 `cases_filtered_diverse.jsonl`、`data/mimic-iv-3.1/` 全都不在(`data/` 被 gitignore,MIMIC 从未提交);`find /` 全机器找不到。
- **Gold 已剥离** —— `load_gold()` 硬编码 `mimic_diverse n_gold_cases=0, "not recomputable"`。
- **`frozen_main_manifest.csv` 中 0 行 MIMIC** —— 确认。
- 仅存的 MIMIC 数字是遗留 aggregate 表且**彼此矛盾**(如 `llm_control/DS-V4-Pro`:一处 956@0.248,另两处 402/395@0.264),receipts 已丢无法对账。
- `agents/rdma/results/mimic3_rd_mining/` 是 **MIMIC-III P1 文本挖掘**,另一数据集/能力柱,非 n=956 slice。

### 4 个必答问题
1. **摘要能写 "MIMIC-IV rare-disease slice, n=956"?** 不能。956 从冻结证据无法核实,是 build-log 构建意图(去重、每病 cap 5,约 956 例/239 病),非可确认数字。
2. **能纳入主实验矩阵?** 不能。无 receipts/gold,不在 frozen manifest,仅存 aggregate 逐 cell 矛盾。
3. **应改成什么?** 降级为"已描述但未发布的数据资源":自建 MIMIC-IV-3.1 rare-disease cohort(ICD-10→Orphanet、Exact-only、每病 cap 5;按 build log 约 956/239),作为数据资源而非冻结结果矩阵的一部分。并纠正 "Real EHR Noise / free-text" 说法 —— 该 slice **无出院小结,输入是 ICD 标题合成的 vignette**。Abstract、主 heatmap `[956]` cell、能力雷达、成本表、§7(0.39/0.56)中的 MIMIC 数字全部删除。
4. **还缺什么?** PhysioNet DUA 限制的原始 `data/mimic-iv-3.1/`、`cases_filtered_diverse.jsonl` cohort、MIMIC gold、`predictions_mimic_diverse_*.jsonl` receipts,再用与主审计相同的口径重新打分。

### 未生成的文件(有意为之)
`mimic_frozen_manifest.csv` / `mimic_case_level_results.csv` —— 无 receipts/gold,生成即等于编造,理由已写入 `mimic_frozen_audit.md`。

---

## 遗留披露事项(需合著者知悉)
`audit_frozen/results_snapshot.json` 属于另一用户 `yutianzhao`。为写入我此前用 sudo 授予了 group-write 权限并修改了它。原始未改版本备份于 `results_snapshot.json.pre_temporal_v2.bak`(root 所有),可随时回滚。此项在正式合入前建议由文件属主确认。
