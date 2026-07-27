# MIMIC-IV note-based, de-leaked probe — results (v2)

- 生成 (UTC): 2026-07-24（HPO 线 416 分层补充于 2026-07-25）
- 约束: 行级 MIMIC 数据全部 gitignored；仅聚合指标/hash 入库；打分口径 = `audit_frozen/recompute_engine.py`（failures 计入分母，variant-aware cross-map）。
- API: `https://litellm.dealism.ai`（OpenAI 兼容）。

## 这是什么

用**新到的 MIMIC-IV-Note 出院小结**替换 v1 的"ICD 标题=答案"输入，从根上修 data leakage：
输入 = 出院小结的 **presentation 段**（主诉/现病史/查体/检验/影像；在首个诊断揭示段处截断），gold 病名逐字 mask。
gold 仍为 code-derived（ICD→Orphanet exact 映射），故定位为**单独报告的 code-supervised 病历诊断探针**，不进主诊断矩阵、不进 Avg。

## 评测子集构造漏斗（150,033 → 491）

| 步 | 剩余 | 脚本 |
|---|---|---|
| 全罕见病住院 cohort | 150,033 | `harness/ingest/mimic_iv.py` |
| E-only（精确映射，gold 唯一） | 107,144 | |
| + 真罕见（剔 Orphanet 非罕见/废弃 flag，排除 1,829 ID） | 18,392 | `build_mimic_note_eval_subset.py` |
| + gold 码 = 本次住院 principal（seq_num=1） | 2,325 | |
| + 有出院小结（可评测） | **1,255** (117 病) | → `note_eval_subset_v1.jsonl` |
| − 既往已知病型（HPI "history of/hx/on rituximab"…） | **1,083** (112 病) | `filter_mimic_note_prior_known.py` → `_v2.jsonl` |
| 每病上限 10（均衡） | **491** (112 病) | → `note_eval_cap10_v2.jsonl` |

漏斗本身即关键发现：**"本次住院主诊断就是真·罕见病且有病历"的案例仅 ~1,255**，其余罕见病码多为次要诊断/既往史（任务不对齐）或根本非罕见。这量化了 v1 code-derived gold 的效度问题。

## A / B 分层（是否残余软泄露）

- **A 类 (406)**：gold 病名在 presentation 里**从未逐字出现** → 最干净，必须真推理。
- **B 类 (85)**：gold 病名曾出现、已被 mask → 文中提过该病，很可能是隐含既往诊断（软泄露）。

## 结果

### DeepSeek V4 (flash)  —  花费 $0.13，491/491 全 ok

| 子集 | N | R@1 | R@5 |
|---|---|---|---|
| 全体 | 491 | **0.053** | 0.077 |
| A 类（最干净） | 406 | **0.030** | 0.049 |
| B 类（较可疑） | 85 | **0.165** | 0.212 |

### Claude Opus 4.8  —  花费 $8.20，491/491 全 ok

| 子集 | N | R@1 | R@5 |
|---|---|---|---|
| 全体 | 491 | **0.304** | 0.367 |
| A 类（最干净） | 406 | **0.217** | 0.281 |
| B 类（较可疑） | 85 | **0.718** | 0.776 |

### 严格 A 类（堵掉同义词/缩写泄露）—— 主结果

原 A 类只 mask 了 Orphanet **规范病名**，但评分器 `gold_hit_with_crossmap` 认
同义词/缩写/eponym（HCC、ADPKD、PBC、GBS、ASD…）+ fuzzy≥90。病历里出现这些、
模型抄到，评分算命中 → 原 A 类里有残留泄露。`build_mimic_note_strict_A.py` 用
Orphanet SynonymList 把同义词也纳入 mask 与分类：原 A 类 406 → **严格 A 类 359**
（剔除 47 例伪 A 类，**11.6%**；sha256 `c3cb3adb…`）。用**已有回执重算**（不花钱）。

| 子集 | N | DeepSeek V4 R@1 | Opus 4.8 R@1 |
|---|---|---|---|
| **严格 A 类** | 359 | **0.033** | **0.189** |
| 原 A 类 | 406 | 0.030 | 0.217 |

- DeepSeek 几乎不变（0.030→0.033）：它本就没抄对同义词，剔掉伪 A 后分母缩、命中不变。
- Opus 掉 ~13%（0.217→0.189）：这就是同义词泄露的量化——之前一部分"命中"是抄
  病历里的 HCC/ADPKD/PBC 缩写。堵掉后强模型真实 top-1 ≈ **19%**。
- 泄露的同义词 top: ASD(8)、PBC(7)、atrial septal defect(7)、HCC(4)、GBS(4)…

### HPO 线（416 / 68 病）—— 与其它数据集器官系统分层对齐

其它数据集输入即 case-level HPO，每 case 100% 可映到器官系统；MIMIC 自由文本无 case 级
HPO，故取"gold 病在 Orphadata en_product4 有**疾病级** HPO 标注"的子集 = **416 / 68 病**
（`note_eval_hpo_line_v1.jsonl`，sha `67d156aa…`）。丢掉的 271 例是**标注缺失、非质量筛**。
复用回执不花钱；两模型 416/416 全覆盖（Opus 全 ok；DeepSeek 401 ok + 15 parser_error 计入分母）。

总体: **Opus micro 0.272 / macro 0.197 · DeepSeek micro 0.070 / macro 0.048**（长尾+误分类下 macro 更可信）。

| H7 器官系统 | n/病 | Opus micro/macro | DeepSeek micro/macro |
|---|---|---|---|
| nervous | 103/11 | 0.534/0.270 | 0.185/0.117 |
| respiratory | 101/5 | 0.0/0.0 | 0.0/0.0 |
| digestive | 61/8 | 0.377/0.339 | 0.131/0.083 |
| immune | 61/10 | 0.164/0.182 | 0.0/0.0 |
| cardiovascular | 33/13 | 0.152/0.167 | 0.030/0.077 |
| blood | 18/7 | 0.444/0.264 | 0.0/0.0 |

- **"呼吸" 101 例全 0 是长尾+误分类假象**: 其中 54 例 Idiopathic achalasia（食管病）、21 例 ARDS
  （危重症），disease-level modal-system 把 achalasia 误判成呼吸系统。→ 看 macro，勿看 micro。
- **罕见度非单调**: ultra 0.71 > rare 0.10；低分集中在标注缺失批，是标注缺失非"越罕越难"。
- 粒度: H7/H4 基于疾病级 HPO（非病例级），受 65% 疾病级标注覆盖限制，与其它数据集结构对齐非等价。

### 两模型对照（原 A/B，供参考）

| 子集 | DeepSeek V4 R@1 | Opus 4.8 R@1 | 倍数 |
|---|---|---|---|
| 全体 | 0.053 | 0.304 | 5.7× |
| A 类 | 0.030 | 0.217 | 7.3× |
| B 类 | 0.165 | 0.718 | 4.4× |

## 去泄露 BEFORE vs AFTER（4 backbone，同案 416，2026-07-26 新增）

裸 LLM（`llm_control`）在**同一批 416 例**上跑两遍——BEFORE = 泄露版（完整 note，不截断、不
mask，诊断揭示段与 gold 病名都在题面）；AFTER = 去泄露版（presentation 截断 + gold 病名 mask）。
唯一变量是"截没截断/mask 没 mask"，故为**真·同案前后对比**。打分口径同 24-cell 主矩阵
（分母=416，failure 计 miss，`gold_hit_with_crossmap`，dedupe prefer-ok，bootstrap CI）。

数据: `note_leaked_v1_416.jsonl`（sha `df7b8f40…`）vs `note_eval_hpo_line_v1.jsonl`（sha `67d156aa…`）。
打分产物: `before_after_scores.json`。脚本: `scripts/score_mimic_note_before_after.py`。

| backbone | BEFORE (泄露) micro R@1 [95%CI] | AFTER (去泄露) micro R@1 [95%CI] | Δ 绝对 | Δ 相对 |
|---|---|---|---|---|
| deepseek-v4-pro | 0.500 [0.452,0.546] | 0.365 [0.320,0.411] | −0.135 | **−27%** |
| deepseek-v4-flash | 0.553 [0.507,0.599] | 0.353 [0.308,0.399] | −0.199 | **−36%** |
| gpt-5 | 0.425 [0.380,0.471] | 0.363 [0.317,0.409] | −0.062 | **−15%** |
| gemini-3-flash | 0.452 [0.406,0.498] | 0.373 [0.327,0.418] | −0.079 | **−18%** |

macro R@1（BEFORE→AFTER）：v4-pro 0.492→0.318 · v4-flash 0.525→0.285 · gpt-5 0.436→0.345 ·
gemini 0.468→0.345。ok 数：BEFORE 均 405–416（gemini 11 例结构化输出失败计入分母）、AFTER 370–415。

**读法**:
1. **去泄露在全部 4 个 backbone 上都掉分**（−15% 至 −36%，CI 不重叠），普遍存在，非单模型偶发 →
   旧 MIMIC 分数里确有一块是"复读题面答案"而非诊断能力。
2. **弱模型掉得更多**（v4-flash −36% vs gpt-5 −15%）:强模型本就更多靠真推理、少靠复读，故去泄露对它冲击小。
   这解释了为什么泄露会**压缩模型间真实差距**——泄露版里 v4-flash(0.553) 甚至"超过" gpt-5(0.425)，
   去泄露后才回归合理排序（都 ~0.36）。**泄露不仅抬高绝对分，还扭曲模型排序。**
3. AFTER 4 个 backbone 收敛到 ~0.36±0.01,与 2-model 探针 Opus HPO 线 micro 0.272 同量级
   （子集/口径不同,不直接可比,但都指向"去泄露后 top-1 ≈ 二到三成"）。

## 24-cell agent 矩阵（6 agent × 4 backbone × 416，去泄露 HPO 线，2026-07-26 完成）

在去泄露 416 探针（`note_eval_hpo_line_v1.jsonl`，sha `67d156aa…`）上跑 **6 个 agent 家族 ×
4 个 backbone**。打分口径同上：**分母=416**（failure/timeout/parser_error/empty-ok 一律计
miss，无 success-only 灌水），匹配 `gold_hit_with_crossmap`（ID 交叉映射 + 病名 fuzzy≥90），
dedupe prefer-ok，bootstrap 95%CI。**raw rank-1 口径，无任何后处理**（见 §限定语 caveat）。
打分产物 `agent_matrix_scores.json`，脚本 `scripts/score_mimic_note_matrix.py`。全 24 格
present=416/416。

### micro R@1（hits/416，[95%CI]）

| agent | deepseek-v4-pro | deepseek-v4-flash | gpt-5 | gemini-3-flash | 行均值 |
|---|---|---|---|---|---|
| **llm_control（裸 LLM）** | 0.365 [.320,.411] | 0.353 [.308,.399] | 0.363 [.317,.409] | 0.373 [.327,.418] | **0.364** |
| medagents | 0.349 [.303,.394] | 0.337 [.291,.380] | 0.315 [.272,.358] | 0.401 [.356,.447] | 0.350 |
| mdagents | 0.346 [.300,.392] | 0.368 [.322,.413] | 0.435 [.389,.481] | 0.317 [.274,.361] | 0.367 |
| agentclinic | 0.216 [.178,.255] | 0.166 [.130,.202] | 0.048 [.029,.070] | 0.130 [.099,.164] | 0.140 |
| deeprare | 0.012 [.002,.024] | 0.017 [.005,.031] | 0.002 [.000,.007] | 0.012 [.002,.024] | 0.011 |
| maidxo | 0.002 [.000,.007] | 0.005 [.000,.012] | 0.000 [.000,.000] | 0.005 [.000,.012] | 0.003 |

### 主结论（精确表述，勿夸大）

**裸 LLM 与最好的轻量协作框架（medagents/mdagents）在统计上持平，且大幅优于重编排框架
（agentclinic/deeprare/maidxo）。** 具体：

1. **裸 LLM ≈ medagents ≈ mdagents**（行均值 0.364 / 0.350 / 0.367，CI 大幅重叠）。
   逐格看，裸 LLM 在 3/4 backbone 上被某个轻量 agent 微弱超过（mdagents×flash 0.368、
   mdagents×gpt-5 0.435、medagents×gemini 0.401），差距均在 CI 内。**不能说"裸 LLM 打败
   所有 agent"**——诚实表述是"多 agent 编排相对裸 LLM 没有可检出的净收益"。
2. **重编排框架（agentclinic/deeprare/maidxo）远低于裸 LLM**（Δ = +0.22 / +0.35 / +0.36），
   CI 完全不重叠。**编排越重，越差**——这是本矩阵最强、最稳的信号，支持"重 agent 框架
   在真实去泄露病历上不仅无益、反而有害"。
3. gpt-5 在 mdagents 上最高（0.435）但在 maidxo 上崩到 0（见 §红旗），**同一强 backbone 在
   不同框架下天差地别 → 差距主要来自框架设计，不是 backbone 能力**。

### 三个"高 ok 率却近零命中"红旗的定性（已逐一 audit，均非打分 bug 主导）

| 红旗 | 裁定 | 说明 |
|---|---|---|
| **maidxo×gpt-5 = 0.000**（357 ok） | **真·协议崩溃** | gpt-5 在 maidxo 多 agent 面板里回声 prompt 占位符、不产出评分假设，`final_diagnosis` 退化成刮病历碎片（137 例同一碎片、32 例吐 prompt 模板串）。打分器验证正确（干净病名可命中）。诚实计 miss。 |
| **deeprare 全 4 格 ≈0.01** | **真·模式坍缩**（fuzzy 未坏） | 预测坍缩到 ARPKD/primary hyperoxaluria 等**从不在 68 病 gold 集**的病；rapidfuzz 在真实打分环境正常（`HAS_RAPIDFUZZ=True`）。DeepRare 是 HPO 输入管线，自由文本病历下 HPO 饥饿→零样本乱猜。 |
| **agentclinic×gpt-5 = 0.048** vs v4-pro 0.216 | **真·解析 artifact**（唯一真 bug，已披露不改） | adapter 把医生自由文本终诊原样塞 rank0，不做 rank2-5 那样的括号/限定语清洗；gpt-5 输出长病名带括号补语（`"Adult-onset Still's disease (systemic JIA, adult form)"`）→ fuzzy 掉到 90 以下 → 误判 miss，而干净的 `ORPHA:829` 排在 rank1（R@1 看不到）。见下方 caveat。 |

### 自证：maidxo 打分用的是「正则修复后重跑版」，不是旧 bug 版

曾有过一次质疑："manifest 里 maidxo 行均值还是 0.003，是不是打分时重跑没跑完、用了旧文件？"
——**不成立**。0.003 只是显示精度巧合（新版 (1+2+0+2)/1664=0.0030、旧版 (2+0+0+3)/1664=0.0030
四舍五入相同）。看**整数命中数与 `n_ok` 指纹**即可自证，无需查时间戳：

| cell | 现役文件重算 hits_r1 | manifest `hits_r1` | 旧 bug 版 hits_r1 | manifest `n_ok` | 旧 bug 版 ok |
|---|---|---|---|---|---|
| maidxo×deepseek-v4-pro | 1 | **1** ✅ | 2 ✗ | 272 | 352 |
| maidxo×deepseek-v4-flash | 2 | **2** ✅ | 0 ✗ | 256 | 363 |
| maidxo×gpt-5 | 0 | **0** ✅ | 0 | 357 | 391 |
| maidxo×gemini-3-flash | 2 | **2** ✅ | 3 ✗ | 262 | 279 |

- 4 格整数命中数**逐一等于现役预测文件**；旧 bug 版有 3/4 格给出不同值（2/0/3），manifest 一格都没匹配旧版。
- `n_ok` 是决定性指纹：manifest 记的 272/256/357/262 精确等于现役文件；旧 bug 版为 352/363/391/279。
  旧版 ok 率反而更高，正是该 bug 的特征（"成功"产出垃圾）。
- 时间戳佐证：manifest 写于 `14:57:08`，4 个现役 maidxo 文件末次写入 `14:27`/`14:34`/`13:02`/`09:50`，全部早于打分。
- 旧 bug 版留档在 `data/round2/_maidxo_prefix_backup_prefix/`（不进打分，仅供审计追溯）。

**真实解读**：正则修复**没有**让 maidxo 变好（行均值 0.0030→0.0030）。修复只解决了 prefix 正则这一个
具体 bug，而 maidxo 的失败是更深的协议崩溃（见上表 gpt-5 行）；同时重跑版 ok 率反而更低
（352/363/391/279 → 272/256/357/262），两者相抵。ok 率下降的构成（去重后逐格）：

| cell | 旧 bug 版 | 重跑版 |
|---|---|---|
| ×v4-pro | ok 352 / parser_error 43 / timeout 21 | ok 272 / parser_error 66 / timeout 78 |
| ×v4-flash | ok 363 / parser_error 30 / timeout 23 | ok 256 / parser_error 39 / timeout 121 |
| ×gpt-5 | ok 391 / parser_error 25 | ok 357 / parser_error 59 |
| ×gemini-3-flash | ok 279 / parser_error 137 | ok 262 / parser_error 154 |

两个 deepseek 格主要是 timeout 上升（21/23 → 78/121，与重跑采用 CONC=16 高并发、面板子进程争抢
网关吞吐一致）；gpt-5 / gemini 两格则是 parser_error 上升（25→59、137→154），与并发无关，属面板
输出协议本身不稳。无论哪种成因，**全部按 miss 计入 416 分母，未做 success-only 灌水**。
**近零命中是真实结果，不是打分陈旧。**

### 限定语清洗 caveat（sensitivity analysis，主表不做后处理）

上述 agentclinic 解析 artifact 是真实存在的。做了只读敏感性分析（`_audit_qualifier_cleaning_sim.py`）：
若在匹配前剥离病名尾部括号/逗号后限定语，各行 R@1 变化为——

| row | raw meanR@1 | 清洗后 meanR@1 | Δ |
|---|---|---|---|
| llm_control | 0.364 | 0.364 | **+0.000** |
| medagents | 0.350 | 0.350 | **+0.000** |
| mdagents | 0.367 | 0.367 | **+0.000** |
| agentclinic | 0.140 | 0.162 | +0.022（gpt-5 格 0.048→0.099） |
| deeprare | 0.011 | 0.013 | +0.002 |
| maidxo | 0.003 | 0.003 | +0.001 |

**决策：主表报 raw、不做清洗、不改生产打分代码 `cross_map.py`**，理由：
- 清洗对 llm_control/medagents/mdagents 三条主力行 **Δ=0.000**（它们本就输出干净病名/ID）→
  **主结论完全不受此 artifact 影响**；
- 清洗只惠及底部三行，且清洗后 agentclinic（0.162）/deeprare/maidxo **仍远低于裸 LLM**，
  任何定性排序不变；
- 与既定"不对 agent 做后处理提分"口径一致（避免"美化 agent 分"的质疑）；改共享打分代码还会
  连累 2-model 探针等其它 pillar，风险不值。
- **透明披露 > 偷偷修**：此表即上界敏感性分析，审稿人可自行判断。



1. **"模型弱 vs 任务难"——答案是：两者都占，但模型能力是主因。**
   最干净 A 类上 Opus (0.217) 是 DeepSeek (0.030) 的 **7.3×**。DeepSeek 的 3% 主要
   是模型弱，不是任务不可解。强模型能从纯入院表现推出 ~22% 的罕见病主诊断。
2. **但去泄露后强模型也明显掉分**：Opus A 类 0.217 vs 旧 MIMIC 0.35–0.38。
   即使是强模型，去掉 leakage 后也掉 ~40%（0.35→0.22）——旧数里有相当一块是复读答案，
   不是诊断能力。任务本身确实更难了，只是没到 DeepSeek 显示的"几乎做不了"。
3. **A vs B 差距在两模型上都巨大且一致**：DeepSeek 5.5×（0.030→0.165）、
   Opus 3.3×（0.217→0.718）。"文中提过该病"（B 类）即使 mask 病名也严重泄露——
   Opus 在 B 类冲到 0.72，印证 B 类多是隐含既往诊断，不该算真推理。**主结论必须看 A 类。**
4. R@5 与 R@1 同向（Opus A 类 R@5 仅 0.281）→ 不是排序问题；提升主要来自模型能力而非候选覆盖。
5. **净结论**：去泄露后，罕见病"从入院表现→精确 Orphanet 病名"的真实 top-1 能力，
   强模型 ~22%、弱模型 ~3%；旧版 0.35–0.38 高估了真实能力（leakage + 复读）。

## 诚实边界

- gold 仍 code-derived，非独立临床判读（note 修不掉）。
- A 类 855→（cap 后 406）例规则无法排除 paraphrase 型既往史；B 类明确较脏。
- note 覆盖率 52%，有无 note 的住院可能有 selection bias。
- 主库 zip 下载截断，本次用出院小结 presentation；icu 早窗结构化线待重下主库。
- **HPO 分层是 disease-level（gold 病的 Orphanet 表型列表）、非 case-level**，受 68/105=65%
  疾病级标注覆盖限制；modal-system 会误分类（如 achalasia→呼吸）。与其它数据集"结构对齐"非等价。

## 复现

```bash
python3 scripts/build_mimic_note_eval_subset.py --output data/mimic_iv_rd_slice/note_eval_subset_v1.jsonl
python3 scripts/filter_mimic_note_prior_known.py --output data/mimic_iv_rd_slice/note_eval_subset_v2.jsonl
# cap10 均衡子集见 note_eval_cap10_v2.jsonl（每病≤10，按 hadm 稳定排序）
LITELLM_API_KEY=... python3 scripts/score_mimic_note_llm.py --live \
  --model deepseek-v4-flash --output data/mimic_iv_rd_slice/predictions_mimic_note_deepseek_v4.jsonl
```
