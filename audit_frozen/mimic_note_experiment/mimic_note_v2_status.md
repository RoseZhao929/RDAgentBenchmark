# MIMIC-IV v2 (note-based, de-leaked) — build status

- 生成 (UTC): 2026-07-24
- 约束: 未调用任何 LLM；未伪造任何预测/分数；行级 MIMIC 数据全部 gitignored（仅代码/聚合/hash 可入库）。

## 发生了什么

MIMIC-IV-Note 已下载到 `data/mimic-iv-note-.../note/`（`discharge.csv.gz` 1.1G、`radiology.csv.gz` 746M，gzip 校验 OK）。
这解锁了从**临床病历文本**做罕见病诊断的 v2 任务，从根本上修掉 v1 的 data leakage（v1 是把 ICD 标题=答案塞进输入）。

我已把「只差跑模型」之前的**全部数据准备**做完了，全程**不花钱、不调 LLM、确定性可复现**：

| 步 | 结果 |
|---|---|
| 解压主库 hosp 表 | 主库 `mimic-iv-3.1.zip` **下载被截断**（5.62G / 官方 ~7.0G，末尾无 zip 中央目录）。但需要的 4 张 hosp 表都在完好区内，按字节偏移抠出、gzip 校验全 OK：`diagnoses_icd`(6.36M行)/`d_icd_diagnoses`(112K)/`admissions`(546K)/`patients`(365K)。截断掉的是尾部 icu 大表，不影响建 cohort。 |
| 重建罕见病 cohort + gold | `harness/ingest/mimic_iv.py` 重跑，产出 **150,033** 罕见病住院（E 107,144 / NTBT 37,872 / BTNT 5,017）→ `data/mimic_iv_rd_slice/cases_all_relations.jsonl`。注：历史「956 diverse」是这上面的采样/去重子集，v2 不再受限于 956。 |
| join 病历 + 覆盖率 | 出院小结覆盖 hadm 331,793 个。cohort 里 **78,166 / 150,033 = 52.1%** 有出院小结（E-only 55,503 = 51.8%）。→ v2 可用盘子是**几万例**，远超旧 956。 |
| 构造去泄露输入 | `scripts/build_mimic_note_deleaked.py`：① 在首个诊断揭示段（Brief Hospital Course / Discharge Diagnosis / Impression / …）处截断，只留 presentation（主诉/现病史/查体/影像/检验）；② 把 gold 病名逐字 mask。产出 78,166 例 → `note_deleaked_v1.jsonl`（sha256 `ecceb5f0…`）。 |

## 去泄露自检（核心证据）

| 指标 | 值 | 含义 |
|---|---|---|
| 截断后 gold 病名仍逐字出现的 case | **2,776 / 78,166 = 3.55%** | v1 里几乎 100%（答案=输入）；v2 截断后只剩 3.55%，再被 mask |
| mask 掉的逐字出现总数 | 4,976 | 全部替换为 `[MASKED_DIAGNOSIS]` |
| model_input 里残留 gold | **0**（构造上保证） | 程序化断言全量核过：0 个诊断段头泄露、0 个 gold 逐字泄露 |
| 空输入 | 0 | median 输入 5,222 字符，真实临床文本 |

对比 v1 的真实 cohort 实测（handoff）：v1 去掉 target 后 340/956=35.6% 直接变空、其余仍印着答案标题。v2 从"答案印在题面"变成"给临床表现、答案藏起来"——**这才是真正的鉴别诊断输入**。

## 还差最后一步（要花钱、要授权）

跑 agent×backbone 模型矩阵，对 `note_deleaked_v1.jsonl` 打分 → 得到去泄露的真实 R@1。
- 受"no new LLM calls"约束，**未擅自开跑**，等你明确授权并定预算。
- 预算可控：可先在**分层子样本**（如每个 relation 抽 N 例、或 E-only 500 例）上跑一轮定标，再决定是否上全量。
- 打分口径沿用 `audit_frozen/recompute_engine.py`（failures 计入分母）。

## 诚实边界（写进 paper 时必须声明）

1. **gold 仍是 code-derived**（ICD→Orphanet 映射），不是独立临床判读——这是构念边界，note 修不掉。v2 只修了 leakage（①），没修 construct validity（②）。仍应作为**单独报告的结构化/病历 EHR 探针**，不进主诊断矩阵、不进 Avg。
2. 截断/mask 是**规则式**去泄露，非人工判读；presentation 段里仍可能有弱线索指向诊断（如典型影像描述），但这属于"合理的诊断线索"，不是"答案逐字泄露"。
3. 主库 zip 截断需**重新完整下载**才能拿到 icu 事件表做「早窗 24/48h 结构化」那条线；当前 v2 用的是出院小结 presentation 段，不依赖 icu 表。
4. 覆盖率 52.1% 意味着有 note 的与无 note 的住院可能存在系统差异（selection bias），分析时应对比两组基线特征。

## 复现命令

```bash
# 1) cohort（需 hosp 4 表在 data/mimic-iv-3.1/hosp/）
python3 -c "from harness.ingest.mimic_iv import write_canonical_jsonl; \
  write_canonical_jsonl('data/mimic_iv_rd_slice/cases_all_relations.jsonl', \
  'data/mimic-iv-3.1','data/orphadata/en_product1.xml',('E','NTBT','BTNT'))"

# 2) 去泄露 note 输入
python3 scripts/build_mimic_note_deleaked.py \
  --output data/mimic_iv_rd_slice/note_deleaked_v1.jsonl
```
