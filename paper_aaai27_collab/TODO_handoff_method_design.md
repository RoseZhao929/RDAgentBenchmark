交接 TODO — Method / Design / Supplementary 需配合 Main Results 的改动

背景：Main Results（MainResults.tex）这一轮做了大幅精简，把不属于"用 benchmark 得到的 agent 发现"的内容移出了正文。以下是需要前面章节（同事负责的 AnonymousSubmission2027 的 method/design 段 + Supplementary）配合调整的点。MainResults.tex 已改好，不用动它。

一、Self-Preference / LLM-as-judge 可靠性分析（从 Main Results 移出）
- Main Results 里原来有一整节 "Self-Preference Bias in LLM-as-Judge"（Protocol / Judge-family sensitivity / Effect on H10 / Implications 四段），现已删除。
- Main Results 现在只在 findings 收尾保留一句：换裁判分数移动 .40--.50 点 → trace 分当 exploratory、headline 靠 deterministic matching，并 refer 图 (f)。
- 需要同事做：把移出的完整论证放到 method/design 或 supplementary，作为"我们为什么这样设计 P5 评测"的支撑（judge-family 敏感性 → 用多裁判 + 人工复核）。建议位置：evaluation methodology 或 supplementary 的评测协议节。
- 素材：完整原文在 MainResults.tex.bak_pre_selfpref_del（本目录），可直接取用。
- 注意：原文里有几处暴露我们自己管线 bug 的表述（v1 漏传 conversation_history、抓取不全、"trace-capture artifact"、v1/v2 pipeline 修复），这些是运行/工程失误，不是发现，搬过去时也不要写进论文正文/supplementary 的对外表述。

二、physician adjudication / 多裁判（A12）状态需与实际对齐
- paper_sections 里多处写 "physician validation remains future work" / "planned" / "A1-A3, A5-A12 TODO"。
- 但据雨恬确认：200 条人工评审实际已完成。
- 需要同事：把 method/design/conclusion 里 physician adjudication 的措辞从 "planned/future work" 更新为"已完成"，并确保 A12（多裁判 + 人工交叉验证）的描述与实际一致。否则会 underclaim（把已做的说成计划）。

三、deterministic matching 的定义（Main Results 引用了这个术语）
- Main Results 收尾句用了 "rely on deterministic matching for the headline metrics"。
- 确保 method 节有 deterministic matching 的定义：预测疾病名/ID 与 gold（OMIM/ORPHA）做程序化匹配（+ variant-aware 模糊匹配），客观可复现，区别于 LLM-as-judge 和人工评审。

四、Main Results 里删掉的外链（前面章节若被引用要检查）
Main Results 已删除以下对 supplement/appendix 的外链（改为正文自包含）：
- Appendix G（cost 明细）、Appendix I（bootstrap CI）、Appendix C（trace patches）
- "supplement, Temporal-Holdout Protocol"、开头 "appear in the supplement"
- section 交叉引用 sec-5-2（Backbones）已从 Main Results 删除
这些内容本身仍应在 supplementary 存在，只是 Main Results 不再指向。若 supplementary 依赖 Main Results 的 label 反向引用，需检查。

五、命名统一
- Main Results 已把 MIMIC-N 全部改为 MIMIC-IV-Note，并删除所有 "de-leaked / leakage" 表述（不再强调 leakage 主题）。
- 若 method/design/supplementary 仍用 MIMIC-N 或强调 leakage，需与 Main Results 统一（除非 leakage 内容你们决定单独保留在 supplementary 作为独立 topic）。

六、design/method 里 P5 相关内容需去重（重要）
Main Results 现在只保留一句 self-preference 结果发现（换裁判分数移动 .40--.50 点 → trace 分当 exploratory、headline 靠 deterministic matching）+ 图 (f)。
因此 design/method 部分需要检查并分工：
- 保留（方法层，不与 Main Results 重复）：P5 pillar 的定义与评分四轴（factuality/relevance/depth/faithfulness）、judge 协议、以及 deterministic matching 的定义。
- 删除（发现层，已归 Main Results）：design 里若有重复讲"换裁判分数变 / self-preference 效应 / .40--.50 点"这类结果性表述，应删掉，避免与 Main Results 那句重复。
- 原则：design 讲"怎么评的"，Main Results 讲"评出了什么"，两边不重叠。

七、图
- Main Results 6-panel 主图（fig:main6）现为：(a) LLM-vs-classical stacked (figM1_v2a) / (b) cost-accuracy (figM2) / (c) hypotheses (figM6) / (d) scaffolding (figF2) / (e) prevalence (figM3) / (f) self-pref judge-swap (figM5)。
- 独立的 figM7（latency "orchestration cost buys no accuracy"）已从 Main Results 删除，论点并入 F2 文字。
