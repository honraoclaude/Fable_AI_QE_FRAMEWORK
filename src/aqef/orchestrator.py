"""Workflow runner: ordered agent steps -> merged metrics -> gate verdict.

Agent adapters are pluggable callables `(action, context) -> metrics dict`, so the
same workflow definition can be driven by LLM agents, classical tooling, or test
stubs. A step with no adapter, or a step that raises, contributes no metrics —
the gate then fails closed on whatever evidence is missing. The orchestrator
never invents data to fill a gap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping

from aqef.config import FrameworkConfig
from aqef.gates import GateResult, evaluate_gate

# An adapter executes one agent: (action, read-only context metrics) -> new metrics.
AgentAdapter = Callable[[str, Mapping[str, float]], Mapping[str, float] | None]


@dataclass(frozen=True)
class StepResult:
    agent: str
    action: str
    metrics: dict[str, float] = field(default_factory=dict)
    error: str | None = None  # adapter missing or raised; metrics stay absent

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class WorkflowResult:
    workflow: str
    steps: tuple[StepResult, ...]
    gate_result: GateResult
    human_checkpoint_required: bool

    def summary(self) -> str:
        lines = [f"Workflow {self.workflow!r}"]
        for step in self.steps:
            status = "ok" if step.ok else f"ERROR: {step.error}"
            lines.append(f"  {step.agent} · {step.action}: {status}")
        lines.append(self.gate_result.rationale())
        checkpoint = "REQUIRED" if self.human_checkpoint_required else "not required"
        lines.append(f"Human checkpoint: {checkpoint}")
        return "\n".join(lines)


def run_workflow(
    config: FrameworkConfig,
    workflow_name: str,
    adapters: Mapping[str, AgentAdapter],
    initial_metrics: Mapping[str, float] | None = None,
) -> WorkflowResult:
    try:
        workflow = config.workflows[workflow_name]
    except KeyError:
        known = ", ".join(sorted(config.workflows))
        raise KeyError(f"unknown workflow {workflow_name!r} (known: {known})") from None

    metrics: dict[str, float] = dict(initial_metrics or {})
    steps: list[StepResult] = []

    for step in workflow.steps:
        adapter = adapters.get(step.agent)
        if adapter is None:
            steps.append(
                StepResult(step.agent, step.action, error="no adapter registered")
            )
            continue
        try:
            emitted = adapter(step.action, dict(metrics)) or {}
        except Exception as exc:  # a failed step must not kill the audit trail
            steps.append(
                StepResult(step.agent, step.action, error=f"{type(exc).__name__}: {exc}")
            )
            continue
        emitted = {str(k): float(v) for k, v in emitted.items()}
        metrics.update(emitted)
        steps.append(StepResult(step.agent, step.action, metrics=emitted))

    gate_result = evaluate_gate(config.gates[workflow.gate], metrics)

    checkpoint_required = workflow.human_checkpoint == "always" or (
        workflow.human_checkpoint == "on_fail" and gate_result.failed
    )

    return WorkflowResult(
        workflow=workflow_name,
        steps=tuple(steps),
        gate_result=gate_result,
        human_checkpoint_required=checkpoint_required,
    )
