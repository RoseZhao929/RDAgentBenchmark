# Yutian 10% coverage run — handoff

Branch: `run/coverage-10pct-yutian-20260728`

Scope: the nine cells assigned in `PLAN_yutian.md`. Final case-level receipts
are in `data/round2/phase4a/`; intermediate fixed-prefix files and raw attempt
archives stay under the gitignored `logs/coverage_10pct_20260728/`.

## Final coverage audit

- Target/actual: 1,713 / 1,713 rows and unique case IDs.
- Exact target membership: passed for all nine cells.
- Scoreable attempted-denominator rows: 1,713 / 1,713.
- Statuses: 1,311 `ok`, 402 `parser_error`/explicit abstention.
- Infrastructure failures: 0 `agent_error`, 0 `timeout`.
- Schema checks: no malformed JSON, duplicate predictions, invalid metadata,
  non-positive latency, or `ok` rows with empty predictions.
- Machine-readable report:
  `logs/coverage_10pct_20260728/audit_yutian.json` (gitignored runtime evidence).

The high MAI-DxO/Gemini abstention rate is the corrected post-regex behavior,
not an infrastructure failure: PP has 17/200 `ok`; RareArena has 20/200 `ok`.
Explicit refusal/“unable to establish” responses remain attempted misses and
are not selectively retried.

## Changes relative to the plan branch

1. Canonical backbone IDs are passed to the harness while AIHub wire-model
   aliases are kept separate.
2. DeepRare concurrent calls use private per-case CSV inputs; the historical
   shared `dataset/cases.csv` caused cross-case input races.
3. DeepRare sends gateway-compatible reasoning parameters and surfaces API
   exceptions instead of silently swallowing them.
4. Empty diagnosis candidate sets take the normal fallback path rather than
   crashing the tokenizer.
5. DeepRare parses both Markdown headings and plain numbered diagnosis lists.
   A final response with no ranked diagnoses is a `parser_error`, never an
   empty `ok`.
6. RareArena free text is converted to HPO before DeepRare runs. The internal
   extractor uses the AIHub wire ID `gemini-3-flash-preview`; the canonical
   provider-prefixed alias returned HTTP 400.
7. If free-text extraction cannot normalize any HPO IDs, the case is retained
   as an attempted `parser_error`; DeepRare is not allowed to hallucinate from
   an empty input.
8. All 200 RareArena/DeepRare receipts were rerun after the input fix. One PP
   and two RareBench receipts affected by the old shared-CSV race were also
   rerun.
9. Frozen pre-regex MAI-DxO prefixes were rerun separately and deterministically
   overlaid before final compaction, so old and corrected implementations are
   not mixed.

## Reproduce the audit

```bash
python3 tasks/coverage_10pct_20260728/audit_yutian.py
/tmp/paper_venv/bin/python audit_frozen/recompute_engine.py
/tmp/paper_venv/bin/python audit_frozen/build_deliverables.py
```

Do not commit or copy `.env`, raw gateway logs, or any DUA-controlled data.
