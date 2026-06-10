"""Evidence-based release recommendation: PROMOTE / HOLD / ROLLBACK.

Maps the gate verdict and (optionally) baseline movement into a single release
recommendation with reasons, following evidence-driven release management
practice for LLM-era systems (arXiv:2603.15676).

The recommendation is advisory by design: in this framework a human makes
release decisions (workflows with release impact run human_checkpoint: always).
This module's job is to make the evidence pointed and explainable, not to ship.

Mapping:
  FAIL                          -> ROLLBACK  (blocking evidence against the build)
  WARN                          -> HOLD      (degraded confidence; investigate)
  PASS + regressions vs baseline -> HOLD     (clears thresholds but sliding)
  PASS, clean                    -> PROMOTE
"""

from __future__ import annotations

from dataclasses import dataclass

from aqef.compare import MetricDelta, regressions
from aqef.gates import FAIL, WARN, GateResult

PROMOTE = "PROMOTE"
HOLD = "HOLD"
ROLLBACK = "ROLLBACK"


@dataclass(frozen=True)
class Decision:
    recommendation: str  # PROMOTE | HOLD | ROLLBACK
    reasons: tuple[str, ...]

    def describe(self) -> str:
        lines = [f"Recommendation: {self.recommendation}"]
        lines += [f"  - {reason}" for reason in self.reasons]
        lines.append(
            "  (advisory: the release decision belongs to the human quality owner)"
        )
        return "\n".join(lines)


def recommend(
    gate_result: GateResult,
    deltas: list[MetricDelta] | None = None,
) -> Decision:
    reasons: list[str] = []

    if gate_result.verdict == FAIL:
        for r in gate_result.results:
            if r.passed or r.rule.severity != "blocking":
                continue
            if r.missing:
                reasons.append(
                    f"blocking rule '{r.rule.metric}' has no collected evidence "
                    "(fail-closed)"
                )
            else:
                reasons.append(
                    f"blocking rule violated: {r.rule.metric} = {r.actual:g} "
                    f"(required {r.rule.operator} {r.rule.threshold:g})"
                )
        return Decision(recommendation=ROLLBACK, reasons=tuple(reasons))

    if gate_result.verdict == WARN:
        for r in gate_result.results:
            if r.passed or r.rule.severity != "warning":
                continue
            if r.missing:
                reasons.append(f"warning rule '{r.rule.metric}' missing evidence")
            else:
                reasons.append(
                    f"warning rule violated: {r.rule.metric} = {r.actual:g} "
                    f"(expected {r.rule.operator} {r.rule.threshold:g})"
                )
        return Decision(recommendation=HOLD, reasons=tuple(reasons))

    # PASS — but a pass that is sliding toward its thresholds is not a clean pass.
    if deltas is not None:
        regressed = regressions(deltas)
        if regressed:
            for d in regressed:
                reasons.append(
                    f"regression vs baseline: {d.metric} "
                    f"{d.baseline:g} -> {d.current:g} ({d.severity})"
                )
            return Decision(recommendation=HOLD, reasons=tuple(reasons))
        reasons.append("all gate rules satisfied; no regression vs baseline")
    else:
        reasons.append("all gate rules satisfied (no baseline provided)")
    return Decision(recommendation=PROMOTE, reasons=tuple(reasons))


def decision_to_dict(decision: Decision) -> dict:
    return {
        "recommendation": decision.recommendation,
        "reasons": list(decision.reasons),
        "advisory": True,
    }
