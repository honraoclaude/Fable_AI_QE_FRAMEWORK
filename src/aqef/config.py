"""Schema and validation for framework.yaml.

Validation is strict and errors are specific: a misconfigured quality system is
worse than none, because it manufactures false confidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

VALID_OPERATORS = {">=", "<=", ">", "<", "==", "!="}
VALID_SEVERITIES = {"blocking", "warning", "info"}
VALID_CHECKPOINTS = {"always", "on_fail", "never"}


class ConfigError(ValueError):
    """Raised when framework.yaml is structurally or referentially invalid."""


@dataclass(frozen=True)
class Rule:
    metric: str
    operator: str
    threshold: float
    severity: str


@dataclass(frozen=True)
class Gate:
    name: str
    description: str
    rules: tuple[Rule, ...]


@dataclass(frozen=True)
class AgentDef:
    name: str
    role: str
    trust_tier: int
    spec: str


@dataclass(frozen=True)
class Step:
    agent: str
    action: str


@dataclass(frozen=True)
class Workflow:
    name: str
    description: str
    steps: tuple[Step, ...]
    gate: str
    human_checkpoint: str


@dataclass(frozen=True)
class FrameworkConfig:
    version: str
    name: str
    default_tier: int
    trust_tiers: dict[int, str]
    agents: dict[str, AgentDef]
    gates: dict[str, Gate]
    workflows: dict[str, Workflow]


def load_config(path: str | Path) -> FrameworkConfig:
    raw = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    return parse_config(data)


def parse_config(data: dict) -> FrameworkConfig:
    for section in ("trust", "agents", "gates", "workflows"):
        if section not in data:
            raise ConfigError(f"missing required section: {section!r}")

    trust = data["trust"]
    tiers_raw = trust.get("tiers")
    if not isinstance(tiers_raw, dict) or not tiers_raw:
        raise ConfigError("trust.tiers must be a non-empty mapping")
    trust_tiers = {int(k): str(v) for k, v in tiers_raw.items()}
    default_tier = int(trust.get("default_tier", min(trust_tiers)))
    if default_tier not in trust_tiers:
        raise ConfigError(f"trust.default_tier {default_tier} is not a defined tier")

    agents = {
        name: _parse_agent(name, spec, trust_tiers)
        for name, spec in data["agents"].items()
    }
    gates = {name: _parse_gate(name, spec) for name, spec in data["gates"].items()}
    workflows = {
        name: _parse_workflow(name, spec, agents, gates)
        for name, spec in data["workflows"].items()
    }

    return FrameworkConfig(
        version=str(data.get("version", "0")),
        name=str(data.get("name", "unnamed framework")),
        default_tier=default_tier,
        trust_tiers=trust_tiers,
        agents=agents,
        gates=gates,
        workflows=workflows,
    )


def _parse_agent(name: str, spec: dict, trust_tiers: dict[int, str]) -> AgentDef:
    if not isinstance(spec, dict):
        raise ConfigError(f"agent {name!r}: definition must be a mapping")
    try:
        tier = int(spec["trust_tier"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigError(f"agent {name!r}: trust_tier must be an integer") from exc
    if tier not in trust_tiers:
        raise ConfigError(f"agent {name!r}: trust_tier {tier} is not a defined tier")
    return AgentDef(
        name=name,
        role=str(spec.get("role", "unspecified")),
        trust_tier=tier,
        spec=str(spec.get("spec", "")),
    )


def _parse_gate(name: str, spec: dict) -> Gate:
    if not isinstance(spec, dict):
        raise ConfigError(f"gate {name!r}: definition must be a mapping")
    rules_raw = spec.get("rules")
    if not isinstance(rules_raw, list) or not rules_raw:
        raise ConfigError(f"gate {name!r}: must define a non-empty rules list")
    rules = tuple(_parse_rule(name, i, r) for i, r in enumerate(rules_raw))
    return Gate(name=name, description=str(spec.get("description", "")), rules=rules)


def _parse_rule(gate_name: str, index: int, raw: dict) -> Rule:
    where = f"gate {gate_name!r} rule #{index + 1}"
    if not isinstance(raw, dict):
        raise ConfigError(f"{where}: must be a mapping")
    metric = raw.get("metric")
    if not metric or not isinstance(metric, str):
        raise ConfigError(f"{where}: 'metric' is required and must be a string")
    operator = raw.get("operator")
    if operator not in VALID_OPERATORS:
        raise ConfigError(
            f"{where}: operator {operator!r} not in {sorted(VALID_OPERATORS)}"
        )
    threshold = raw.get("threshold")
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
        raise ConfigError(f"{where}: threshold must be numeric, got {threshold!r}")
    severity = raw.get("severity")
    if severity not in VALID_SEVERITIES:
        raise ConfigError(
            f"{where}: severity {severity!r} not in {sorted(VALID_SEVERITIES)}"
        )
    return Rule(
        metric=metric, operator=operator, threshold=float(threshold), severity=severity
    )


def _parse_workflow(
    name: str,
    spec: dict,
    agents: dict[str, AgentDef],
    gates: dict[str, Gate],
) -> Workflow:
    if not isinstance(spec, dict):
        raise ConfigError(f"workflow {name!r}: definition must be a mapping")

    steps_raw = spec.get("steps")
    if not isinstance(steps_raw, list) or not steps_raw:
        raise ConfigError(f"workflow {name!r}: must define a non-empty steps list")
    steps = []
    for i, raw in enumerate(steps_raw):
        where = f"workflow {name!r} step #{i + 1}"
        if not isinstance(raw, dict) or "agent" not in raw or "action" not in raw:
            raise ConfigError(f"{where}: each step needs 'agent' and 'action'")
        if raw["agent"] not in agents:
            raise ConfigError(f"{where}: unknown agent {raw['agent']!r}")
        steps.append(Step(agent=str(raw["agent"]), action=str(raw["action"])))

    gate = spec.get("gate")
    if gate not in gates:
        raise ConfigError(f"workflow {name!r}: unknown gate {gate!r}")

    checkpoint = spec.get("human_checkpoint", "always")
    if checkpoint not in VALID_CHECKPOINTS:
        raise ConfigError(
            f"workflow {name!r}: human_checkpoint {checkpoint!r} "
            f"not in {sorted(VALID_CHECKPOINTS)}"
        )

    return Workflow(
        name=name,
        description=str(spec.get("description", "")),
        steps=tuple(steps),
        gate=str(gate),
        human_checkpoint=str(checkpoint),
    )
