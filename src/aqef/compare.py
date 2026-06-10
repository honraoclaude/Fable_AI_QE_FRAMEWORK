"""Baseline comparison: detect regressions between two metric snapshots.

Eval-driven practice: a change that ships without a baseline comparison is a
future incident. Passing the gate's absolute thresholds is necessary but not
sufficient — a metric can clear its threshold while sliding toward it. This
module makes that slide visible and, with --fail-on-regression, blocking.

Direction semantics per rule operator:
  >= / >   higher is better
  <= / <   lower is better
  == / !=  closer to the target value is better (distance-to-target)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from aqef.config import Gate, Rule

_DIRECTION = {">=": "up", ">": "up", "<=": "down", "<": "down"}

IMPROVING = "improving"
WORSENING = "worsening"
FLAT = "flat"
NOT_COMPARABLE = "not comparable"


def assess_change(rule: Rule, old: float, new: float) -> str:
    """Judge a metric's movement against its rule's direction."""
    if new == old:
        return FLAT
    direction = _DIRECTION.get(rule.operator)
    if direction is None:
        # Equality-style rules: improvement is moving closer to the target.
        old_distance = abs(old - rule.threshold)
        new_distance = abs(new - rule.threshold)
        if new_distance == old_distance:
            return FLAT
        return IMPROVING if new_distance < old_distance else WORSENING
    moved_up = new > old
    return IMPROVING if moved_up == (direction == "up") else WORSENING


@dataclass(frozen=True)
class MetricDelta:
    metric: str
    severity: str
    baseline: float | None
    current: float | None
    assessment: str

    def describe(self) -> str:
        baseline = "—" if self.baseline is None else f"{self.baseline:g}"
        current = "—" if self.current is None else f"{self.current:g}"
        return (
            f"[{self.severity:8}] {self.metric}: {baseline} -> {current} "
            f"({self.assessment})"
        )


def compare_metrics(
    gate: Gate,
    current: Mapping[str, float],
    baseline: Mapping[str, float],
) -> list[MetricDelta]:
    """One delta per gate rule, in rule order. Missing values are reported,
    never inferred."""
    deltas = []
    for rule in gate.rules:
        old = baseline.get(rule.metric)
        new = current.get(rule.metric)
        if old is None or new is None:
            assessment = NOT_COMPARABLE
        else:
            assessment = assess_change(rule, float(old), float(new))
        deltas.append(
            MetricDelta(
                metric=rule.metric,
                severity=rule.severity,
                baseline=None if old is None else float(old),
                current=None if new is None else float(new),
                assessment=assessment,
            )
        )
    return deltas


def regressions(
    deltas: Iterable[MetricDelta],
    severities: tuple[str, ...] = ("blocking", "warning"),
) -> list[MetricDelta]:
    """Deltas that worsened on rules whose severity can affect a verdict.
    info-severity movement is recorded but never blocks."""
    return [d for d in deltas if d.assessment == WORSENING and d.severity in severities]


def format_comparison(deltas: list[MetricDelta]) -> str:
    ordered = sorted(deltas, key=lambda d: d.assessment != WORSENING)
    lines = ["Baseline comparison:"]
    lines += [f"  {d.describe()}" for d in ordered]
    return "\n".join(lines)


def delta_to_dict(delta: MetricDelta) -> dict:
    return {
        "metric": delta.metric,
        "severity": delta.severity,
        "baseline": delta.baseline,
        "current": delta.current,
        "assessment": delta.assessment,
    }
