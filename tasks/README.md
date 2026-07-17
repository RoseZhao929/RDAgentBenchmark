# 第一轮并行任务总览(Task Board)

> 项目:罕见病 Agent Benchmark(EMNLP 投稿)
> 项目根目录:`/Users/yutianzhao/Desktop/RDAgentBenchmark/`
> 总体方案见根目录 `round1_plan.md`、`plan.md`、`agent_methods.md`、`罕见病benchmark方案.md`
>
> **本目录的作用**:把 round1_plan.md §1 的 7 条并行 stream 拆成自包含 task,供多个 Claude session(或 subagent)并行执行。

---

## 任务清单(7 个主 stream + Stream E 的 10 个子任务)

| Stream | 任务 | 状态 | 阻塞 | 预估耗时 | 路径 |
|---|---|---|---|---|---|
| A | 三大开源数据集 ingest | pending | — | 1-2 天 | `stream_A_data_ingest/task.md` |
| B | Canonical case schema 设计 | pending | A 部分完成 | 2-3 天 | `stream_B_canonical_schema/task.md` |
| C | MIMIC-IV 罕见病切片构建 | pending | 等用户下载 MIMIC | 1 周 | `stream_C_mimic_pipeline/task.md` |
| D | PMC OA cutoff 后 holdout 流水线 | pending | — | 1 周(代码)+ 2 周(人工核验) | `stream_D_pmc_holdout/task.md` |
| E | 10 个 agent 代码可用性侦察 | pending | — | 5-7 天(并行) | `stream_E_agent_scouting/task.md` |
| F | 评估 harness(metric + 日志) | pending | — | 1 周 | `stream_F_harness/task.md` |
| G | MyGene2 + DDD 申请 | pending | 人(申请负责人) | 1 周提交 + 2-6 周审批 | `stream_G_applications/task.md` |

### Stream E 内部子任务

| Sub-task | 难度估计 | 状态 | 路径 |
|---|---|---|---|
| 3 个 LLM 控制组 smoke test(DeepSeek V3.2 / GPT-5 / Gemini 3 Flash via OpenRouter) | 低 | pending | `stream_E_agent_scouting/agents/llm_controls.md` |
| DeepRare canary | 中 | pending | `stream_E_agent_scouting/agents/deeprare.md` |
| MDAgents canary | 低 | pending | `stream_E_agent_scouting/agents/mdagents.md` |
| MedAgents canary | 低 | pending | `stream_E_agent_scouting/agents/medagents.md` |
| AgentClinic canary | 低 | pending | `stream_E_agent_scouting/agents/agentclinic.md` |
| MAI-DxO(社区版)canary | 中 | pending | `stream_E_agent_scouting/agents/maidxo.md` |
| RareAgents canary | 高(可能拿不到代码) | pending | `stream_E_agent_scouting/agents/rareagents.md` |
| PhenoBrain canary | 中-高 | pending | `stream_E_agent_scouting/agents/phenobrain.md` |
| RDMA canary | 中 | pending | `stream_E_agent_scouting/agents/rdma.md` |
| VC-RDAgent canary | 中 | pending | `stream_E_agent_scouting/agents/vc_rdagent.md` |

---

## 多 session 协作协议

每个 session(或 subagent)拿任务的流程:

1. **认领**:在 `tasks/README.md`(本文)对应行的"状态"列改为 `in_progress (session-id 或简称)`,如 `in_progress (deeprare-session)`
2. **执行**:严格按 `task.md` 的 Goal / Deliverables / Acceptance criteria 来做,**不要扩大范围**
3. **记录**:在该 stream 目录下的 `progress.md` 末尾追加一段:
   ```
   ## YYYY-MM-DD HH:MM — session-id
   - 做了 X
   - 卡在 Y
   - 下一步 Z
   ```
   **追加式,不覆盖之前的记录**
4. **完成**:更新本 README 状态为 `done`,在 `progress.md` 写最终一段总结(产出文件清单 + 已知坑 + 下游可以怎么用)
5. **遇到设计决策点**:不要自己拍板。在 `progress.md` 写明问题、列 2-3 个选项,标 `🛑 需要主线决策`,然后停下来等主 session 协调

## 共享约定

- **API key**:从根目录 `.env` 读取(`OPENROUTER_API_KEY`)。**绝对不要**把 key 写进代码、commit message、log 文件、聊天回复
- **数据路径**:所有数据落到 `data/<dataset_name>/` 下
- **代码路径**:所有 agent checkout 落到 `agents/<agent_name>/` 下
- **Python 环境**:每个 agent 用独立 venv 或 conda env,环境配置写在该 agent 的 `progress.md` 里
- **Canary backbone**:统一用 `google/gemini-3-flash` via OpenRouter(详见 `.env`),除非 task.md 明确要求别的
- **License 红线**:RareArena 是 CC-BY-NC-SA(学术 OK,商业不行);MIMIC-IV 数据**不传任何云 API**;PUMCH-ADM 暂时按未授权处理,先不动它
- **代码风格**:每个 stream 自成体系,不强求统一框架。Stream F harness 出来后再考虑统一接口

## 关键日期 / 决策点

- **Day 7 checkpoint**:Stream E canary 结果出 → 决定 10 个 agent 阵容是否要裁/补
- **Day 10 sanity-check**:3 个 LLM 控制组 + 200 例小子集端到端跑通
- **预注册 OSF**:必须在 PMC OA holdout 人工核验完成之前完成假设预注册(防自欺欺人)

---

## 当前未确认的全局问题(主 session 等用户回复)

- [ ] Gemini 3 Flash 在 OpenRouter 的确切 model ID(目前占位 `google/gemini-3-flash`)
- [ ] PMC OA 人工核验具体负责人
- [ ] MyGene2 / DDD 申请负责人
