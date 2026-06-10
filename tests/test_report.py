"""Report generation: JSON serialization, markdown rendering, and CLI."""

import json
from pathlib import Path

import pytest

from aqef.cli import main
from aqef.config import Gate, Rule, load_config
from aqef.gates import evaluate_gate
from aqef.report import (
    gate_result_to_dict,
    render_markdown_report,
    workflow_result_to_dict,
)
from aqef.orchestrator import run_workflow

FRAMEWORK_YAML = Path(__file__).parents[1] / "framework.yaml"
SAMPLE_METRICS = Path(__file__).parents[1] / "examples" / "sample-metrics.json"
FAILING_METRICS = Path(__file__).parents[1] / "examples" / "failing-metrics.json"

COVERAGE = Rule(metric="coverage", operator=">=", threshold=80, severity="blocking")
MUTATION = Rule(metric="mutation", operator=">=", threshold=60, severity="warning")


def small_gate() -> Gate:
    return Gate(name="g", description="", rules=(COVERAGE, MUTATION))


class TestJsonSerialization:
    def test_gate_result_round_trips_through_json(self):
        result = evaluate_gate(small_gate(), {"coverage": 90})
        data = json.loads(json.dumps(gate_result_to_dict(result)))
        assert data["gate"] == "g"
        assert data["verdict"] == "WARN"  # mutation missing -> warn
        by_metric = {r["metric"]: r for r in data["rules"]}
        assert by_metric["coverage"]["passed"] is True
        assert by_metric["mutation"]["missing"] is True
        assert by_metric["mutation"]["actual"] is None

    def test_workflow_result_serializes(self):
        config = load_config(FRAMEWORK_YAML)
        adapters = {
            agent: (lambda action, ctx: {}) for agent in config.agents
        }
        result = run_workflow(config, "pr-quality-gate", adapters)
        data = workflow_result_to_dict(result)
        assert data["workflow"] == "pr-quality-gate"
        assert len(data["steps"]) == 5
        assert data["gate"]["verdict"] == "FAIL"  # no metrics emitted, fail closed
        assert data["human_checkpoint_required"] is True


class TestMarkdownReport:
    def test_contains_verdict_and_evidence(self):
        result = evaluate_gate(small_gate(), {"coverage": 60, "mutation": 70})
        text = render_markdown_report(result, subject="PR #42")
        assert "# FAIL" in text
        assert "PR #42" in text
        assert "| coverage | 60 |" in text
        assert "blocking" in text

    def test_violations_listed_before_passes(self):
        result = evaluate_gate(small_gate(), {"coverage": 60, "mutation": 70})
        text = render_markdown_report(result)
        assert text.index("| coverage |") < text.index("| mutation |")

    def test_missing_evidence_section(self):
        result = evaluate_gate(small_gate(), {"coverage": 90})
        text = render_markdown_report(result)
        assert "MISSING EVIDENCE" in text
        assert "`mutation` (warning)" in text

    def test_no_missing_evidence_states_so(self):
        result = evaluate_gate(small_gate(), {"coverage": 90, "mutation": 70})
        text = render_markdown_report(result)
        assert "None — every rule had collected evidence." in text

    def test_workflow_context_adds_checkpoint_policy(self):
        config = load_config(FRAMEWORK_YAML)
        workflow = config.workflows["release-readiness"]
        result = evaluate_gate(
            config.gates[workflow.gate],
            {
                "line_coverage_pct": 90,
                "open_critical_defects": 0,
                "new_critical_vulnerabilities": 0,
                "p95_latency_ms": 300,
                "error_rate_pct": 0.05,
                "open_high_defects": 0,
            },
        )
        text = render_markdown_report(result, workflow=workflow)
        assert "**Policy:** always" in text
        assert "**Required for this run:** YES" in text

    def test_no_workflow_context_is_honest_about_it(self):
        result = evaluate_gate(small_gate(), {"coverage": 90, "mutation": 70})
        text = render_markdown_report(result)
        assert "checkpoint policy unknown" in text

    def test_human_sections_are_placeholders_not_fabricated(self):
        result = evaluate_gate(small_gate(), {"coverage": 90, "mutation": 70})
        text = render_markdown_report(result)
        assert "Residual risk" in text
        assert "_To be completed by the human quality owner" in text


class TestCli:
    def test_gate_json_format(self, capsys):
        code = main(
            [
                "gate", "pr-gate",
                "--config", str(FRAMEWORK_YAML),
                "--metrics", str(SAMPLE_METRICS),
                "--format", "json",
            ]
        )
        assert code == 0
        data = json.loads(capsys.readouterr().out)
        assert data["verdict"] == "PASS"

    def test_report_for_workflow_to_stdout(self, capsys):
        code = main(
            [
                "report", "pr-quality-gate",
                "--config", str(FRAMEWORK_YAML),
                "--metrics", str(SAMPLE_METRICS),
                "--subject", "PR #7",
            ]
        )
        assert code == 0
        out = capsys.readouterr().out
        assert "# Quality Report: PR #7" in out
        assert "# PASS" in out
        assert "**Policy:** on_fail" in out

    def test_report_fail_exit_code_and_out_file(self, tmp_path, capsys):
        out_file = tmp_path / "report.md"
        code = main(
            [
                "report", "pr-quality-gate",
                "--config", str(FRAMEWORK_YAML),
                "--metrics", str(FAILING_METRICS),
                "--out", str(out_file),
            ]
        )
        assert code == 1
        text = out_file.read_text(encoding="utf-8")
        assert "# FAIL" in text
        assert "**Required for this run:** YES" in text
        assert "verdict: FAIL" in capsys.readouterr().out

    def test_report_for_bare_gate(self, capsys):
        code = main(
            [
                "report", "pr-gate",
                "--config", str(FRAMEWORK_YAML),
                "--metrics", str(SAMPLE_METRICS),
            ]
        )
        assert code == 0
        assert "checkpoint policy unknown" in capsys.readouterr().out

    def test_report_unknown_target(self, capsys):
        code = main(
            [
                "report", "no-such-thing",
                "--config", str(FRAMEWORK_YAML),
                "--metrics", str(SAMPLE_METRICS),
            ]
        )
        assert code == 2
        assert "neither a workflow nor a gate" in capsys.readouterr().err
