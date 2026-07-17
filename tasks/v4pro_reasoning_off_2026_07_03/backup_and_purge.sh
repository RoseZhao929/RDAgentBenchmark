#!/bin/bash
# Backup old V4-Pro records (reasoning-ON / broken) for the 4 main agents,
# then remove originals so the reasoning-OFF rerun starts fresh.
set -eu
cd /Users/yutianzhao/Desktop/RDAgentBenchmark
BK=data/round2/phase4a_v4pro_reasoningON_backup_20260703
mkdir -p "$BK"
PRED=data/round2/phase4a
moved=0
for AG in llm_control agentclinic mdagents medagents; do
  for DS in phenopacket_store rarearena_rds mimic_diverse rarebench; do
    f="$PRED/predictions_${DS}_${AG}_deepseek_deepseek-v4-pro.jsonl"
    if [ -f "$f" ]; then
      mv "$f" "$BK/"
      moved=$((moved+1))
      echo "backed up + purged: $(basename $f)"
    fi
  done
done
echo "TOTAL backed up + purged: $moved files → $BK"
