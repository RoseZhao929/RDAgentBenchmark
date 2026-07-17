# Harness — Rare Disease Agent Benchmark

Python package wrapping:
1. **Canonical case schema** — `canonical_case.py`(Pydantic v2)
2. **Per-dataset ingest adapters** — `ingest/`
3. **Per-agent adapter shims** — `agents/`(每个 agent 一个 module,Step 0 任务)
4. **Metric library** — `metrics/`
5. **Prediction log schema + cost/latency capture** — `logging/`

## 安装(等到 Stream F 完成后)

```bash
cd harness
pip install -e .[dev]
```

## 用法草稿

```python
from harness import CanonicalCase
from harness.ingest import ingest_rarearena
from harness.metrics import recall_at_k

cases = ingest_rarearena("/path/to/data/rarearena/benchmark_data/RDS_benchmark.jsonl")
# cases: List[CanonicalCase]

# ... 调用 agent ...
predictions = []  # List[Dict[str, Any]] from each agent

# 评估
metric = recall_at_k(predictions, cases, k=1)
```

## 设计文档

详见根目录:
- `round1_plan.md` § Stream B / F
- `plan.md` § 8 主实验设计
- `agent_methods.md` § 评估系统阵容

## TODO(Stream F 子任务)

- [x] `canonical_case.py` — Pydantic models
- [ ] `canonical_case.schema.json` — 自动 export
- [ ] `ingest/phenopacket_store.py`
- [ ] `ingest/rarebench.py`
- [ ] `ingest/rarearena.py`
- [ ] `ingest/mimic_iv.py`(等用户提供 MIMIC 数据后)
- [ ] `ingest/pmc_oa.py`(等 Stream D 流水线)
- [ ] `metrics/accuracy.py`(Recall@k, MR, MRR)
- [ ] `metrics/phenotype.py`(HPO P/R/F1)
- [ ] `metrics/calibration.py`(Brier, ECE, Confidence AUROC)
- [ ] `metrics/reliability.py`(pass^k)
- [ ] `metrics/cost.py`(token cost, latency, cost-normalized accuracy)
- [ ] `logging/schema.py`(JSONL prediction log schema)
- [ ] `logging/backend.py`(per-call logger + OpenRouter token accounting)
- [ ] `agents/base.py`(adapter shim base class)
- [ ] `agents/deeprare.py`(10 个 agent 各一个 module)
- [ ] ... 等等

## Pydantic schema 验证

```python
from harness import CanonicalCase
case = CanonicalCase.model_validate(some_dict)
# 自动验证 HP:xxxxxxx / OMIM:xxxxxx / ORPHA:xxx pattern
```

```python
# Export JSON Schema for OSF preregistration package
import json
print(json.dumps(CanonicalCase.model_json_schema(), indent=2))
```
