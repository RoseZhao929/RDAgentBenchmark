# Stream A — 三大开源数据集 ingest

## 项目上下文(冷启动必读)

这是一个**罕见病 Agent Benchmark**项目,目标投 EMNLP。Benchmark 评估 10 个 agent 系统在 5 个能力 pillar(表型抽取、仅表型 DDx、基因型感知、Family-aware、临床沟通)上的性能,数据集分四层。

完整方案见项目根目录:
- `round1_plan.md`(第一轮细节方案)
- `agent_methods.md`(数据集 + agent 阵容详情)
- `plan.md`(执行 plan)

本任务负责四层数据集中**最容易拿的三个**:Phenopacket-Store、RareBench、RareArena 全部开源,直接下载即可。

---

## Goal

把三个公开数据集的全量数据拉到本地 `data/` 目录,统一组织,**输出每个数据集的字段 schema 清单**(给 Stream B 设计 canonical case object 用)。

## 不要做的事

- ❌ **不要**自己设计 canonical case schema — 那是 Stream B 的工作。本任务只是把原始数据搬下来 + 摸清字段长什么样
- ❌ **不要**做任何模型推理 / agent 评估 — 那是后续阶段
- ❌ **不要**改文件名 / 重新打包 — 保持每个数据集的原始目录结构,只在外面加一层 README 描述

## Deliverables

```
/Users/yutianzhao/Desktop/RDAgentBenchmark/data/
├── phenopacket_store/
│   ├── <原始目录结构>
│   └── INGEST_REPORT.md     ← 你写的:版本号、文件数、字段清单、样例 case
├── rarebench/
│   ├── ramedis/
│   ├── mme/
│   ├── hms/
│   ├── lirical/
│   ├── pumch_adm/           ← 如果公开版只有部分,也下下来
│   └── INGEST_REPORT.md
└── rarearena/
    ├── rds/
    ├── rdc/
    └── INGEST_REPORT.md
```

每份 `INGEST_REPORT.md` 必须包含:
1. **来源 URL** 和 **commit hash / version**(可复现性)
2. **License**(Phenopacket-Store: CC-BY;RareBench: Apache 2.0;RareArena: CC-BY-NC-SA)
3. **文件数 / 病例数 / 疾病数**(对照 `agent_methods.md` 第一/三层表里的预期数字)
4. **字段 schema 清单**:每个文件类型的字段名、类型、是否必填、样例值。**重点**:HPO 词项怎么存(列表/字符串/嵌套?),疾病 label 怎么存(OMIM ID / Orphanet ID / 文本名?),VCF 路径 / 家族信息字段是否存在
5. **一个完整 case 样例**(JSON 或截图,展示典型 record 长什么样)
6. **任何坑 / 异常**:文件损坏、字段缺失、编码问题、size 异常等

## 来源参考

- **Phenopacket-Store**:`https://github.com/monarch-initiative/phenopacket-store`(Danis et al., HGG Adv 2025)
  - 直接 `git clone` 或下载 release tarball
  - 文件格式:GA4GH Phenopackets(.json)
- **RareBench**:`https://huggingface.co/datasets/chenxz/RareBench`(Chen et al., KDD 2024)
  - HuggingFace Datasets 或 GitHub
  - 5 个子集合包:RAMEDIS / MME / HMS / LIRICAL / PUMCH-ADM
  - 注意:PUMCH-ADM 可能需要额外申请;先看公开版有多少
- **RareArena**:`https://github.com/zhao-zy15/RareArena`(Zhao et al., Lancet Digit Health 2025)
  - RDS 子集(49,760 例)+ RDC 子集(22,901 例)
  - **License CC-BY-NC-SA**:商业用途禁止,论文里要显式 acknowledge

## Acceptance Criteria

- [ ] 三个数据集本地完整可用,文件计数与公开数字吻合(允许 ±5% 出入,大幅偏差要在 INGEST_REPORT.md 标记)
- [ ] 每个 INGEST_REPORT.md 含上面 6 项必填内容
- [ ] 占用磁盘空间记录在 progress.md(`du -sh data/*`)
- [ ] 至少 1 个 case 样例从每个数据集成功 parse 为 Python dict(写在 INGEST_REPORT.md 里)

## 工具与环境

- 用 `git`、`wget`、`curl`、`huggingface_hub` 之类
- Python 环境:可以新建 `data/.venv`,装 `huggingface_hub`、`requests`、`tqdm`、`pydantic`
- **不需要任何 LLM API**

## 进度记录

把进展写到本目录的 `progress.md`,格式见 `tasks/README.md` 的"多 session 协作协议"。

## 完成后的下游

- Stream B 会读你的 INGEST_REPORT.md 来设计 canonical case schema
- Stream F harness 会写 ingest adapter 把这些数据转成 canonical_case.json
- 主实验 Step 2 会从 canonical_case.json 喂给 agent
