RareAgentBench 实验结果定版报告 — frozen_v2_20260728

一、重复的根源

原始 dataset 无重复：canonical 采样帧 2000 唯一无重复；pmc gold 198/220 唯一；rarebench 子源(HMS/LIRICAL/MME/RAMEDIS)正常。
重复全部来自跑的过程：断点续跑(resume)、重试(retry)、并行 worker 把同一 case 的 receipt 多写了几次。
全局：104 个 cell 文件，35 个含重复，原始 105066 行 → 去重后 103578 唯一 case，清掉 1488 条重复行。
去重规则：按 case_id 保留一条，优先 status=ok 且有预测的那条(与 recompute_engine.dedupe_cases 同口径)。

二、冻结结果概览

Agent(8)：llm_control, mdagents, medagents, agentclinic, deeprare, maidxo, lirical(offline), vc_rdagent(offline)
Backbone(4)：Gemini 3 Flash, DeepSeek V4-Pro, DeepSeek V4-Flash, GPT-5 minimal
Dataset(5)：phenopacket_store, rarearena_rds, rarebench, pmc_oa_holdout, pmc_precutoff
Cell 文件总数：104
主表 4×6×4=96 个 LLM cell：全部有数据，缺失 0
去重后总唯一预测：103578；其中 valid(ok+非空)：100881（97.4%）

三、需重跑 / 样本不足（DeepRare & MAI-DxO 在开发层 unique<150）

  rarearena_rds      deeprare  V4-Pro    unique=  54 valid=  36
  rarearena_rds      maidxo    V4-Pro    unique=  59 valid=  54
  phenopacket_store  maidxo    V4-Pro    unique=  71 valid=  65
  phenopacket_store  maidxo    V4-Flash  unique=  78 valid=  15
  rarebench          deeprare  V4-Pro    unique=  82 valid=  42
  phenopacket_store  deeprare  GPT-5     unique= 100 valid=  92
  phenopacket_store  maidxo    Gemini    unique= 100 valid=  81
  rarearena_rds      deeprare  GPT-5     unique= 100 valid=  42
  rarearena_rds      maidxo    Gemini    unique= 100 valid=  88
  rarebench          deeprare  GPT-5     unique= 100 valid=  95
  phenopacket_store  deeprare  V4-Pro    unique= 111 valid=  96
  rarebench          maidxo    V4-Pro    unique= 139 valid=  65

四、valid 率偏低(<80%，多为 V4-Flash empty-content)

  phenopacket_store  maidxo      V4-Flash  unique=  78 valid=  15 (19%)
  pmc_oa_holdout     maidxo      GPT-5     unique= 198 valid=  80 (40%)
  rarearena_rds      deeprare    GPT-5     unique= 100 valid=  42 (42%)
  pmc_oa_holdout     maidxo      Gemini    unique= 198 valid=  91 (46%)
  rarebench          maidxo      V4-Pro    unique= 139 valid=  65 (47%)
  rarebench          deeprare    V4-Pro    unique=  82 valid=  42 (51%)
  pmc_oa_holdout     maidxo      V4-Flash  unique= 198 valid= 110 (56%)
  pmc_oa_holdout     maidxo      V4-Pro    unique= 198 valid= 120 (61%)
  rarearena_rds      medagents   V4-Flash  unique=2000 valid=1292 (65%)
  rarearena_rds      deeprare    V4-Pro    unique=  54 valid=  36 (67%)
  pmc_oa_holdout     medagents   V4-Flash  unique= 198 valid= 137 (69%)
  rarebench          medagents   V4-Flash  unique=1122 valid= 783 (70%)