"""Report generation: gate and workflow results as JSON or markdown.

The markdown report mirrors templates/quality-report.md: verdict first, then
rule-by-rule evidence with violations on top, missing evidence called out, and
the human checkpoint section. Sections that require human judgment (residual
risk, checkpoint decision) are emitted as explicit placeholders — the renderer
never fabricates content a human is supposed to supply.
"""

from __future__ import annotations

from datetime import datetime, timezone

from aqef.config import Workflow
from aqef.gates import GateResult, RuleResult
from aqef.orchestrator import WorkflowResult


def rule_result_to_dict(result: RuleResult) -> dict:
    return {
        "metric": result.rule.metric,
        "operator": result.rule.operator,
        "threshold": result.rule.threshold,
        "severity": result.rule.severity,
        "actual": result.actual,
        "missing": result.missing,
        "passed": result.passed,
    }


def gate_result_to_dict(result: GateResult) -> dict:
    return {
        "gate": result.gate,
        "verdict": result.verdict,
        "rules": [rule_result_to_dict(r) for r in result.results],
    }


def workflow_result_to_dict(result: WorkflowResult) -> dict:
    return {
        "workflow": result.workflow,
        "steps": [
            {
                "agent": s.agent,
                "action": s.action,
                "ok": s.ok,
                "metrics": s.metrics,
                "error": s.error,
            }
            for s in result.steps
        ],
        "gate": gate_result_to_dict(result.gate_result),
        "human_checkpoint_required": result.human_checkpoint_required,
    }


def _outcome_cell(result: RuleResult) -> str:
    if result.passed:
        return "pass"
    if result.missing:
        return "**MISSING EVIDENCE**"
    return "**FAIL**"


def _verdict_summary(result: GateResult) -> str:
    blocking = [r for r in result.results if not r.passed and r.rule.severity == "blocking"]
    warning = [r for r in result.results if not r.passed and r.rule.severity == "warning"]
    missing = [r for r in result.results if r.missing and r.rule.severity != "info"]
    if not blocking and not warning:
        return "All blocking and warning rules satisfied."
    parts = []
    if blocking:
        names = ", ".join(f"`{r.rule.metric}`" for r in blocking)
        parts.append(f"{len(blocking)} blocking rule(s) violated: {names}.")
    if warning:
        names = ", ".join(f"`{r.rule.metric}`" for r in warning)
        parts.append(f"{len(warning)} warning rule(s) violated: {names}.")
    if missing:
        names = ", ".join(f"`{r.rule.metric}`" for r in missing)
        parts.append(f"Missing evidence (fail-closed): {names}.")
    return " ".join(parts)


def render_markdown_report(
    gate_result: GateResult,
    *,
    subject: str = "",
    workflow: Workflow | None = None,
    generated_at: datetime | None = None,
) -> str:
    """Render a populated quality report (templates/quality-report.md shape)."""
    when = (generated_at or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M UTC")
    title_subject = subject or gate_result.gate
    workflow_name = workflow.name if workflow else "—"

    lines = [
        f"# Quality Report: {title_subject}",
        "",
        f"**Generated:** {when} · **Gate:** {gate_result.gate} · "
        f"**Workflow:** {workflow_name}",
        "",
        "## Verdict",
        "",
        f"# {gate_result.verdict}",
        "",
        _verdict_summary(gate_result),
        "",
        "## Rule-by-rule evidence",
        "",
        "| Metric | Actual | Rule | Severity | Outcome |",
        "|--------|--------|------|----------|---------|",
    ]

    ordered = sorted(gate_result.results, key=lambda r: r.passed)
    for r in ordered:
        actual = "— missing —" if r.missing else f"{r.actual:g}"
        lines.append(
            f"| {r.rule.metric} | {actual} | {r.rule.operator} "
            f"{r.rule.threshold:g} | {r.rule.severity} | {_outcome_cell(r)} |"
        )

    missing = [r for r in gate_result.results if r.missing]
    lines += ["", "## Missing evidence", ""]
    if missing:
        lines += [
            f"- `{r.rule.metric}` ({r.rule.severity}) — metric was never collected"
            for r in missing
        ]
        lines.append("")
        lines.append(
            "Missing evidence is treated as failure on blocking rules (fail-closed), "
            "never inferred."
        )
    else:
        lines.append("None — every rule had collected evidence.")

    lines += ["", "## Human checkpoint", ""]
    if workflow is not None:
        required = workflow.human_checkpoint == "always" or (
            workflow.human_checkpoint == "on_fail" and gate_result.failed
        )
        lines += [
            f"- **Policy:** {workflow.human_checkpoint}",
            f"- **Required for this run:** {'YES' if required else 'no'}",
            "- **Reviewed by / decision:** _to be recorded by the human quality owner_",
        ]
    else:
        lines.append(
            "_No workflow context provided — checkpoint policy unknown. The gate "
            "verdict above stands as computed._"
        )

    lines += [
        "",
        "## Residual risk",
        "",
        "_To be completed by the human quality owner: what this run did NOT cover "
        "and what ships untested if this verdict is acted on._",
        "",
    ]
    return "\n".join(lines)
