"""Gate evaluation: declarative rules over metrics, fail-closed.

Semantics (see docs/03-quality-gates.md):
  blocking rule violated or metric missing -> FAIL
  warning  rule violated or metric missing -> WARN (at best)
  info     rules are recorded, never affect the verdict
Verdict precedence: FAIL > WARN > PASS.
"""

from __future__ import annotations

import operator as _op
from dataclasses import dataclass
from typing import Mapping

from aqef.config import Gate, Rule

_OPS = {
    ">=": _op.ge,
    "<=": _op.le,
    ">": _op.gt,
    "<": _op.lt,
    "==": _op.eq,
    "!=": _op.ne,
}

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"


@dataclass(frozen=True)
class RuleResult:
    rule: Rule
    actual: float | None  # None when the metric was never collected
    passed: bool          # always False when missing (fail closed)

    @property
    def missing(self) -> bool:
        return self.actual is None

    def describe(self) -> str:
        actual = "— missing —" if self.missing else f"{self.actual:g}"
        outcome = "pass" if self.passed else ("MISSING EVIDENCE" if self.missing else "FAIL")
        return (
            f"[{self.rule.severity:8}] {self.rule.metric} = {actual} "
            f"(rule: {self.rule.operator} {self.rule.threshold:g}) -> {outcome}"
        )


@dataclass(frozen=True)
class GateResult:
    gate: str
    verdict: str  # PASS | WARN | FAIL
    results: tuple[RuleResult, ...]

    @property
    def failed(self) -> bool:
        return self.verdict == FAIL

    def rationale(self) -> str:
        """Human-auditable evidence: every rule, violations first."""
        ordered = sorted(self.results, key=lambda r: r.passed)
        lines = [f"Gate {self.gate!r}: {self.verdict}"]
        lines += [f"  {r.describe()}" for r in ordered]
        return "\n".join(lines)


def evaluate_rule(rule: Rule, metrics: Mapping[str, float]) -> RuleResult:
    actual = metrics.get(rule.metric)
    if actual is None:
        return RuleResult(rule=rule, actual=None, passed=False)
    passed = bool(_OPS[rule.operator](float(actual), rule.threshold))
    return RuleResult(rule=rule, actual=float(actual), passed=passed)


def evaluate_gate(gate: Gate, metrics: Mapping[str, float]) -> GateResult:
    results = tuple(evaluate_rule(rule, metrics) for rule in gate.rules)
    verdict = PASS
    for result in results:
        if result.passed or result.rule.severity == "info":
            continue
        if result.rule.severity == "blocking":
            verdict = FAIL
            break
        verdict = WARN  # warning severity; FAIL would have broken out already
    return GateResult(gate=gate.name, verdict=verdict, results=results)
