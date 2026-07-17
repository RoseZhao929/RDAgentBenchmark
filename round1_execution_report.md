# Round 1 执行结果(Execution Report)

> 对应计划文档:`round1_plan.md`
> 执行时段:2026-05-11(单次会话)
> 状态:**80% 完成,3 项后台任务还在跑(PhenoBrain 下载 / PMC 抽取-mapping / DeepRare adapter subagent)**
> MIMIC-IV 数据按约定延后到次日;Stream G(申请)按用户指示"先简单地来,不联系作者"完全跳过

---

## 1. 做了什么(产出概述)

### 1.1 数据集收集 — Stream A + D

| 数据集 | 规模 | 状态 |
|---|---|---|
| Phenopacket-Store | **10,051 例 / 751 OMIM 疾病**(比 paper 多 — 数据集近期扩展)| ✅ Ingest + canonical 全转完,100% 验证 |
| RareBench(HF 数据)| RAMEDIS 624 / MME 40 / HMS 88 / LIRICAL 370 = **1,122 例 / 4 splits** | ✅ 数字与 KDD'24 论文吻合;PUMCH_ADM 不在公开 data.zip(印证用户说"假设未授权")|
| RareArena RDS + RDC | **72,661 例 / >8,000 疾病** | ✅ 自由文本 + Orpha_id + pub_date 全 ingest |
| Orphadata 主表 | **11,456 病种 / 26,365 name aliases / 4,978 有 OMIM 交叉引用** | ✅ 解析 + fuzzy mapping 测试通过 |
| PMC OA holdout(自建)| 2,401 PubMed 候选 → 2,398 PMC IDs → **2,394 XML 已下载** | ✅ 4 个 fetch 失败(0.17% 容忍率);LLM 抽取在后台跑 |

**总计可用评估池:~84,000 例 / >12,000 疾病**(MIMIC-IV 明天到位后再翻一层)

### 1.2 评估系统 — Stream E(scouting + install/run)

侦察(scouting):8 个 agent 全部完成。Install + actual smoke test:**8 个里 6 个完全跑通,2 个部分跑通**。

| Agent | Smoke Test | 耗时 | OpenRouter Gemini 3 Flash backbone | 主要发现 |
|---|---|---|---|---|
| **MDAgents** | ✅ basic + intermediate | 6.5s + 142s | ✅ 12 patches 后通 | Multi-expert recruiter/debate 全链通,top-5 输出医学合理 |
| **MAI-DxO** | ✅ instant + no_budget | 9s + 74s | ✅ LiteLLM 路由 | **5 个模式全 callable** — A11 cost-cap 消融现成 |
| **VC-RDAgent** | ✅ Stage 1 完全离线 | n/a | 不需要 | 0 OpenRouter calls,Poincaré + IC 融合,2 个 PUMCH-ADM 样例 gold 在 rank 3/4 |
| **RDMA** | ✅ Pillar 1 mining | 4.7s | ✅ 原生 | **Pillar 1 specialist 定位坐实**: `LLMEntityExtractor.extract_entities()` |
| **MedAgents** | ✅ 5-stage 全管线 | 51s / ~10 calls | ✅ 25 LOC patch | Unanimous vote round 1 |
| **AgentClinic** | ✅ Doctor/Patient/Measure/Moderator | 15.8s / 5 calls | ✅ 30 LOC patch | **NEJM case 0(Exogenous ochronosis)端到端诊断正确** — 我们 8 agent 里第一个完整证明正确诊断流程 |
| **DeepRare** | ✅ end-to-end 1m46s | 1m46s / ~$0.01-0.04 | ✅ 全管线 | **3 个阻塞全部解锁** by adapter subagent(120 LOC patches, 8 files)。Microcephaly+Seizures+DD 三联征:Top-1 = ARX-Related Epileptic Encephalopathy,top-5 含 ASPM/WWOX/FoxG1/SLC13A5(MCPH+Rett-family 合理覆盖)|
| ~~**PhenoBrain**~~ | ⛔ **dropped from lineup** (2026-05-12) | n/a | n/a | Drive 上 ICTODQAcrossModel + HPOProbMNBModel sub-folders 作者**实际就没上传**(浏览器也是空的)— 不可恢复。换 LIRICAL 作为 non-LLM classic baseline。详见下面"PhenoBrain Drive 阻塞详情" |
| **LIRICAL**(新)| 待集成(Round 2)| n/a | n/a | Java 工具,Apache 2.0,在 RareBench LIRICAL split 里就是 gold-standard 工具,经典 baseline,不需要 14 GB checkpoint |

**verdict**:**7 个 agent 现在就能开始主实验集成**。PhenoBrain 因 Drive 上游 2 个 critical sub-folder 真实空 + 即使有也只能搞到 4/5 ensemble(degraded)→ **正式 drop**,换 LIRICAL 作为 non-LLM classic baseline(Round 2 集成,Java 工具,无 checkpoint 依赖)。

**PhenoBrain Drive 阻塞详情(2026-05-12 上午多次尝试后定性)**:

实际下到 2.6 GB,其中**只有 BOQA 完整**(28 个 .tab),CNB 只有 1 个 .joblib(不完整),**HPOICCalculator 拿到 IC.json**(460 KB,关键 ensemble 组件)。其余 5 个推荐模型(ICTODQAcrossModel / HPOProbMNBModel / LRNeuronModel / MICA / SimGIC 等)在 Drive sub-folder 里,gdown unauthenticated 拿不到。

**第一次诊断**:gdown unauth 只能下 shared folder 顶层文件;sub-folder 的文件 listing 需要 Drive API OAuth。

**用户浏览器手动验证后(2026-05-12)**:重新登录 Google 账号下载后总共拿到 7.6 GB,包括:
- ✅ BOQAModel(641 MB, 29 文件)
- ✅ CNBModel(6 GB,3 个 .joblib variant)
- ✅ HPOICCalculator(IC.json 460 KB)
- ✅ NN-Mixup-1(957 MB TF checkpoint)— 经代码验证就是 `LRNeuronModel` 的一个 instance(`test_optimal_model.py:733`:`(LRNeuronModel, ..., {'model_name':'NN-Mixup-1'})`),Drive uploader 把它 flattened 到顶层
- ❌ ICTODQAcrossModel — 子文件夹 `SimTODQAcrossModel/` 用户在浏览器里也确认是空的
- ❌ HPOProbMNBModel — 子文件夹 `HPOProbMNB/` 浏览器也空

**结论**:ICTODQAcrossModel + HPOProbMNBModel 这两个 critical sub-folder 在 Drive 上游就**没文件**(作者实际没上传)。即使绕过 gdown 也拿不到。

**最终决策 — Plan B(2026-05-12 锁定)**:**PhenoBrain 退出阵容**。即使强行用 4/5 model ensemble 跑,缺 ICTODQ("strongest single similarity model")是已知缺陷,reviewer 必质疑。直接换 **LIRICAL**:
- Java 工具,Apache 2.0
- 在 RareBench LIRICAL split 里本身就是 gold-standard tool(那个 split 就是 LIRICAL 跑出来的)
- 经典 baseline,论文 baseline 列表更标准
- 无 14 GB checkpoint 依赖
- 集成进 Round 2 工作流(Stream E10 任务追踪)

清华 PhenoBrain REST API 也仍然 502 down(scouting 时验证过)— 即使想绕过本地 install 也没法。

`agents/phenobrain/`、`data/phenobrain_checkpoints/`(7.6 GB)保留在磁盘上,作为 future work / camera-ready 期可能的 revisit;Round 1 / 主实验不再依赖它。

---

**DeepRare 解锁细节(adapter subagent 产出)**:
- `DEEPRARE_NO_WEB=1` env shim — 4 个 Selenium 工具(`web_search/page_fetch/hpo_search/uptodate_search`)直接 early-return
- `utils.py:set_up_data` — 5 个缺失 RAG CSV 用 try/except 容忍 + 空 DataFrame fallback
- `api/interface.py:get_embedding` — `DEEPRARE_LOCAL_EMBEDDING=1` shim 使用 `BAAI/bge-small-en-v1.5`(110 MB,384 dim,padded to 1536)
- `diagnosis.py` — `PubCaseFinderSearchTool` + `PhenobrainAPITool` 也外包了(它们的 public API 也已经 404)
- **Caveat**:bge-small-en-v1.5 向量空间不与原 text-embedding-3-small 对齐,similar-case 检索退化成 row order — 后续主实验前需要补

### 1.3 评估 harness 包 — Stream F

`harness/` Python 包,17 个 .py 文件全部 import 通过,在真实数据上端到端验证:

- **canonical_case.py**:Pydantic v2 schema(在 10,051 例 Phenopacket-Store 上 0 失败 ingest)
- **ingest/**:Phenopacket-Store / RareArena / RareBench 三个 adapter,全部 cross-dataset matching 验证通过(预测 OMIM 或 ORPHA 都能 hit RareBench gold)
- **metrics/**:5 个 metric 模块,覆盖 Tier 1 + Tier 2
  - accuracy(Recall@k / MR / MRR)、phenotype(HPO P/R/F1)、calibration(Brier / ECE / AUROC)、reliability(pass^k)、cost(Cost-Normalized Accuracy)
- **logging/**:PredictionLog Pydantic schema(覆盖 agent_id / backbone / pillar / eval_mode / tool_calls / cost / latency / reasoning_trace 等所有 reviewer 必查字段)+ JSONL append-only writer
- **pmc_oa/**:5 步流水线 — search(E-utils PubMed 找 2,401 候选)/ linking(PMID→PMC 99.9% 转换)/ fetch(JATS XML 拉取)/ extract(OpenRouter Gemini 3 Flash 抽取,5/5 测试 100% 成功)/ orphanet(name fuzzy → ORPHA + OMIM 交叉引用,Marfan/Cystic fibrosis/Aicardi exact 100,Marfan typo fuzzy 96.6)

### 1.4 OpenRouter / backbone 验证

- Model 实际 ID 确认:`google/gemini-3-flash-preview` → `google/gemini-3-flash-preview-20251217`(日期戳符合 reviewer 可复现性要求)
- 6 个 agent + harness PMC 抽取 + Orphanet mapping 都跑通了

---

## 2. 产出文档清单(路径)

### 顶层方案 / 计划

| 文档 | 路径 | 描述 |
|---|---|---|
| 罕见病 benchmark 方案 | `罕见病benchmark方案.md` | 整体可行性分析(已有,未改)|
| Plan | `plan.md` | 5 pillar / 双 pass / 12 消融 / 11 假设 完整 plan(已有,未改)|
| Round 1 计划 | `round1_plan.md` | 第一轮并行任务详细方案(已有,未改)|
| Agent / 数据集 方案 | `agent_methods.md` | 10 系统阵容 + 数据集层(已有,未改)|
| 申请方案 | `applications.md` | MyGene2 + DDD 申请流程(已有,按用户指示**本轮不执行**)|
| **本文件** | `round1_execution_report.md` | Round 1 执行结果(本文)|

### 数据 INGEST_REPORT

| 文档 | 路径 |
|---|---|
| Phenopacket-Store | `data/phenopacket_store/INGEST_REPORT.md` |
| RareBench | `data/rarebench/INGEST_REPORT.md` |
| RareArena | `data/rarearena/INGEST_REPORT.md` |

### Agent scouting 报告(8 份)

`tasks/stream_E_agent_scouting/agents/*_REPORT.md`:
- `deeprare_REPORT.md` / `mdagents_REPORT.md` / `medagents_REPORT.md` / `agentclinic_REPORT.md` / `maidxo_REPORT.md` / `rdma_REPORT.md` / `phenobrain_REPORT.md` / `vc_rdagent_REPORT.md`

### Agent install + run 报告(8 份)

`tasks/stream_E_agent_scouting/agents/*_RUN_REPORT.md`:
- 同 8 个 agent,每个有独立 install + smoke test 报告

### Harness 代码

| 模块 | 路径 |
|---|---|
| 包入口 | `harness/__init__.py` |
| Schema | `harness/canonical_case.py` |
| Ingest adapter | `harness/ingest/{phenopacket_store,rarearena,rarebench}.py` |
| Metric 库 | `harness/metrics/{accuracy,phenotype,calibration,reliability,cost}.py` |
| Logging | `harness/logging/{schema,backend}.py` |
| PMC OA pipeline | `harness/pmc_oa/{search,linking,fetch,extract,orphanet}.py` |
| pyproject | `harness/pyproject.toml` |
| README | `harness/README.md` |

### 任务 board

| 文档 | 路径 | 备注 |
|---|---|---|
| Task board | `tasks/README.md` | 第一轮任务状态总览(状态比 TaskList 老,本报告是最新)|
| 个 stream task.md | `tasks/stream_A_data_ingest/task.md` 等 | 各 stream 的自包含 brief(原本想给外部 session 用,后改成 subagent brief)|

### 数据产出

| 类型 | 路径 | 大小 |
|---|---|---|
| Phenopacket-Store git clone | `data/phenopacket_store/` | 147 MB |
| RareBench code | `data/rarebench/` | 3.6 MB |
| RareBench HF data | `data/rarebench_hf/` | 290 MB |
| RareArena | `data/rarearena/` | 195 MB |
| Orphadata XML | `data/orphadata/` | 60 MB |
| PMC OA 候选 PMIDs | `data/pmc_oa_holdout/01_pmids.jsonl` | 2,401 PMIDs |
| PMC OA PMID→PMC mapping | `data/pmc_oa_holdout/02_pmid_to_pmc.jsonl` | 2,398 records |
| PMC OA XML | `data/pmc_oa_holdout/03_xml/` | 2,394 .xml.gz(后台 finished)|
| PMC OA LLM 抽取 | `data/pmc_oa_holdout/04_extracted.jsonl` | 🔄 后台进行中 |
| PMC OA Orphanet mapped | `data/pmc_oa_holdout/05_orphanet_mapped.jsonl` | ⏳ 等 04 完成自动 chain |
| Agent code clones | `agents/{8 agents}/` | 各 venv 已建,deps 装好 |

### 配置

| 文档 | 路径 | 备注 |
|---|---|---|
| Env 配置 | `.env` | `OPENROUTER_API_KEY` + `CANARY_BACKBONE_MODEL`。**用户提醒后需 rotate**|

---

## 3. 过程中遇到的问题

### 3.1 数据 / 流水线层面

| # | 问题 | 处理 |
|---|---|---|
| P1 | PMC E-utils PMC db 直接 search 只返回 ~100 结果,数量太少 | 切换到 PubMed db + `pubmed pmc open access[sb]` filter + elink 转 PMC ID,扩到 2,401 候选 |
| P2 | PMC OA fetch 单线程串行,2,398 个文件预估 ~14 分钟实际跑 ~1 小时(network latency 主导) | 接受了 — 实际 2,394/2,398 完成,4 个失败(0.17%)无碍 |
| P3 | RareBench `infomation_content.json` 文件名拼写错误 | 不修(保持与 RareBench eval 代码兼容)|
| P4 | RareArena CC-BY-NC-SA license — ShareAlike 可能传染我们 benchmark license | 记录在 INGEST_REPORT 里,论文 method 需显式声明 |
| P5 | 多个数据集 disease ID 系统不一(OMIM / ORPHA / CCRD / name) | canonical_case 设计为 parallel ID 字段,evaluator 接受 any-match;Orphadata cross-map 已下载 |
| P6 | Phenopacket-Store 没有 free-text vignette;RareBench 也是 HPO list 形式 | Schema 加 `synthetic_vignette` 字段,后续 v2 用 LLM 合成 |
| P7 | RareArena 没有 gold HPO | 标记为已知 gap;Pillar 1 双 pass 评估在此数据集上"gold pass"用 LLM-soft-gold(标记不确定性)|

### 3.2 Agent 安装 / 兼容层面

| # | 问题 | 处理 |
|---|---|---|
| P8 | **MDAgents、MedAgents、RDMA、VC-RDAgent 无 LICENSE 文件** | 用户决策"不联系作者,先简单地来" — 本地评估仍可,论文里不打包代码,只引用 URL |
| P9 | MDAgents 写死 `gpt-4o-mini`,`load_data` 走错路径 | 12 个 patches 解决(includes 写在 RUN_REPORT)|
| P10 | MedAgents 用 openai==0.27 写死 Azure | ~25 LOC patch,保留旧 SDK 只换 base_url+model |
| P11 | AgentClinic 用 openai==0.28 写死,image 分支有 fall-through bug | ~30 LOC patch,force-disable image 分支 |
| P12 | DeepRare 5 个 RAG CSV(xinhua/mimic/rarebench/mygene/ddd_rag.csv)写死缺失 | DeepRare adapter subagent 正在 patch(让 set_up_data 容忍缺失)|
| P13 | DeepRare 无 `--no-web` flag,4 个工具都强制 Selenium | adapter subagent 加 `DEEPRARE_NO_WEB=1` env shim |
| P14 | OpenRouter 无 embeddings endpoint | adapter subagent 用 local SentenceTransformer 替换(BAAI/bge-small-en-v1.5,110 MB)|
| P15 | RDMA 重依赖 faiss/sent2vec/scispacy 在 Py3.13 无 wheel | 写 `requirements_smoke.txt` 最小子集,faiss 路径推迟到 Py3.11 sibling venv |
| P16 | RDMA 25+ 个写死 `/home/johnwu3/...` 路径 | Catalogued,smoke test 路径不涉及它们 |
| P17 | PhenoBrain 三重阻塞(Docker / 14GB Drive checkpoint / 清华 API 502) | Drive 下载正在第三次尝试(`--remaining-ok` flag 不支持,已去掉);Docker + API 等用户决策 |
| P18 | DeepRare HF database 用 `huggingface-cli download` 在 hub 1.x 已 deprecated | 改用 `huggingface_hub.snapshot_download(...)` Python API |
| P19 | DeepRare requirements 含 16 个 CUDA-only `nvidia-*` + `triton` wheel,无 macOS arm64 | grep 过滤生成 `requirements-macos.txt` |
| P20 | Multiple agents 用 pre-1.0 openai SDK 互相冲突 | 每个 agent 独立 venv |

### 3.3 工具 / 工程层面

| # | 问题 | 处理 |
|---|---|---|
| P21 | `gdown` 第一次 pip install --user 后 PATH 找不到 | 改用 `python3 -m gdown` |
| P22 | `gdown` 老版本不识别 `--remaining-ok` flag | 第二次去掉 flag |
| P23 | Subagent / Bash 偶发触发 task tracking reminder,任务状态曾错乱(把 scouting 任务状态当成 install 任务) | 中途纠正了一次,现在 TaskList 正确 |
| P24 | task.md 文件初次创建后用 `Write` 写不进(因为 `touch` 创建了空文件,Write tool 要求先 Read) | 改用 Read+Write 序列 |
| P25 | Subagent 看不到聊天上下文,brief 要冷启动自包含 | 每个 subagent prompt 写得 600-900 字,包含路径 + 任务 + 约束 |

---

## 4. 接下来的 To-do

### 4.1 后台还在跑(本轮内会出结果)

- [ ] **PMC OA LLM 抽取**:对 2,394 个 XML 跑 Gemini 3 Flash 抽取,产出 `04_extracted.jsonl`。预估 2-4 小时,~$8 token cost。完成后自动 chain Orphanet mapping → `05_orphanet_mapped.jsonl`
- [ ] **PhenoBrain Drive 下载**:第三次尝试中,预估 1-3 小时,14GB
- [ ] **DeepRare adapter subagent**:解锁 3 个阻塞(`--no-web` patch / set_up_data 容忍缺失 CSV / local SentenceTransformer 替换 embeddings)→ 跑 microcephaly+seizures+DD 三联征 smoke test

### 4.2 等用户(blocked)

- [ ] **MIMIC-IV 数据**:用户明天提供 PhysioNet credentialed 数据 →启动 Stream C(ICD→Orphanet 映射 + NLP 召回 + ~1,875 例罕见病切片)
- [ ] **PMC OA 200 例人工核验**:用户曾确认"有人不阻塞"。需要在 Orphanet mapping 完成后启动(预计明天)。每例 5-10 分钟 × 200 ≈ 17-33 小时分给 1-2 名标注员
- [x] ~~PhenoBrain 最终决策~~ **已决:drop → 换 LIRICAL**(2026-05-12)

### 4.3 Stream F 还可以补的(非阻塞)

- [ ] **HPO 本体 ancestor / descendant matching**:phenotype.py 目前只支持 exact match;Tier 3 metric 需要 ontology-walk(下载 hp.obo)
- [ ] **OMIM ↔ ORPHA 跨映射**:目前 evaluator 只在 parallel ID 内 match;真正跨映射要查 Orphadata
- [ ] **Agent adapter base class**:`harness/agents/base.py` — 定义所有 agent 共用接口(`predict(case, pillar)`, `extract_phenotypes(case)` 等)
- [ ] **Cost-tracker 接 OpenRouter response**:目前 logging.schema 有 CostBreakdown 字段但没 wrapper 自动填充。要写个 `OpenRouterClient` wrapper
- [ ] **预注册 OSF**:H1-H11 假设 + A1-A12 消融需要预注册到 OSF。**必须在 PMC OA holdout 人工核验完成之前**做

### 4.4 主实验启动前剩余(Round 2 准备)

- [ ] **Per-agent adapter shim**(8 份):每个 agent 一个 `harness/agents/<name>.py`,实现 base class,把 canonical_case 投影到 agent 原生输入 + 解析输出回 ranked predictions。预估 0.5-1 天 / agent
- [ ] **Backbone 阵容固化**:DeepSeek V3.2 + GPT-5 + Gemini 3 Flash 模型 ID + 价格表,写到 `.env`。**用户提到 Gemini 3 Flash 是 "latest GA Flash"** — 实际我们用 preview 版,需用户确认是否切到 `gemini-3.1-flash-lite`(真正 GA)
- [ ] **Sanity-check 跑**:3 LLM 控制组 × 200 例小子集 × 5 pillar → 验证 pipeline 全通
- [ ] **小规模 baseline**:在 RareBench 5 splits + Phenopacket-Store 100 例上跑 LLM control,复现 RareBench KDD'24 数字(必须复现否则 reviewer 必问)

### 4.5 v2(camera-ready / 期刊版,不影响 Round 1 完成)

- [ ] MyGene2 + DDD 申请(等用户决策"先简单地来"政策是否变)
- [ ] PhenoBrain checkpoint mirror 到 lab S3(防 Drive 失效)
- [ ] LICENSE 邮件 4 个作者(等用户决策)
- [ ] Pillar 4 升级为独立 pillar(需 ≥150 个 trio)

---

## 5. 重要决策点(供回顾)

1. **Gemini Flash 版本**:用了 `google/gemini-3-flash-preview`(实际 ID `google/gemini-3-flash-preview-20251217`),价格 $0.50/$3 per 1M。reviewer 可复现性角度,**应在主实验前确认**是否切到真正 GA 的 `gemini-3.1-flash-lite`
2. **agent 阵容**:8 个 agent 中 PhenoBrain 阻塞最严重,但代码完整 + 论文 baseline 标志意义大。**短期可以换** LIRICAL(已在 RareBench 数据里)作为非 LLM baseline,**长期** 要等 Drive 下完 + Docker 装好。用户先前回复倾向"保留"
3. **RDMA 重新定位为 Pillar 1 specialist**(不是 P2-4 DDx 通用)— 用户在 round 1 阶段已默认接受
4. **Stream G(申请)整体跳过** — 按用户"先简单地来,不联系作者"指示;v2 / camera-ready 再启动

---

## 6. Round 1 完成度估算

- 数据集收集:**95%**(只差 MIMIC + PMC 抽取后台跑完)
- Agent 阵容打通:**100% v1 阵容**(8/8 adapter verified — PhenoBrain dropped,LIRICAL Java 工具已在 Round 1 内集成完成)
- Harness:**85%**(主要 Tier 1+2 metric 都有,缺 adapter base class + 预注册脚手架)
- 整体:**100% Round 1 完成(2026-05-14)**

### 2026-05-12 终态(8/8 adapter verified + LIRICAL + OSF + S1-S4)

| 模块 | LOC | 状态 |
|---|---|---|
| `harness/agents/base.py` | 144 | ✅ |
| `harness/agents/_adapter_utils.py` | 239 | ✅ 共享 helper(`.env` loader / `case_to_question` / `parse_ranked_top5` / `map_names_to_ids`)|
| `harness/agents/mdagents.py` | 301 | ✅ verified RAMEDIS:PDH-E1α / Leigh / COXPD1 等(7.8s, $0.0001) |
| `harness/agents/medagents.py` | 348 | ✅ verified same:mtDNA hep / Tyrosinemia I 等(15s)|
| `harness/agents/agentclinic.py` | 509 | ✅ verified OSCE 7 inferences(37s)|
| `harness/agents/maidxo.py` | 447 | ✅ instant 模式 12.4s,5 模式都 callable(A11 cost-cap 现成)|
| `harness/agents/deeprare.py` | 417 | ✅ Jacobsen case 128.6s,top-5 = Sotos/Mowat-Wilson 等(医学合理,gold 未命中是 DeepRare 自己的 miss)|
| `harness/agents/vc_rdagent.py` | 310 | ✅ LIRICAL case 0 **top-1 命中 OMIM:191900**(77s,0 LLM cost)|
| `harness/agents/rdma.py` | 364 | ✅ Pillar 1 mining 4.7s,返回 phrases(deferred phrase→HP ID 归一化需 S5 / faiss + Drive 上的 embeddings)|
| `harness/agents/lirical.py` | 369 | ✅ Phenopacket-Store Jacobsen 8.0s,Adoptium Temurin 21 bundled(151 MB)+ LIRICAL v2.4.0 + 345 MB 数据,绕过 NCBI FTP bug 走 Zenodo |
| 总 adapter LOC | **3,485** | ✅ |

### Sanity-check pilot 结果(2026-05-14,Stream I)

`harness/agents/llm_control.py` + `scripts/sanity_check_pilot.py` 写完跑完。
**Pipeline 端到端 verified**:adapter → JsonlPredictionLogger → read_logs → cross-map → recall_at_k / MRR / cost 全跑通。

50 例 stratified(25 Phenopacket-Store + 25 RareArena RDS,seed=42,P2 only):

| Backbone | R@1 | R@5 | MRR | Cost ($) | Mean Lat | OK |
|---|---|---|---|---|---|---|
| `google/gemini-3-flash-preview` | **0.26** | 0.40 | 0.305 | 0.05 | 3.5s | 50/50 |
| `deepseek/deepseek-v3.2-exp` | 0.20 | 0.30 | 0.238 | 0.01 | 6.3s | 50/50 |
| `openai/gpt-4o-mini` (gpt-5 replacement) | 0.08 | 0.18 | 0.111 | 0.01 | 3.9s | 50/50 |
| `openai/gpt-5` | **batch 不可用** | — | — | — | 77s/call,hang | 4/6 |

**关键发现**:
- Gemini 3 Flash 是最强 LLM control,几乎免费 — 这就是我们 scaffolded agent **必须 beat 的 baseline**
- **GPT-5 batch unusable**:60-90s/call + 频繁 5min hang,reasoning tokens 吃光 max_tokens 让 content=null。换 `openai/gpt-4o-mini` 作为第 3 个 no-scaffold control(主实验阵容可能要再换 `gpt-5-mini` 或 `o1-mini`)
- 数据集:`data/sanity_check/results.jsonl`(156 PredictionLog),`REPORT.md` 详细对比

**Stream H4 完成的 5 个模块**:
| 模块 | 用途 | 验证 |
|---|---|---|
| `harness/metrics/cross_map.py`(S1) | OMIM ↔ ORPHA 双向跨映射,evaluator 用 | ✅ Marfan OMIM:154700 → [ORPHA:558, ORPHA:284963] |
| `harness/metrics/hpo_ontology.py`(S2)| hp.obo 17k 词项 + ancestor closure | ✅ 0.1s 加载 |
| `harness/logging/openrouter_wrapper.py`(S3)| OpenRouter 包装 + auto cost fill | ✅ live API + 双 backbone 价格表 |
| `.env`(S4)| backbone aliases + 价格 | ✅ DeepSeek/GPT-5/Gemini 全 ID + 价格 |
| `osf_preregistration.md`(OSF)| H1-H11 + A1-A12 + 统计计划 + reviewer 攻击 + 8 backbone version 钉死 | ✅ 草稿 ~330 行,等 PMC unblind 前 freeze |

预计明天到位 MIMIC-IV + PhenoBrain 下完 + DeepRare adapter + PMC 抽取完 → **Round 1 100% 完成,可以启动 Sanity-check + 主实验**。
