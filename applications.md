# 受控数据集申请方案(MyGene2 + DDD)

> **状态**:v1 不阻塞主线实验(v1 的 Pillar 4 已规划为折入 Pillar 3 做 trio vs 单体分层)。两个申请到位后,数据进入 v2 升级 Pillar 4 为独立 pillar。
>
> **现在就提交** — DDD 审批周期 2-6 周,越早交越好。

---

## 1. MyGene2

### 一句话画像

家长/患者主导的开放罕见病数据共享平台(华盛顿大学 University of Washington Center for Mendelian Genomics 主办),家庭自愿提交先证者 + trio/pedigree 数据。**全开放数据**,但需要注册账号并同意条款。

### 用途映射

- **Pillar 4(Family-aware 诊断)**:提供 trio/pedigree 病例,作为遗传方式推理(AD/AR/XL/线粒体)的评估材料
- **预期病例数**:约 146 个先证者(2024 年公开统计),其中带 pedigree block 的部分可作 trio 评估

### 申请流程

```
Step 1 — 访问平台
  网址:https://mygene2.org/MyGene2/
  入口:右上角 "Login / Sign Up"

Step 2 — 账号注册
  需要:邮箱、机构隶属、研究目的简述(1-2 句)
  身份选项:Researcher / Clinician / Family — 选 Researcher
  通常即时通过,无需人工审核

Step 3 — 同意 Data Use Agreement
  关键条款(论文里需要 cite):
    - 数据 CC-BY 协议,可学术使用
    - 必须在出版物中 acknowledge MyGene2 和 University of Washington CMG
    - 不得尝试重新识别患者(re-identification)
    - 派生数据集需保持同样的开放协议

Step 4 — 下载或 API 访问
  - 病例浏览:网页前端 mygene2.org/MyGene2/profiles
  - 结构化导出:联系 contact@mygene2.org 请求 bulk export
    (报告里说 "for research benchmarking, please request structured
     CSV/JSON dumps with HPO + variant + pedigree blocks")

Step 5 — 持续访问
  注册账号长期有效;无需续期
```

### 预期周期

- 账号注册:**即时-几小时**
- Bulk export:邮件请求后 **1-5 个工作日**(Center for Mendelian Genomics 团队响应)

### 论文 acknowledgement 必备措辞

> "Data from MyGene2 (mygene2.org) is provided by participating families and the University of Washington Center for Mendelian Genomics, funded by NHGRI/NHLBI grant UM1HG006493."

### 负责人

- [ ] **填名字**

---

## 2. DDD(Deciphering Developmental Disorders)

### 一句话画像

英国/爱尔兰 13,500 个家庭的发育障碍 trio 队列(Wellcome Sanger Institute 主导),**EGA(European Genome-phenome Archive)受控访问**。Sci Rep s41598-024-53461-x 用其中 305 个 trio 做了 GPT-4 评估,是 family-aware 罕见病评估的当前最佳数据源。

### 用途映射

- **Pillar 4(Family-aware 诊断)**:提供 trio + de novo 变异 + 遗传方式标注的金标准
- **预期病例数**:305+ trio(参考已发表用法,实际可申请到的子集取决于 DAC 审批范围)

### 申请流程(这是受控访问 — 流程较长)

```
Step 1 — 在 EGA 注册账号
  网址:https://ega-archive.org/
  注册时填:机构邮箱(必须是 .edu/.ac.uk 等学术域名)、PI 信息、ORCID

Step 2 — 找到 DDD 的 EGA Dataset ID
  搜索 "EGAS00001000775"(DDD main study accession)
  关联的 dataset 例如 EGAD00001003776(请实际访问时核对最新 ID)
  这一步只是定位,不是申请

Step 3 — 准备 Data Access Application(核心)
  下载申请表:DDD Data Access Committee 主页
  网址:https://www.ddduk.org/access.html
  
  申请表关键字段(你需要写的内容):
    a) Title of Research Project
       建议措辞:"Benchmarking AI agent systems for rare disease 
        diagnosis with family-aware reasoning"
    
    b) Lay summary(非专业读者版,~200 字)
       要点:
       - 罕见病诊断 AI agent 的开放基准缺失
       - 我们构建首个 agent 评估框架,覆盖 5 个能力维度
       - DDD 数据用于评估 family-aware(trio/pedigree)能力维度
       - 不重新识别患者;仅做评估,不用于训练任何模型
    
    c) Scientific summary(详细技术版,~500 字)
       要点:
       - benchmark 设计的 5 个 pillar 与 metric 框架
       - DDD 在 Pillar 4 中的具体作用:trio 模式准确率、MOI 推理、
         de novo vs inherited 分类
       - 引用 Sci Rep 2024 (s41598-024-53461-x) 的 305 trio 用法作为
         先例(同样的"在 DDD 上评估 LLM 诊断"研究路径)
       - 数据使用范围:仅用于跑 baseline + agent 评估,**不微调任何模型**
       - 派生数据(评估结果、agent 错误分类)只发布聚合统计,不重发
         个体水平数据
    
    d) Data security plan
       - 数据存储位置:[填你的机构受控服务器 / 加密本地工作站]
       - 访问权限控制:仅 PI 和指定 named users
       - 销毁计划:研究结束后 6 个月内销毁本地副本
       - **不在云端 LLM API 调用中传入原始 trio 序列**;
         评估时只传入 HPO 词项 + 已 de-identify 的临床描述
       - **关键:不传 raw VCF 给商业 LLM API**;
         如果做基因型评估,要么本地跑模型,要么先做 variant-level
         消息抽象(例如只传 "在 X 基因上检测到 likely pathogenic
         missense variant",不传序列)
    
    e) Outputs and benefits
       - 发表 EMNLP 论文
       - 开源 benchmark harness + leaderboard
       - 公开 Pillar 4 评估代码(不含 DDD 原始数据)
    
    f) Named Users 列表
       PI + 所有需要访问数据的合作者,每人姓名、ORCID、机构邮箱、
       角色(分析/编程/标注)
    
    g) Co-investigator 签名
       PI 必签;每个 named user 单独签 confidentiality agreement

Step 4 — 提交后审批
  DDD DAC 通常 2-6 周回复
  常见反馈:要求澄清 data security、缩小数据使用范围、补充 IRB 信息

Step 5 — 通过后获取数据
  通过 EGA 下载客户端(pyega3)拉取数据
  下载需要 strong network + 几十 GB 到几百 GB 的存储

Step 6 — IRB / 机构伦理(可能需要)
  你所在机构(CMU?)的 IRB 通常需要审批,但用 de-identified
  公开队列的回顾性 secondary analysis 大多走 exempt 路径
  这一步并行 Step 3 启动
```

### 预期周期

- 申请表准备 + 内部签字:**1 周**
- DDD DAC 审批:**2-6 周**(中位约 3-4 周)
- 数据下载:**几天**(取决于网速)
- IRB exempt 申请并行:**1-3 周**

### 备选(如果 DDD 不批)

- **100,000 Genomes Project**:Genomics England Research Environment,审批 2-4 个月,且必须在 GE 安全环境内分析(不能下载)— 不适合 v2 timeline
- **AnVIL CCDG**:NHGRI 队列在 AnVIL 平台,审批 1-2 个月,云原生分析
- **退路**:仅用 MyGene2 + Phenopacket-Store 中带 pedigree block 的子集做 Pillar 4

### 论文 acknowledgement 必备措辞

> "The DDD study presents independent research commissioned by the Health Innovation Challenge Fund (HICF-1009-003), a parallel funding partnership between Wellcome and the Department of Health, and the Wellcome Sanger Institute (WT098051)."

### 负责人

- [ ] **填名字**
- [ ] 机构 IRB 联系人(确认是否需要 exempt 申请)

---

## 申请优先级与时间盒

| 周次 | MyGene2 动作 | DDD 动作 |
|---|---|---|
| Week 0(今天) | 注册账号 + 发邮件请求 bulk export | 起草申请表 lay + scientific summary |
| Week 1 | 收到数据 → 接入数据 schema | 提交申请表 + 启动机构 IRB exempt |
| Week 2-4 | 已可用 | 等待 DAC 反馈,准备回复澄清 |
| Week 5-7 | — | 接收数据 → 接入 schema → 升级 Pillar 4 |

**关键判断点**:Week 4 结束如果 DDD 还没通过,Pillar 4 v2 只依赖 MyGene2 + Phenopacket-Store pedigree 子集;Pillar 4 升级延期到 camera-ready / 期刊版。
