# Temporal-Holdout 最终冻结结果 (v2) — disjoint set + 去伪重复重算

> 只重算与核验。**未修改论文文字，未调用任何 LLM**，只用磁盘上已有的 pre/post prediction receipts。
> 本报告取代 v1 (`audit_frozen/consistency_report.md` §6/§9.1–§9.2 与 `temporal_holdout_audit.csv`)。

- Data version: slim recompute set (MIMIC 与权重已从 git history 剥离)
- Commit: `9babd833618936b6b29942baba130638e212921d`
- 生成时间 (UTC): 见 `temporal_holdout_summary_v2.json:generated_at_utc`
- 生成脚本: `audit_frozen/temporal_v2/build_temporal_v2.py`
- Backbone: Gemini 3 Flash (唯一 pre/post **两侧都齐** 的 backbone；post 另有 DS-V4-Flash 但 pre 无对照，故排除)
- Systems: `llm_control`, `mdagents`, `medagents`, `agentclinic` (4 个两侧都有结果的系统)

---

## 一、统一 publication identity 与 disjoint test set 构建

对每个 pre/post case 建立统一身份。**冻结数据里实际可用的键**：

| 键 | holdout 来源 | dev 层来源 |
|---|---|---|
| PMCID | case_id `pmc_<PMCID>` | RareArena `_id` 前缀 `<PMCID>-n` |
| PMID | `data/pmc_*/02_pmid_to_pmc.jsonl` | Phenopacket case_id `PMID_<pmid>_...` |
| source case ID | case_id | dataset-native id |

**DOI 与 normalized title 在所有冻结产物里都不存在** —— overlap 审计 CSV 保留了这两列但为空，并如实标注。exact-ID 交集因此建立在 **PMCID + PMID**（都是精确匹配）之上。

**各 development layer 的交集结果（对 union 去重，不只 RareArena）：**

| dev 层 | 匹配键 | 可交集? | pre overlap | post overlap |
|---|---|---|---|---|
| RareArena RDS | PMCID | ✅ | 13 | 17 |
| Phenopacket Store | PMID | ✅ | 1 | 1 |
| **RareBench** | — | ❌ **shipped 数据只有 Department/Phenotype/RareDisease，无任何出版物 ID** | 不可查 | 不可查 |
| 其他 PMC prompt/adapter dev cases | — | ❌ 本 checkout 内无 case-report 语料 (`agents/vc_rdagent/*` 是 ontology，非 PMC 病例) | — | — |

⚠️ **RareBench 无法做 ID 交集**，因此本 test set 只能声明"已移除对 RareArena+Phenopacket 的 exact-ID overlap"，**不能声明与全部 development 层 disjoint**。这是覆盖限制，不是"无重叠"。

### overlap union（关键：不是简单相加）

| split | 总病例 | RareArena overlap | Phenopacket overlap | **union** | **clean N** |
|---|---|---|---|---|---|
| pre_cutoff | 220 | 13 | 1 | **14** | **206** |
| post_cutoff | 198 | 17 | 1 | **18** | **180** |

Phenopacket 的 PMID-overlap 病例 (`pmc_11088039` post / `pmc_7653328` pre) 与 RareArena 的 PMCID-overlap **不相交**，所以 union = 13+1 = 14、17+1 = 18，clean N 落到 **206 / 180 —— 不是预设的 207/181**。任务里的告诫成立。

### gold ORPHA 一致性（诚实修正 v1 的 "17/17")

逐病例比对 holdout gold 与 dev gold（原始字符串比对）：**32 条 overlap 里 23 match / 9 differ**。

- RareArena PMCID overlaps：多数 gold ORPHA 完全一致（如 PMC10783329 两边都是 ORPHA:139399），但**有约 7 条 differ**（subtype 粒度或 ORPHA 层级不同）。
- Phenopacket 的 2 条是 **OMIM vs ORPHA 跨词表**（如 ORPHA:15 vs OMIM:305400），字符串必然 differ —— 本列未做 OMIM↔ORPHA 交叉映射，differ 不代表真不一致。

**结论：overlap 判定基于 publication identity（PMCID/PMID）本身，与两层是否给了同一 ORPHA 粒度无关** —— 同一篇 case report 进了 dev 层就是污染，与标注粒度无关。逐病例明细见 `temporal_overlap_audit.csv`（含 split / case_id / PMCID / PMID / DOI(空) / dev source / dev case id / gold agreement / removal reason）。

---

## 二、冻结 clean case lists

- `temporal_pre_clean_case_ids.txt` (206 ids)
- `temporal_post_clean_case_ids.txt` (180 ids)

均按确定性排序 (`sorted`)，文件头记录 data_version / 生成脚本 / commit / 生成时间。
- `temporal_overlap_audit.csv` — 每个被删除 case×source 一行。

---

## 三、per-system 结果 (clean set, 同系统同 backbone 两侧都有)

见 `temporal_holdout_clean_results.csv` / `temporal_holdout_clean_manifest.csv`。attempted 分母、variant-aware 为 primary，failures 保留在分母。四系统做 **Holm-Bonferroni** 校正（family size = 4）。

| system | n_pre | n_post | pre R@1 | post R@1 | ΔR@1 | 95% CI(post) | z | p_raw | **p_holm** |
|---|---|---|---|---|---|---|---|---|---|
| agentclinic | 206 | 180 | 0.257 | 0.283 | +2.6pp | [0.217,0.350] | 0.58 | 0.565 | **0.565** |
| llm_control | 206 | 180 | 0.539 | 0.628 | +8.9pp | [0.556,0.694] | 1.77 | 0.077 | **0.224** |
| mdagents | 206 | 180 | 0.544 | 0.633 | +9.0pp | [0.561,0.700] | 1.78 | 0.075 | **0.224** |
| medagents | 206 | 180 | 0.529 | 0.639 | +11.0pp | [0.567,0.706] | 2.18 | 0.029 | **0.117** |

- 全部四个系统 ΔR@1 **方向为正**（post ≥ pre），即 cutoff 之后的新病例上不差于之前。
- **Holm 校正后无一显著**（最小 p_holm = 0.117）。failures 极少（仅 mdagents pre 1 例 parser_error），strict/variant 双列见 CSV。

---

## 四、pooled analysis 修正（去 pseudo-replication）

**v1 的 pooled z-test（pre 0.461 → post 0.538, z=3.12, p=0.0018）作废** —— 它把同一病例在 4 个系统上的结果当成 4 个独立观测，存在 pseudo-replication，显著性被人为放大。

改用 **case-level macro**（抽样单位 = 病例）：

1. 每个病例取 4 系统 correctness 的平均；
2. pre/post 以病例为单位比较；
3. **cluster bootstrap**（同一病例的 4 系统结果一起重采样，10,000 次）+ permutation test（10,000 次）。

| 口径 | pre macro R@1 (n) | post macro R@1 (n) | Δ | 95% CI | permutation p |
|---|---|---|---|---|---|
| clean set | 0.467 (206) | 0.546 (180) | **+7.9pp** | **[+0.1, +15.6] pp** | **0.051** |

case-clustered 之后 Δ 仍为正、CI 下界几乎贴 0、p≈0.05 **不显著**。这印证了任务判断：v1 的 p=0.0018 是伪重复的产物；正确口径下"post 更好"**够不上统计显著**。

（也可只把 per-system 结果作为 primary，不强制给 pooled significance。）

---

## 五、difficulty-matched sensitivity analysis

匹配在 **case level** 完成（先匹配再算，不先扩成 system×case rows）。特征：phenotype-count 分桶 (`<=5/6-15/16-30/>30`) × prevalence tier（Orphadata en_product9_prev）。disease category 因缺失率高未纳入匹配。在 (pheno_bkt × prev_tier) 上取两侧共有 strata，每 stratum 取 min-count。

- **unknown prevalence 比例**：pre ≈ 37% / post ≈ 34%（约 1/3 病例 Orphadata 无 prevalence tier，如实标注，匹配只在有 tier 的病例上做）。
- matching 前后分布见 `temporal_holdout_summary_v2.json:difficulty_matched.balance_before/after`。
- **retained: 165 / 165**。

| 口径 | pre macro R@1 | post macro R@1 | Δ | 95% CI | permutation p |
|---|---|---|---|---|---|
| difficulty-matched (case-level macro) | 0.485 (165) | 0.549 (165) | +6.4pp | [−2.1, +14.7] pp | 0.153 |

per-system 明细见 `temporal_holdout_difficulty_matched.csv`。difficulty-matched Δ 仍为正但更不显著（CI 跨 0）。**作为 sensitivity analysis，不替代完整 clean set。**

---

## 六、允许的论文结论

结果方向在所有系统、clean set、difficulty-matched 下均保持非负，因此可写：

> **"After removing cases overlapping with development data, none of the four evaluated systems showed detectable post-cutoff degradation."**

**不得写**（本审计明确不支持）：

- ❌ "the holdout is contamination-free" —— RareBench 层无 ID 无法查；LLM 预训练曝露不在本地数据可查范围。
- ❌ "memorization is not the driver"。
- ❌ "post-cutoff performance is significantly better" —— case-clustered / Holm 校正后**不显著**（macro p≈0.05，Holm 全部 >0.11）。
- ❌ "after every model's training cutoff" —— 无官方训练截止日期证据。

时间措辞用 **"published after the prespecified cutoff"**，而非 "guaranteed unseen by the models"。

---

## 七、交付文件（均在 `audit_frozen/temporal_v2/`）

| 文件 | 内容 |
|---|---|
| `temporal_overlap_audit.csv` | 每个被删除 case×dev-source 一行：split/case_id/PMCID/PMID/DOI(空)/title(空)/dev source/dev case id/match key/gold agreement/removal reason |
| `temporal_holdout_clean_manifest.csv` | clean set 逐 split×system：full/removed/clean N + attempted/successful + failures by type + strict/variant R@1 + CI |
| `temporal_holdout_clean_results.csv` | per-system pre/post + failures + strict & ontology-normalized R@1 + CI + Δ + z + p_raw + **p_holm** |
| `temporal_holdout_difficulty_matched.csv` | difficulty-matched per-system + case-level macro |
| `temporal_holdout_summary_v2.json` | 全部：identity model / 各源 overlap / union / clean N / per-system / Holm / case-level macro / difficulty-matched balance / allowed & forbidden claims |
| `temporal_pre_clean_case_ids.txt`, `temporal_post_clean_case_ids.txt` | 冻结 clean case lists（确定性排序 + 版本头） |
| `temporal_holdout_audit_v2.md` | 本报告 |

`audit_frozen/results_snapshot.json` 已更新：删除旧 contaminated pooled headline，写入 `temporal_holdout_v2`（clean N / overlap union / per-system + Holm / case-level macro / `development_overlaps_found_and_removed: true`）。原文件备份于 `results_snapshot.json.pre_temporal_v2.bak`。
