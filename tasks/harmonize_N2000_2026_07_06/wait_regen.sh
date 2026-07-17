#!/bin/bash
cd /Users/yutianzhao/Desktop/RDAgentBenchmark
# wait for topup done
while ! grep -q "TOPUP ALL DONE" tasks/harmonize_N2000_2026_07_06/logs/_topup.log 2>/dev/null; do
  pgrep -f "topup.sh" >/dev/null || break
  sleep 60
done
echo "TOPUP_DONE_REGEN_START $(date)" >> /tmp/harmonize_regen.log
# full regen (canonical-capped)
python3 -u scripts/regen_receipts_and_figures.py >> /tmp/harmonize_regen.log 2>&1
python3 -u scripts/phase4a_report_gen.py >> /tmp/harmonize_regen.log 2>&1
python3 -u scripts/phase4a_ci_bootstrap.py >> /tmp/harmonize_regen.log 2>&1
python3 -u scripts/paper_figures.py >> /tmp/harmonize_regen.log 2>&1
python3 -u scripts/cost_analysis_appendix_j.py >> /tmp/harmonize_regen.log 2>&1
echo "REGEN_ALL_DONE $(date)" >> /tmp/harmonize_regen.log
