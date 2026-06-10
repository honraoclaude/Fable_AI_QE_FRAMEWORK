"""Workflow orchestration against the shipped framework.yaml."""

from pathlib import Path

import pytest

from aqef.config import load_config
from aqef.orchestrator import run_workflow

FRAMEWORK_YAML = Path(__file__).parents[1] / "framework.yaml"

PASSING_PR_METRICS = {
    "line_coverage_pct": 86.2,
    "tests_failed": 0,
    "new_critical_vulnerabilities": 0,
    "mutation_score_pct": 67.5,
    "flaky_test_rate_pct": 1.1,
    "avg_cyclomatic_complexity": 7.8,
}


def make_adapters(emissions: dict[str, dict[str, float]]):
    """Stub adapters: each agent emits a fixed metrics dict regardless of action."""
    return {
        agent: (lambda action, ctx, m=metrics: m)
        for agent, metrics in emissions.items()
    }


@pytest.fixture(scope="module")
def config():
    return load_config(FRAMEWORK_YAML)


class TestPrWorkflow:
    def test_passing_run(self, config):
        adapters = make_adapters(
            {
                "qe-defect-predictor": {},
                "qe-test-generator": {},
                "qe-test-executor": {
                    "tests_failed": 0,
                    "flaky_test_rate_pct": 1.1,
                    "mutation_score_pct": 67.5,
                },
                "qe-coverage-analyzer": {
                    "line_coverage_pct": 86.2,
                    "avg_cyclomatic_complexity": 7.8,
                },
                "qe-security-scanner": {"new_critical_vulnerabilities": 0},
            }
        )
        result = run_workflow(config, "pr-quality-gate", adapters)
        assert result.gate_result.verdict == "PASS"
        assert not result.human_checkpoint_required  # on_fail + PASS
        assert all(step.ok for step in result.steps)

    def test_failing_run_requires_checkpoint(self, config):
        adapters = make_adapters(
            {
                "qe-defect-predictor": {},
                "qe-test-generator": {},
                "qe-test-executor": {"tests_failed": 3, "flaky_test_rate_pct": 1.0},
                "qe-coverage-analyzer": {"line_coverage_pct": 86.2},
                "qe-security-scanner": {"new_critical_vulnerabilities": 0},
            }
        )
        result = run_workflow(config, "pr-quality-gate", adapters)
        assert result.gate_result.verdict == "FAIL"
        assert result.human_checkpoint_required

    def test_missing_adapter_fails_closed(self, config):
        # No security scanner adapter -> new_critical_vulnerabilities never emitted
        adapters = make_adapters(
            {
                "qe-defect-predictor": {},
                "qe-test-generator": {},
                "qe-test-executor": {"tests_failed": 0, "flaky_test_rate_pct": 1.0},
                "qe-coverage-analyzer": {"line_coverage_pct": 86.2},
            }
        )
        result = run_workflow(config, "pr-quality-gate", adapters)
        assert result.gate_result.verdict == "FAIL"
        scanner_step = next(
            s for s in result.steps if s.agent == "qe-security-scanner"
        )
        assert not scanner_step.ok

    def test_crashing_adapter_is_recorded_not_fatal(self, config):
        def boom(action, ctx):
            raise RuntimeError("scanner exploded")

        adapters = make_adapters(
            {
                "qe-defect-predictor": {},
                "qe-test-generator": {},
                "qe-test-executor": {"tests_failed": 0, "flaky_test_rate_pct": 1.0},
                "qe-coverage-analyzer": {"line_coverage_pct": 86.2},
            }
        )
        adapters["qe-security-scanner"] = boom
        result = run_workflow(config, "pr-quality-gate", adapters)
        scanner_step = next(s for s in result.steps if s.agent == "qe-security-scanner")
        assert "scanner exploded" in scanner_step.error
        assert result.gate_result.verdict == "FAIL"  # missing evidence, fail closed


class TestCheckpointPolicy:
    def test_release_readiness_always_requires_checkpoint(self, config):
        passing_release_metrics = {
            "line_coverage_pct": 90,
            "open_critical_defects": 0,
            "new_critical_vulnerabilities": 0,
            "p95_latency_ms": 320,
            "error_rate_pct": 0.05,
            "open_high_defects": 1,
        }
        adapters = make_adapters(
            {
                "qe-test-strategist": {},
                "qe-test-executor": {},
                "qe-security-scanner": {},
                "qe-performance-tester": {},
                "qe-exploratory-tester": {},
            }
        )
        result = run_workflow(
            config, "release-readiness", adapters, initial_metrics=passing_release_metrics
        )
        assert result.gate_result.verdict == "PASS"
        assert result.human_checkpoint_required  # always, even on PASS


class TestErrors:
    def test_unknown_workflow(self, config):
        with pytest.raises(KeyError, match="unknown workflow"):
            run_workflow(config, "no-such-workflow", {})


class TestSummary:
    def test_summary_is_auditable(self, config):
        adapters = make_adapters(
            {
                "qe-defect-predictor": {},
                "qe-test-generator": {},
                "qe-test-executor": dict(
                    tests_failed=0, flaky_test_rate_pct=1.0, mutation_score_pct=70
                ),
                "qe-coverage-analyzer": dict(
                    line_coverage_pct=85, avg_cyclomatic_complexity=6
                ),
                "qe-security-scanner": dict(new_critical_vulnerabilities=0),
            }
        )
        text = run_workflow(config, "pr-quality-gate", adapters).summary()
        assert "pr-quality-gate" in text
        assert "Gate 'pr-gate'" in text
        assert "Human checkpoint" in text
