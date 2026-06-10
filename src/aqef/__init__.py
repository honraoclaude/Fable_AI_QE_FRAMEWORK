"""AQEF — reference implementation of the AI Agentic Quality Engineering Framework.

The mechanical core: load and validate framework.yaml, evaluate quality gates
fail-closed, and run workflows through pluggable agent adapters. The judgment
lives in the agent specs and the humans operating them; this package only
enforces what was configured.
"""

from aqef.config import (
    AgentDef,
    ConfigError,
    FrameworkConfig,
    Gate,
    Rule,
    Step,
    Workflow,
    load_config,
    parse_config,
)
from aqef.gates import GateResult, RuleResult, evaluate_gate
from aqef.orchestrator import StepResult, WorkflowResult, run_workflow

__version__ = "1.0.0"

__all__ = [
    "AgentDef",
    "ConfigError",
    "FrameworkConfig",
    "Gate",
    "GateResult",
    "Rule",
    "RuleResult",
    "Step",
    "StepResult",
    "Workflow",
    "WorkflowResult",
    "evaluate_gate",
    "load_config",
    "parse_config",
    "run_workflow",
]
