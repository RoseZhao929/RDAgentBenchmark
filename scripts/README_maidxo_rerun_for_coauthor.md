# maidxo 重跑 —— 给 co-author 的说明

## 一句话
maidxo 之前的 4 个 backbone 结果全废（正则 bug，见下）。bug 已修好，
只需在**这台机器**上跑一条命令重跑，跑完通知主作者打分即可。

## 怎么跑
在本机、仓库根目录（`/home/research/RDAgentBenchmark`）下，用你自己的登录：

```bash
cd /home/research/RDAgentBenchmark
bash scripts/rerun_maidxo_after_regexfix.sh
```

就这一条。脚本会自己：
1. 检查修复在位、venv/输入/`.env` 都在（缺任何一个会报错中止，不会跑坏）；
2. 把 7/25 的旧（bug 版）maidxo 结果挪到 `data/round2/_maidxo_prefix_backup_prefix/`
   —— **必须挪走**，否则 runner 的 resume 会把旧垃圾行当成"已完成"跳过；
3. 4 个 backbone 并行重跑 × 416 例（v4-pro / v4-flash / gpt-5 / gemini-3-flash）。

**不用配任何 API key**：gateway 配置在仓库根 `.env` 里，runner 自动加载。

## 看进度
```bash
tail -f logs/mimic_note/maidxo_rerun_*.log
# 每个文件跑到 416 行即完成：
wc -l data/round2/phase4a_mimic_note/predictions_mimic_note_maidxo_*.jsonl
```
4 个 log 都出现 `[p4a] DONE` = 全部跑完。预计几小时（跟当时机器负载有关）。

## 跑完做什么
**什么都不用做**，通知主作者「maidxo 4 个 backbone 都 DONE」即可。
打分并入 24-cell 主矩阵由主作者统一做（保证打分口径一致）。

## ⚠️ 数据合规（重要，别踩）
MIMIC 数据受 PhysioNet DUA 约束：
- **只能在这台已授权机器上跑**。不要把 `data/` 目录、`.env`、或任何病历文本
  拷到你自己的笔记本/别的机器。
- 输出的逐案预测（`data/round2/...jsonl`）含 de-identified case id，同样留在本机、
  不入 git（`data/` 已全目录 gitignore）。

## 这个 bug 到底是啥（如果你想知道）
maidxo 面板辩论流程本身是对的，坏在**最后从辩论文本里抽诊断**的正则
（`agents/maidxo/mai_dx/main.py`）。那个正则太贪婪，会把出院小结里的
生命体征行 `"... 87/35, 97% on RA"` 整段当成一个诊断，置信度读成 0.97，
于是触发 `>0.90 就自动收工` 的短路 —— 面板第一轮就拿"血氧饱和度 97%"
当最终答案交卷了。修复：在接受候选诊断前，先用 `looks_like_vitals` 把
明显是生命体征/化验/比值（含 `BP HR SpO2`、`90/40` 这类、或数字占比过高）
的片段剔掉。冒烟测过：辩论恢复正常（iters 从 1 回到 3，不再吐垃圾）。
