# Baseline Reproduction Documentation

This directory holds **per-baseline reproduction documents** for every
agent system evaluated in this benchmark. Each document records:

- Source (repo + commit, license, paper citation)
- Paper-claimed result (the R@1/R@5/Acc number we target)
- Faithful reproduction setup (mode, config, backbone)
- **Endpoint patches** (the ONLY allowed modifications — OpenRouter
  base_url wiring; no algorithmic changes)
- Adapter wrapper (in `harness/agents/` — case projection + output
  parsing, separate from baseline logic)
- Observed result vs paper, with setup-mismatch reasons
- Known incompatibilities (per-backbone)
- Run receipts (jsonl path, run-id)

## Why this exists

Per 2026-05-19 reviewer-defense rule(see `memory/feedback_strict_baseline_repro.md`):
**we do not vibe-modify baseline code or design.** Every per-baseline
patch is enumerated here so reviewers can verify which changes are
behavior-preserving (endpoint wiring) vs behavior-changing (parser
robustness, dual-report).

## Status

| Baseline | Doc | Last reviewed |
|---|---|---|
| mdagents | [mdagents.md](mdagents.md) | 2026-05-19 |
| medagents | [medagents.md](medagents.md) | 2026-05-19 |
| agentclinic | [agentclinic.md](agentclinic.md) | 2026-05-19 |
| maidxo | [maidxo.md](maidxo.md) | 2026-05-19 |
| deeprare | [deeprare.md](deeprare.md) | 2026-05-19 |
| rdma | [rdma.md](rdma.md) | 2026-05-19 |
| vc_rdagent | [vc_rdagent.md](vc_rdagent.md) | 2026-05-19 |
| lirical | [lirical.md](lirical.md) | 2026-05-19 |
| llm_control (internal baseline) | [llm_control.md](llm_control.md) | 2026-05-19 |
