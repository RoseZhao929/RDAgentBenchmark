# Temporal-Holdout 最终冻结结果 (v2-final)

> 最后一次冻结修复。**未修改论文文字，未调用任何新模型**，只用磁盘上已有的 pre/post prediction receipts。
> 取代 `audit_frozen/temporal_v2/` 与 v1 (`consistency_report.md` §6/§9.1–§9.2)。

- Data version: slim recompute set (MIMIC & weights stripped); frozen commit 9babd8336189
- Commit: `9babd833618936b6b29942baba130638e212921d`
- 生成时间 (UTC): `2026-07-23T09:33:07Z` （summary / 本报告 / snapshot 同一 commit 与生成时间）
- 生成脚本: `audit_frozen/temporal_v2_final/build_temporal_v2_final.py`
- Backbone: Gemini 3 Flash（唯一 pre/post 两侧都齐的 backbone）
- Systems: `llm_control`, `mdagents`, `medagents`, `agentclinic`

---

## 本次修复要点（相对 temporal_v2）

1. **prevalence-tier 标签在 difficulty matching 前统一**：trim 空白，并将 `Unknown` / `unknown` / 空值统一映射为单一 `Unknown` 类别（此前 `'Unknown'` 与 `'unknown'` 被当成两个 strata）。
2. 统一标签后**重新执行 case-level matching**，并重新生成 matched case lists、per-system results、case-level macro、bootstrap CI、permutation p。
3. 修正下方两处此前的错误表述。
4. `results_snapshot.json` 从**未改动的备份**重建，彻底抹掉旧的伪重复 pooled p（0.001781…），再写入 `temporal_holdout_v2`。
5. 新增 case×system 长表 `temporal_holdout_case_system_long.csv`，供独立复算 cluster bootstrap / permutation。

---

## 一、disjoint test set（overlap union，未受标签统一影响）

统一 publication identity 用 **PMCID + PMID**（都是精确匹配）。**DOI 与 normalized title 在所有冻结产物里都不存在**，overlap 审计 CSV 保留列但为空并标注。

| dev 层 | 匹配键 | 可交集? | pre overlap | post overlap |
|---|---|---|---|---|
| RareArena RDS | PMCID | ✅ | 13 | 17 |
| Phenopacket Store | PMID | ✅ | 1 | 1 |
| RareBench | — | ❌ shipped 数据无任何出版物 ID | 不可查 | 不可查 |
| 其他 PMC dev cases | — | ❌ 本 checkout 无 case-report 语料 | — | — |

⚠️ RareBench 无法做 ID 交集，因此只能声明"已移除对 identifier-bearing dev 源 (RareArena+Phenopacket) 的 exact-ID overlap"，**不能声明与全部 dev 层 disjoint**。

| split | 总病例 | union（去重后并集） | **clean N** |
|---|---|---|---|
| pre_cutoff | 220 | 14 | **206** |
| post_cutoff | 198 | 18 | **180** |

Phenopacket 的 PMID-overlap 与 RareArena 的 PMCID-overlap 不相交，故 clean N = **206 / 180**（非 207/181）。逐病例明细见 `temporal_overlap_audit.csv`。

---

## 二、per-system 结果（clean set，Holm 校正，family=4）

attempted 分母、variant-aware 为 primary，failures 保留在分母。

| system | n_pre | n_post | pre R@1 | post R@1 | ΔR@1 | 95% CI(post) | z | p_raw | **p_holm** |
|---|---|---|---|---|---|---|---|---|---|
| mdagents | 206 | 180 | 0.5437 | 0.6333 | +9.0pp | [0.5611, 0.7] | 1.783 | 0.0745 | **0.2235** |
| llm_control | 206 | 180 | 0.5388 | 0.6278 | +8.9pp | [0.5556, 0.6944] | 1.766 | 0.0773 | **0.2235** |
| medagents | 206 | 180 | 0.5291 | 0.6389 | +11.0pp | [0.5667, 0.7056] | 2.18 | 0.0293 | **0.1171** |
| agentclinic | 206 | 180 | 0.2573 | 0.2833 | +2.6pp | [0.2167, 0.35] | 0.576 | 0.5649 | **0.5649** |

四个系统 ΔR@1 方向均为正（post ≥ pre）；**Holm 校正后无一显著**（最小 p_holm = 0.117）。

---

## 三、pooled 修正（去 pseudo-replication）

v1 的 pooled z-test（把同病例×4系统当 4 个独立观测，pooled p=0.0017816）**作废并已从 snapshot 抹除**。改用 **case-level macro**（抽样单位=病例；同病例 4 系统一起 cluster-bootstrap + permutation）：

| 口径 | pre macro R@1 (n) | post macro R@1 (n) | Δ | 95% CI | permutation p |
|---|---|---|---|---|---|
| clean set | 0.4672 (206) | 0.5458 (180) | **+7.9pp** | [-0.2, 15.6] pp | **0.0506** |

case-clustered 后 Δ 为正但 **不显著**（p=0.0506）—— 印证 v1 的显著性是伪重复产物。

---

## 四、difficulty-matched sensitivity（标签统一后重算）

匹配在 **case level** 完成，特征 = phenotype-count 分桶 × prevalence tier（**含统一后的 `Unknown` stratum**）。

- **unknown prevalence 比例（统一 `Unknown` 后）**：pre ≈ 34% / post ≈ 31%。
- **说明**：本分析**保留了 `Unknown` stratum 参与匹配**（并非只在有 prevalence tier 的病例上完成）。matching 前后分布见 `temporal_holdout_summary_v2.json:difficulty_matched`。
- retained：**167 / 167**。

| system | n_pre | n_post | pre R@1 | post R@1 | ΔR@1 | p_raw |
|---|---|---|---|---|---|---|
| agentclinic | 167 | 167 | 0.2874 | 0.2754 | -1.2pp | 0.8077 |
| llm_control | 167 | 167 | 0.5389 | 0.6407 | +10.2pp | 0.0586 |
| mdagents | 167 | 167 | 0.5509 | 0.6347 | +8.4pp | 0.1190 |
| medagents | 167 | 167 | 0.5449 | 0.6407 | +9.6pp | 0.0748 |

| case-level macro | Δ=+6.7pp | 95% CI [-1.8, 15.1] pp | permutation p=0.1247 |
|---|---|---|---|

**方向说明**：difficulty-matched 下 **并非所有系统方向都非负** —— AgentClinic 为 -1.2pp（agentclinic 为负）。作为 sensitivity analysis，不替代完整 clean set。

---

## 五、允许的论文结论

> **"After removing exact-identifier overlaps with identifier-bearing development sources, we found no statistically detectable post-cutoff degradation across the four evaluated systems."**

**不得使用**：contamination-free、guaranteed unseen、memorization is not the driver。时间措辞用 **"published after the prespecified cutoff"**。

---

## 六、交付文件（均在 `audit_frozen/temporal_v2_final/`）

| 文件 | 内容 |
|---|---|
| `temporal_overlap_audit.csv` | 每个被删除 case×dev-source 一行 |
| `temporal_holdout_clean_manifest.csv` | clean set 逐 split×system |
| `temporal_holdout_clean_results.csv` | per-system + strict/variant + CI + Δ + z + p_raw + p_holm |
| `temporal_holdout_difficulty_matched.csv` | 标签统一后 difficulty-matched per-system + macro |
| `temporal_holdout_case_system_long.csv` | 每行一个 case×system：split/case_id/system/attempted/successful/correct_variant/matched_flag/phenotype_bucket/prevalence_tier |
| `temporal_holdout_summary_v2.json` | 全部结果 + 标签统一规则 + allowed/forbidden claims |
| `temporal_pre/post_clean_case_ids.txt` | clean case lists（确定性排序 + 版本头） |
| `temporal_pre/post_matched_case_ids.txt` | difficulty-matched case lists |
| `temporal_holdout_audit_v2.md` | 本报告 |

`audit_frozen/results_snapshot.json` 从备份重建：删除旧 `temporal_holdout` 与伪重复 pooled p，写入 `temporal_holdout_v2`。
