"""Release recommendation mapping and the decide CLI."""

import json
from pathlib import Path

from aqef.cli import main
from aqef.compare import compare_metrics
from aqef.config import Gate, Rule
from aqef.decision import HOLD, PROMOTE, ROLLBACK, recommend
from aqef.gates import evaluate_gate

FRAMEWORK_YAML = Path(__file__).parents[1] / "framework.yaml"
SAMPLE_METRICS = Path(__file__).parents[1] / "examples" / "sample-metrics.json"
FAILING_METRICS = Path(__file__).parents[1] / "examples" / "failing-metrics.json"

COVERAGE = Rule(metric="coverage", operator=">=", threshold=80, severity="blocking")
MUTATION = Rule(metric="mutation", operator=">=", threshold=60, severity="warning")
GATE = Gate(name="g", description="", rules=(COVERAGE, MUTATION))


class TestRecommend:
    def test_fail_maps_to_rollback_with_reasons(self):
        result = evaluate_gate(GATE, {"coverage": 60, "mutation": 70})
        decision = recommend(result)
        assert decision.recommendation == ROLLBACK
        assert any("coverage" in r for r in decision.reasons)

    def test_missing_blocking_evidence_named_in_rollback(self):
        result = evaluate_gate(GATE, {"mutation": 70})
        decision = recommend(result)
        assert decision.recommendation == ROLLBACK
        assert any("no collected evidence" in r for r in decision.reasons)

    def test_warn_maps_to_hold(self):
        result = evaluate_gate(GATE, {"coverage": 90, "mutation": 40})
        decision = recommend(result)
        assert decision.recommendation == HOLD

    def test_pass_with_regression_maps_to_hold(self):
        current = {"coverage": 85, "mutation": 65}
        baseline = {"coverage": 92, "mutation": 65}
        result = evaluate_gate(GATE, current)
        deltas = compare_metrics(GATE, current, baseline)
        decision = recommend(result, deltas)
        assert decision.recommendation == HOLD
        assert any("regression vs baseline" in r for r in decision.reasons)

    def test_clean_pass_maps_to_promote(self):
        current = {"coverage": 92, "mutation": 70}
        baseline = {"coverage": 85, "mutation": 65}
        result = evaluate_gate(GATE, current)
        deltas = compare_metrics(GATE, current, baseline)
        decision = recommend(result, deltas)
        assert decision.recommendation == PROMOTE

    def test_describe_states_advisory_nature(self):
        result = evaluate_gate(GATE, {"coverage": 90, "mutation": 70})
        text = recommend(result).describe()
        assert "PROMOTE" in text
        assert "human quality owner" in text


class TestCli:
    def test_decide_promote_exit_0(self, capsys):
        code = main(
            [
                "decide", "release-readiness",
                "--config", str(FRAMEWORK_YAML),
                "--metrics", str(SAMPLE_METRICS),
            ]
        )
        # sample metrics lack release-gate metrics -> fail closed -> ROLLBACK
        assert code == 1
        assert "ROLLBACK" in capsys.readouterr().out

    def test_decide_pr_workflow_promotes_on_clean_pass(self, capsys):
        code = main(
            [
                "decide", "pr-quality-gate",
                "--config", str(FRAMEWORK_YAML),
                "--metrics", str(SAMPLE_METRICS),
            ]
        )
        assert code == 0
        assert "PROMOTE" in capsys.readouterr().out

    def test_decide_hold_on_baseline_regression(self, tmp_path, capsys):
        baseline = tmp_path / "baseline.json"
        baseline.write_text(
            json.dumps(
                {"line_coverage_pct": 95, "tests_failed": 0,
                 "new_critical_vulnerabilities": 0, "mutation_score_pct": 80,
                 "flaky_test_rate_pct": 0.5, "avg_cyclomatic_complexity": 7}
            ),
            encoding="utf-8",
        )
        code = main(
            [
                "decide", "pr-quality-gate",
                "--config", str(FRAMEWORK_YAML),
                "--metrics", str(SAMPLE_METRICS),
                "--baseline", str(baseline),
            ]
        )
        assert code == 1
        assert "HOLD" in capsys.readouterr().out

    def test_decide_json(self, capsys):
        code = main(
            [
                "decide", "pr-gate",
                "--config", str(FRAMEWORK_YAML),
                "--metrics", str(FAILING_METRICS),
                "--format", "json",
            ]
        )
        assert code == 1
        data = json.loads(capsys.readouterr().out)
        assert data["recommendation"] == "ROLLBACK"
        assert data["advisory"] is True
        assert data["gate"]["verdict"] == "FAIL"
