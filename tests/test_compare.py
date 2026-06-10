"""Baseline comparison: direction semantics, regression detection, CLI."""

import json
from pathlib import Path

from aqef.cli import main
from aqef.compare import (
    FLAT,
    IMPROVING,
    NOT_COMPARABLE,
    WORSENING,
    assess_change,
    compare_metrics,
    regressions,
)
from aqef.config import Gate, Rule

FRAMEWORK_YAML = Path(__file__).parents[1] / "framework.yaml"
SAMPLE_METRICS = Path(__file__).parents[1] / "examples" / "sample-metrics.json"

COVERAGE = Rule(metric="coverage", operator=">=", threshold=80, severity="blocking")
LATENCY = Rule(metric="latency", operator="<=", threshold=500, severity="warning")
FAILURES = Rule(metric="failures", operator="==", threshold=0, severity="blocking")
COMPLEXITY = Rule(metric="complexity", operator="<=", threshold=10, severity="info")

GATE = Gate(name="g", description="", rules=(COVERAGE, LATENCY, FAILURES, COMPLEXITY))


class TestAssessChange:
    def test_higher_is_better_for_gte(self):
        assert assess_change(COVERAGE, 80, 90) == IMPROVING
        assert assess_change(COVERAGE, 90, 80) == WORSENING

    def test_lower_is_better_for_lte(self):
        assert assess_change(LATENCY, 400, 300) == IMPROVING
        assert assess_change(LATENCY, 300, 400) == WORSENING

    def test_no_change_is_flat(self):
        assert assess_change(COVERAGE, 85, 85) == FLAT

    def test_equality_rule_uses_distance_to_target(self):
        # target is 0: 2 -> 0 closes the distance, 0 -> 2 opens it
        assert assess_change(FAILURES, 2, 0) == IMPROVING
        assert assess_change(FAILURES, 0, 2) == WORSENING

    def test_equality_rule_same_distance_is_flat(self):
        # -5 and 5 are equidistant from target 0
        assert assess_change(FAILURES, -5, 5) == FLAT


class TestCompareMetrics:
    def test_one_delta_per_rule_in_order(self):
        deltas = compare_metrics(
            GATE,
            {"coverage": 85, "latency": 350, "failures": 0, "complexity": 8},
            {"coverage": 82, "latency": 300, "failures": 1, "complexity": 8},
        )
        assert [d.metric for d in deltas] == [
            "coverage", "latency", "failures", "complexity",
        ]
        by_metric = {d.metric: d.assessment for d in deltas}
        assert by_metric["coverage"] == IMPROVING
        assert by_metric["latency"] == WORSENING
        assert by_metric["failures"] == IMPROVING
        assert by_metric["complexity"] == FLAT

    def test_missing_values_are_not_comparable(self):
        deltas = compare_metrics(GATE, {"coverage": 85}, {})
        assert all(
            d.assessment == NOT_COMPARABLE for d in deltas
        )  # baseline empty -> nothing comparable

    def test_regressions_ignore_info_severity(self):
        deltas = compare_metrics(
            GATE,
            {"coverage": 85, "latency": 350, "failures": 0, "complexity": 12},
            {"coverage": 85, "latency": 300, "failures": 0, "complexity": 5},
        )
        regressed = regressions(deltas)
        assert [d.metric for d in regressed] == ["latency"]  # complexity is info


class TestCli:
    def write_metrics(self, tmp_path, name, data):
        path = tmp_path / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return str(path)

    def test_baseline_comparison_in_text_output(self, tmp_path, capsys):
        baseline = self.write_metrics(
            tmp_path, "baseline.json",
            {"line_coverage_pct": 88, "tests_failed": 0,
             "new_critical_vulnerabilities": 0, "mutation_score_pct": 70,
             "flaky_test_rate_pct": 1.0, "avg_cyclomatic_complexity": 7},
        )
        code = main(
            [
                "gate", "pr-gate",
                "--config", str(FRAMEWORK_YAML),
                "--metrics", str(SAMPLE_METRICS),  # coverage 86.2 < baseline 88
                "--baseline", baseline,
            ]
        )
        assert code == 0  # thresholds still pass; no --fail-on-regression
        out = capsys.readouterr().out
        assert "Baseline comparison:" in out
        assert "worsening" in out

    def test_fail_on_regression_blocks_a_passing_gate(self, tmp_path, capsys):
        baseline = self.write_metrics(
            tmp_path, "baseline.json",
            {"line_coverage_pct": 95, "tests_failed": 0,
             "new_critical_vulnerabilities": 0, "mutation_score_pct": 80,
             "flaky_test_rate_pct": 0.5, "avg_cyclomatic_complexity": 7},
        )
        code = main(
            [
                "gate", "pr-gate",
                "--config", str(FRAMEWORK_YAML),
                "--metrics", str(SAMPLE_METRICS),  # PASS on thresholds, worse than baseline
                "--baseline", baseline,
                "--fail-on-regression",
            ]
        )
        assert code == 1
        err = capsys.readouterr().err
        assert "BASELINE REGRESSION" in err
        assert "line_coverage_pct" in err

    def test_improvement_with_fail_on_regression_passes(self, tmp_path, capsys):
        baseline = self.write_metrics(
            tmp_path, "baseline.json",
            {"line_coverage_pct": 81, "tests_failed": 0,
             "new_critical_vulnerabilities": 0, "mutation_score_pct": 61,
             "flaky_test_rate_pct": 1.9, "avg_cyclomatic_complexity": 9},
        )
        code = main(
            [
                "gate", "pr-gate",
                "--config", str(FRAMEWORK_YAML),
                "--metrics", str(SAMPLE_METRICS),
                "--baseline", baseline,
                "--fail-on-regression",
            ]
        )
        assert code == 0

    def test_json_output_includes_baseline_block(self, tmp_path, capsys):
        baseline = self.write_metrics(
            tmp_path, "baseline.json",
            {"line_coverage_pct": 95, "tests_failed": 0,
             "new_critical_vulnerabilities": 0, "mutation_score_pct": 80,
             "flaky_test_rate_pct": 0.5, "avg_cyclomatic_complexity": 7},
        )
        main(
            [
                "gate", "pr-gate",
                "--config", str(FRAMEWORK_YAML),
                "--metrics", str(SAMPLE_METRICS),
                "--baseline", baseline,
                "--format", "json",
            ]
        )
        data = json.loads(capsys.readouterr().out)
        assert "baseline" in data
        assert "line_coverage_pct" in data["baseline"]["regressions"]

    def test_fail_on_regression_requires_baseline(self, capsys):
        code = main(
            [
                "gate", "pr-gate",
                "--config", str(FRAMEWORK_YAML),
                "--metrics", str(SAMPLE_METRICS),
                "--fail-on-regression",
            ]
        )
        assert code == 2
        assert "requires --baseline" in capsys.readouterr().err
