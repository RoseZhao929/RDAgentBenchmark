"""Per-agent adapter shims producing PredictionLog from CanonicalCase.

Public surface:
- `AgentAdapter` — base class (in `harness.agents.base`)
- Concrete adapters (added by subagents as they complete):
  `MDAgentsAdapter`, `MedAgentsAdapter`, `AgentClinicAdapter`,
  `MaiDxOAdapter`, `DeepRareAdapter`,
  `VCRDAgentAdapter`, `RDMAAdapter`,
  `LIRICALAdapter`.

Note: dropped from v1 lineup: PhenoBrain (Drive sub-folder contents 缺失,
see round1_execution_report.md Plan B decision).
"""

from harness.agents.base import AgentAdapter
from harness.agents.agentclinic import AgentClinicAdapter
from harness.agents.deeprare import DeepRareAdapter, parse_deeprare_final_diagnois
from harness.agents.lirical import LIRICALAdapter
from harness.agents.llm_control import LLMControlAdapter
from harness.agents.maidxo import MaiDxOAdapter
from harness.agents.mdagents import MDAgentsAdapter
from harness.agents.medagents import MedAgentsAdapter
from harness.agents.rdma import RDMAAdapter
from harness.agents.vc_rdagent import VCRDAgentAdapter

# concrete adapter exports populated lazily as files are added
__all__ = [
    "AgentAdapter",
    "AgentClinicAdapter",
    "DeepRareAdapter",
    "LIRICALAdapter",
    "LLMControlAdapter",
    "MDAgentsAdapter",
    "MaiDxOAdapter",
    "MedAgentsAdapter",
    "RDMAAdapter",
    "VCRDAgentAdapter",
    "parse_deeprare_final_diagnois",
]
