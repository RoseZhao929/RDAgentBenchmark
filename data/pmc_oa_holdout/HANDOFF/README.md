# 罕见病病例人工核验 — 交接包

你好,感谢帮忙做这个标注任务。这个包是**自包含**的,所有需要的东西都在这个文件夹里。

## 一句话任务

从 1,433 个自动筛出的罕见病候选病例里,**人工核验挑出 ~200 个高质量的**,
每个病例做 4 项检查(诊断对不对、表型准不准、是不是 2024 年后的新报告、是不是真罕见病)。

## 你该怎么做(3 步)

1. **先读 `INSTRUCTIONS.md`** — 详细说明:4 项 check 怎么查、高效工作流、常见陷阱、输出格式。
2. **打开 `review_template.csv`**(Excel / Numbers / Google Sheets 都行)——
   已预填好 top-250 候选,你逐行填 7 个列(4 个 check + 决定 + 2 个辅助列)。
   **从第 11 行开始**(前 10 个 demo 已审,见参考文件)。填到累计 ~200 个 `accept` 即可停。
3. **填完把 `review_template.csv` 发回**给发你这个包的人。就这一个文件。

每个病例约 5–10 分钟。理想节奏:每天 30–50 个,1 人约 1 周 / 2 人 3–4 天。

## 文件清单

| 文件 | 是什么 |
|---|---|
| `README.md` | 本文件 |
| `INSTRUCTIONS.md` | **详细标注说明(必读)** |
| `review_template.csv` | **你要填的表**(250 行预填候选 + 待填的 check 列) |
| `candidates_full_pool.jsonl` | 全部 1,433 候选(CSV 250 个不够时,从第 251 行起补) |
| `demo_accepted_9.jsonl` | 参考:demo 已审通过的 9 个(学 notes 怎么写) |
| `demo_rejected_1.jsonl` | 参考:demo 拒掉的 1 个(学怎么 justify reject) |
| `demo_review_summary.md` | 参考:demo 全过程总结 + 实操 tips + 陷阱 |

## 要填的列(review_template.csv)

| 列 | 填什么 |
|---|---|
| `check1_diagnosis_match` | `pass` / `fail` — 诊断匹配正确? |
| `check2_hpo_accurate` | `pass` / `fail` — HPO 表型准确? |
| `check3_cutoff_verified` | `pass` / `fail` — 真是 2024-01-01 之后的新报告? |
| `check4_truly_rare` | `pass` / `fail` — 真是罕见病(≤1/2000)? |
| `review_decision` | `accept`(4 项全 pass)/ `reject`(任一 fail)/ `uncertain`(需二次核) |
| `hpo_phenotypes_clean` | `true` / `false`(辅助,不阻塞 accept) |
| `reviewer_notes` | reject/uncertain 必填:哪个 check fail + 证据(文章哪段) |

## 工具提示(重要)

**不要用浏览器逐个打开 orpha.net / pmc 网页**(慢 + 易触发验证码)。用 `INSTRUCTIONS.md §5`
的 NCBI E-utilities + Orphadata 离线 XML,10 个病例从 1 小时降到 ~30 秒。

## 有问题

审的过程中任何不确定 → 标 `uncertain` 暂存,**不要瞎拒**,集中找时间走第二轮。
发现某类病例系统性错误 → 直接反馈给发你这个包的人。
