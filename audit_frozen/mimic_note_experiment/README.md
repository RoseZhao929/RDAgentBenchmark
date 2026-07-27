# MIMIC-IV note-based, de-leaked rare-disease probe

新版 MIMIC 实验的**权威说明 + 数据筛选流程**。目标:用真实临床病历（MIMIC-IV-Note
出院小结）替换旧版"ICD 标题=答案"的输入，从根上修掉 data leakage，得到一个可信的
病历→罕见病诊断探针。

- 生成 (UTC): 2026-07-25
- 作者: 审计流程（Claude Code）
- 约束（务必遵守）
  - **PhysioNet DUA**：`data/` 全目录 gitignored，行级 MIMIC 文本/ID **绝不入库**；
    仅聚合计数、sha256、路径、provenance 可写进本文档与 git。
  - **不伪造**任何预测/分数；打分口径 = `audit_frozen/recompute_engine.py`
    （failures/timeout/parser-error 计入分母，variant-aware cross-map）。
  - 定位为**单独报告**的 code-supervised EHR 探针，**不进主诊断矩阵、不进 Avg**
    （gold 仍是 code-derived，非独立临床判读——见"诚实边界"）。

## 目录内容

| 文件 | 说明 |
|---|---|
| `README.md` | 本文件：完整筛选流程 + 复现命令 |
| `mimic_note_v2_status.md` | 数据准备阶段状态（解压/cohort/去泄露自检） |
| `mimic_note_v2_results.md` | 打分结果（DeepSeek 已定，Opus 待补） |

相关脚本（在 repo `scripts/` 下，除打分脚本外均无 LLM 调用，均确定性可复现）:
`build_mimic_note_deleaked.py` · `build_mimic_note_eval_subset.py` ·
`filter_mimic_note_prior_known.py` · `build_mimic_note_strict_A.py` ·
`build_mimic_note_cap.py` · `build_mimic_note_hpo_line.py` ·
`score_mimic_note_llm.py` · `stratify_mimic_note_scores.py` ·
`stratify_mimic_note_hpo.py` · `analyze_mimic_note_prevalence.py`

---

## 为什么要做这版（旧版的问题）

旧版 MIMIC 任务（`harness/ingest/mimic_iv.py`）:
- **输入** `synthetic_vignette` = 该 ICD 码的 ICD 长标题（`icd_title`）。
- **gold** = 同一 ICD 码经 Orphanet 映射（优先 `E` 精确关系）得到的 Orphanet 病名。

→ 输入里几乎逐字印着答案（如输入 "Cystic fibrosis with ..."，gold "Cystic fibrosis"）。
旧版 R@1 0.35–0.38 主要是**复读答案**，不是诊断能力。实测：去掉 target ICD 后
340/956=35.6% 的输入直接变空，其余仍印着答案标题。

三层问题，note 只能修第①层:
1. **data leakage**（答案印在题面）——note 版可修（本实验）。
2. **construct validity**（gold 是 ICD→Orphanet 码派生，非独立临床判读）——note 修不掉。
3. **task alignment**（ICD 码反映全次住院最终/账单诊断，非"从入院早期该推断什么"）——部分靠 principal 门缓解。

---

## 数据来源

| 数据 | 路径（gitignored） | 状态 |
|---|---|---|
| MIMIC-IV-Note 2.2 出院小结 | `data/mimic-iv-note-.../note/discharge.csv.gz` (1.1G) | 331,793 条 DS，gzip OK |
| MIMIC-IV 3.1 hosp 表 | `data/mimic-iv-3.1/hosp/*.csv.gz` | **主库 zip 下载截断**（5.62G/~7.0G），4 张 hosp 表按字节偏移抠出、gzip 全 OK；截断的是尾部 icu 表，不影响建 cohort |
| Orphanet en_product1 | `data/orphadata/en_product1.xml` (51M) | ICD-10↔Orphanet 映射 + DisorderFlag |

note 与 hosp 表经 `subject_id`/`hadm_id` join；出院小结覆盖 cohort 的 52.1%。

---

## 筛选流程（150,033 → 严格 A：capped 359 / uncapped 687）

每一步都是确定性的；每步产物、剩余数、脚本如下。

### 步 0 — 重建罕见病 cohort + gold
`harness/ingest/mimic_iv.py` 重跑（放宽到 E/NTBT/BTNT 三种关系）。
- 产物: `data/mimic_iv_rd_slice/cases_all_relations.jsonl`
- **150,033** 罕见病住院（E 107,144 / NTBT 37,872 / BTNT 5,017）。
- 注: 旧版"956 diverse"是这上面的采样/去重子集；v2 不再受 956 限制。

### 步 1 — 去泄露输入
`scripts/build_mimic_note_deleaked.py`:
- ① **presentation 截断**: 在首个诊断揭示段头（Brief Hospital Course /
  Discharge Diagnosis / Impression / Assessment and Plan / …）处切断，只留
  主诉、现病史、查体、检验、影像等入院早期信息。
- ② **gold 病名逐字 mask**: 大小写/空白不敏感替换为 `[MASKED_DIAGNOSIS]`。
- 产物: `note_deleaked_v1.jsonl`（78,166 例，sha256 `ecceb5f0…`）。
- **去泄露自检**: 截断后 gold 病名仍逐字出现 2,776/78,166=3.55%（旧版≈100%），
  全部 mask；`model_input` 残留 gold = **0**（程序化全量断言）。

### 步 2 — 四门"可评测"过滤
`scripts/build_mimic_note_eval_subset.py`，四门全过才可评测:

| 门 | 判据 | 理由 |
|---|---|---|
| 1. relation==E | ICD-10↔Orphanet 精确映射 | gold 唯一、无歧义 |
| 2. 真罕见 | 剔除 Orphanet 非罕见/废弃 flag（`{32,16,256,512,1024,8192}`）+ 名称以 "NON RARE" 开头；共排除 **1,829** 个 ORPHA id | 去掉 Parkinson/MS/高血压/HCC 等被误标的"罕见" |
| 3. principal | gold 码 = 本次住院主诊断（`diagnoses_icd.seq_num==1`, `icd_version==10`） | 罕见病是本次住院的原因，不是既往/次要码 → 与入院表现对齐 |
| 4. 有出院小结 | 该 hadm 存在 DS | 否则无 note 输入 |

- 漏斗: 150,033 → E 107,144 → +真罕见 18,392 → +principal 2,325 → +有 DS **1,255**（117 病）。
- 产物: `note_eval_subset_v1.jsonl`（1,255 例，sha256 `f5d9b437…`）。
- **漏斗本身即关键发现**: "本次住院主诊断就是真·罕见病且有病历"仅 ~1,255 例，
  其余罕见病码多是次要诊断/既往史（任务不对齐）或根本非罕见 → 量化了旧版 gold 的效度问题。

### 步 3 — 剔除既往已知病型（软泄露）
`scripts/filter_mimic_note_prior_known.py`:
- 问题: 即便 mask 了病名，"history of X" / "hx NMO on rituximab" / "s/p resection"
  这类结构仍把答案交给模型（软泄露）——这不是诊断，是复述既往史。
- 规则: 对每个 `[MASKED_DIAGNOSIS]` token 前后 45 字窗检查 history 线索（history of/
  hx/known/s\p/diagnosed with/on rituximab…）。命中则标 `prior_known` 并丢弃。
- 产物: `note_eval_subset_v2.jsonl`（**1,083** 例，112 病；丢弃 172 prior_known）。
- 同时打两个分层标记:
  - `history_undeterminable=true`（=**A 类**，855 例）: gold 名从未逐字出现 →
    规则无从判定既往，**保留**；这是最干净、必须真推理的子集。
  - `=false`（=**B 类**）: gold 名曾出现、已 mask → 文中提过该病，较可疑。

### A / B 分层（务必理解的反直觉点）

步 3 给每例打了 A/B 标记:
- **A 类（最干净）**: gold 病名在输入里**从未逐字出现**。必须从临床表现真推理。
- **B 类（较可疑）**: gold 病名曾出现、被 mask。文中提过该病 → 很可能是隐含既往诊断。

⚠️ 反直觉但正确: **逐字出现过 = 更可疑，不是"更合格"**。所以主结论看 A 类。

### 步 4 — 严格 A 类（堵同义词泄露，**主结果用这个**）
`scripts/build_mimic_note_strict_A.py`:
- 问题: 上面的 A 类只 mask 了 Orphanet **规范病名**，但评分器
  `gold_hit_with_crossmap` 也认**同义词/缩写/eponym**（HCC、ADPKD、PBC、GBS、
  ASD…）+ fuzzy≥90。病历里出现这些、模型抄到就算命中 → 原 A 类残留泄露。
- 做法: 用 Orphanet SynonymList（7030/11456 病有同义词）把每个 gold 的全部同义词
  也纳入 mask 与分类；任一同义词在输入中出现过 → 从 A 类降级。短全大写缩写
  （≤4 字符如 HCC/ASD）按大小写敏感的独立 token 匹配，避免误伤普通词。
- **诊断确认漏洞真实存在**: 原 A 类里 11.6%（cap 后）/19.6%（全量）病历含 gold 同义词。

### 步 5 — 每病均衡上限 10（防分布绑架）
`scripts/build_mimic_note_cap.py`（每病按 hadm_id 升序取前 10）:
- 目的: 防单一高频病主导指标（长尾问题，见下节"数据量与分布"）。
- 确定性: 该脚本可字节级重现现有 cap10 文件（sha 已核对一致）。

### 步 6 — HPO 线（与其它数据集器官系统分层对齐，**HPO 分层用这个**）
`scripts/build_mimic_note_hpo_line.py`（从 uncapped 严格 A 里只留"gold 病在
Orphadata `en_product4.xml` 有疾病级 HPO 标注"的病）:
- 目的: 其它四个数据集（RareBench/PhenoPacket-Store/LIRICAL/RAMEDIS）的输入本身
  就是 **case-level HPO 表型列表**，每个 case 100% 能映到 H7 器官系统 / H4 复杂度。
  MIMIC 自由文本**没有 case 级 HPO**，只能用"gold 病在 Orphanet 的疾病级表型列表"近似。
  能归类的前提 = gold 病在 en_product4 有标注。
- 结果: 687 → **416 例 / 68 病**（sha256 `67d156aa…`）。丢掉 271 例 / 37 病。
- ⚠️ **丢掉的 271 例是"标注缺失"，不是"质量差"**: Orphanet 对那 37 个病根本没做
  表型标注（en_product4 只覆盖我们 105 个 gold 病里的 68 个）。不得当成质量筛。
- ⚠️ **粒度差异必须声明**: 我们是 **disease-level** HPO（拿 gold 病的 Orphanet
  表型列表），其它数据集是 **case-level**（每个病人自己的表型）。故 416 是"结构上
  最接近"其它数据集的口径，非完全等价。

### 三条最终线（严格 A × cap / HPO）

| 线 | 例数 | 病种 | 用途 | 产物 |
|---|---|---|---|---|
| **capped 严格 A**（主指标） | **359** | 105 | 每病≤10，分布均衡，报 micro R@1 | `note_eval_strict_A_v1.jsonl` (sha `c3cb3adb…`) |
| **HPO 线**（器官系统分层，与其它数据集对齐） | **416** | 68 | 每病都可归 H7/H4，报 **macro**；不 cap（cap 是我们压 MIMIC 长尾自造的，其它数据集没有） | `note_eval_hpo_line_v1.jsonl` (sha `67d156aa…`) |
| uncapped 严格 A（附录） | 687 | 105 | 全量，样本最大，但**必须 macro-avg**，否则被长尾/高频扭曲 | 重跑 strict_A on `note_eval_subset_v2.jsonl` |

注: 三条线**都用同一批已有回执重算**，不再花钱（预测已存于 687 全集，子集只重算命中）。
416⊂687，两模型均 416/416 全覆盖（Opus 全 ok；DeepSeek 401 ok + 15 parser_error，
计入分母算 miss）。

---

## 数据量与分布（359 够吗？丢回全量会不会不均？）

**359 够用**——与其它数据集同量级或更大:
MME 40 / RareBench HMS 88 / PMC holdout 198–220 / **MIMIC 严格A capped 359** /
LIRICAL 370 / RAMEDIS 624 / **MIMIC 严格A uncapped 687**。
359 例上 R@1≈0.19 的标准误约 ±2%，作为单独探针站得住。

**丢回全量（687）分布严重长尾**（这是为什么保留 cap）:
- top10 病占 **52%**，最大单病（Primary localized amyloidosis）占 8.6%；
- 105 病里 **39%（41 个）只有 1 例**。
- 后果: 不 cap 且用 micro 平均 → 总分被少数高频病绑架，不反映长尾罕见病能力。
- 因此 uncapped 若要用，**必须 macro-average（每病先算 R@1 再对病种平均）**。

**359 不是"零问题"**——仍有两类残留（见下"诚实边界"）:
paraphrase 型既往史（不含病名，规则抓不到）；gold 仍 code-derived（构念边界，
任何字符串处理都修不掉）。故**单独报告、不进主 Avg**；不得声称"保证干净"。

---

## HPO 器官系统分层（416 线，`scripts/stratify_mimic_note_hpo.py`）

器官系统方案 = `hp.obo` 中 HP:0000118 的顶层子节点（~23 类"器官系统"），与本 benchmark
其它数据集的 H7 specialty 轴**同一套**（`ablation_H4_H7_specialty.py`）。H4 复杂度 = gold 病
表型涉及的**不同器官系统数**（single=1 / oligo=2-3 / multi=4+）；H7 = **modal**（最高频）系统。

**总体（416 / 68 病）**: Opus micro 0.272 / **macro 0.197** · DeepSeek micro 0.070 / **macro 0.048**。

| H7 器官系统 | n / 病 | Opus micro/macro | DeepSeek micro/macro |
|---|---|---|---|
| nervous 神经 | 103 / 11 | 0.534 / 0.270 | 0.185 / 0.117 |
| respiratory 呼吸 | 101 / 5 | **0.0 / 0.0** | 0.0 / 0.0 |
| digestive 消化 | 61 / 8 | 0.377 / 0.339 | 0.131 / 0.083 |
| immune 免疫 | 61 / 10 | 0.164 / 0.182 | 0.0 / 0.0 |
| cardiovascular 心血管 | 33 / 13 | 0.152 / 0.167 | 0.030 / 0.077 |
| blood 血液 | 18 / 7 | 0.444 / 0.264 | 0.0 / 0.0 |
| integument 皮肤 | 14 / 6 | 0.214 / 0.167 | 0.071 / 0.056 |
| genitourinary 泌尿生殖 | 12 / 3 | 0.75 / 0.30 | 0.0 / 0.0 |
| musculoskeletal 肌肉骨骼 | 8 / 3 | 0.0 / 0.0 | 0.0 / 0.0 |

**H4 复杂度**: multi(4+) 386例 Opus 0.238/0.192 · oligo(2-3) 30例 Opus 0.70/0.304。
**罕见度**（注意**非单调**）: moderate 0.390 · rare 0.102 · ultra **0.710** · super-rare 0.409（Opus micro）。

**读这三张表必须带的三条限定**:

1. **micro 会被长尾+误分类扭曲，看 macro**。典型: "呼吸系统" 101 例两模型全 0，但拆开看
   101 例里 **54 例是 Idiopathic achalasia（贲门失弛缓，实为食管/消化病）**、21 例 ARDS（急性
   呼吸窘迫，更像危重症）——① 75/101 就俩病（长尾），② disease-level modal-system 把 achalasia
   因 HPO 带误吸/呼吸表型**误分成呼吸系统**。这正是"疾病级 HPO ≠ 病例级"的实证。

2. **罕见度不单调预测难度**: ultra-rare 反而最高（0.71）。有 HPO 标注的超罕见病常是表型极
   鲜明的综合征，好认；低分主要出现在"标注缺失/prev.xml 缺失"那批，是**标注缺失导致**，
   不是"越罕见越难"。

3. **粒度声明**（重复但关键）: H7/H4 基于 gold 病的**疾病级** Orphanet 表型列表，非病人**病例级**
   表型；且受 68/105=65% 疾病级标注覆盖限制。与其它数据集"结构对齐"，非完全等价。

---

## 打分（步 6，最后一步）

见 `mimic_note_v2_results.md`。`scripts/score_mimic_note_llm.py` 对 cap10 子集调
backbone 出 top-5 鉴别诊断，`stratify_mimic_note_scores.py` 出 A/B/all 分层 R@1/R@5。

| 子集 | DeepSeek V4 R@1 | Opus 4.8 R@1 |
|---|---|---|
| **严格 A 类 (359)** ← 主结果 | **0.033** | **0.189** |
| 原 A 类 (406) | 0.030 | 0.217 |
| B 类 (85) | 0.165 | 0.718 |
| 全体 (491) | 0.053 | 0.304 |

**结论**（"3% 是任务难还是模型弱"）: 主要是模型弱——严格 A 类上 Opus 0.189 是
DeepSeek 0.033 的 ~5.7×。但去泄露后强模型也明显掉分（Opus 0.189 vs 旧版
0.35–0.38，掉 ~50%），说明旧数里相当一块是复读答案。堵掉同义词泄露后 Opus 再掉
~13%（0.217→0.189）。**净结论: 强模型真实 top-1 ≈ 19%，弱模型 ≈ 3%。**
详见 `mimic_note_v2_results.md`。

---

## 诚实边界（写进 paper 必须声明）

1. **gold 仍 code-derived**（ICD→Orphanet），非独立临床判读——note 修不掉的构念边界。
   只修了 leakage（①），没修 construct validity（②）。故单独报告，不进主矩阵/Avg。
2. 截断/mask/prior-known 均为**规则式**去泄露，非人工判读；A 类无法排除 paraphrase
   型既往史（"a chronic autoimmune condition treated with…"），B 类明确较脏。
3. presentation 段里可能仍有典型影像/检验线索指向诊断——这属于"合理诊断线索"，
   不是"答案逐字泄露"。
4. note 覆盖率 52.1% → 有/无 note 的住院可能有 selection bias。
5. 主库 zip 截断 → 若要做"早窗 24/48h icu 结构化线"需重新完整下载主库；本实验用出院小结
   presentation 段，不依赖 icu 表。

---

## 复现命令

```bash
cd /home/research/RDAgentBenchmark

# 步0 cohort（需 hosp 4 表在 data/mimic-iv-3.1/hosp/）
python3 -c "from harness.ingest.mimic_iv import write_canonical_jsonl; \
  write_canonical_jsonl('data/mimic_iv_rd_slice/cases_all_relations.jsonl', \
  'data/mimic-iv-3.1','data/orphadata/en_product1.xml',('E','NTBT','BTNT'))"

# 步1 去泄露 note 输入
python3 scripts/build_mimic_note_deleaked.py --output data/mimic_iv_rd_slice/note_deleaked_v1.jsonl

# 步2 四门可评测子集
python3 scripts/build_mimic_note_eval_subset.py --output data/mimic_iv_rd_slice/note_eval_subset_v1.jsonl

# 步3 剔除既往已知病型
python3 scripts/filter_mimic_note_prior_known.py \
  --input data/mimic_iv_rd_slice/note_eval_subset_v1.jsonl \
  --output data/mimic_iv_rd_slice/note_eval_subset_v2.jsonl

# 步4 每病上限10（从 v2 均衡采样）
python3 scripts/build_mimic_note_cap.py --cap 10 \
  --input  data/mimic_iv_rd_slice/note_eval_subset_v2.jsonl \
  --output data/mimic_iv_rd_slice/note_eval_cap10_v2.jsonl

# 步5 打分（需 LITELLM_API_KEY；默认 dry-run，--live 才真调）
LITELLM_API_KEY=... python3 scripts/score_mimic_note_llm.py --live \
  --input  data/mimic_iv_rd_slice/note_eval_cap10_v2.jsonl \
  --output data/mimic_iv_rd_slice/predictions_mimic_note_deepseek_v4.jsonl \
  --model deepseek-v4-flash --backbone-id litellm/deepseek-v4-flash

# 步6 HPO 线（只留有疾病级 HPO 标注的病；416/68）
python3 scripts/build_mimic_note_hpo_line.py \
  --output data/mimic_iv_rd_slice/note_eval_hpo_line_v1.jsonl

# A/B 分层 R@1/R@5（cap10 子集）
python3 scripts/stratify_mimic_note_scores.py \
  --preds data/mimic_iv_rd_slice/predictions_mimic_note_deepseek_v4.jsonl --label "DeepSeek V4"

# HPO 器官系统 / 复杂度 / 罕见度分层（416 线，micro+macro，复用回执不花钱）
python3 scripts/stratify_mimic_note_hpo.py \
  --subset data/mimic_iv_rd_slice/note_eval_hpo_line_v1.jsonl \
  --preds data/mimic_iv_rd_slice/predictions_mimic_note_opus48.jsonl \
          data/mimic_iv_rd_slice/predictions_mimic_note_deepseek_v4.jsonl
```
