"""Gate engine semantics: verdict precedence and fail-closed behavior."""

from aqef.config import Gate, Rule
from aqef.gates import evaluate_gate


def gate(*rules: Rule) -> Gate:
    return Gate(name="g", description="", rules=tuple(rules))


COVERAGE = Rule(metric="coverage", operator=">=", threshold=80, severity="blocking")
MUTATION = Rule(metric="mutation", operator=">=", threshold=60, severity="warning")
COMPLEXITY = Rule(metric="complexity", operator="<=", threshold=10, severity="info")


class TestVerdicts:
    def test_all_pass(self):
        result = evaluate_gate(
            gate(COVERAGE, MUTATION, COMPLEXITY),
            {"coverage": 90, "mutation": 75, "complexity": 5},
        )
        assert result.verdict == "PASS"
        assert not result.failed

    def test_blocking_violation_fails(self):
        result = evaluate_gate(gate(COVERAGE, MUTATION), {"coverage": 60, "mutation": 75})
        assert result.verdict == "FAIL"
        assert result.failed

    def test_warning_violation_warns(self):
        result = evaluate_gate(gate(COVERAGE, MUTATION), {"coverage": 90, "mutation": 40})
        assert result.verdict == "WARN"
        assert not result.failed

    def test_info_violation_never_changes_verdict(self):
        result = evaluate_gate(
            gate(COVERAGE, COMPLEXITY), {"coverage": 90, "complexity": 99}
        )
        assert result.verdict == "PASS"

    def test_fail_beats_warn(self):
        result = evaluate_gate(gate(COVERAGE, MUTATION), {"coverage": 10, "mutation": 10})
        assert result.verdict == "FAIL"


class TestFailClosed:
    def test_missing_blocking_metric_fails(self):
        result = evaluate_gate(gate(COVERAGE), {})
        assert result.verdict == "FAIL"
        assert result.results[0].missing

    def test_missing_warning_metric_warns(self):
        result = evaluate_gate(gate(MUTATION), {})
        assert result.verdict == "WARN"

    def test_missing_info_metric_still_passes(self):
        result = evaluate_gate(gate(COMPLEXITY), {})
        assert result.verdict == "PASS"


class TestBoundaries:
    def test_exact_threshold_passes_gte(self):
        result = evaluate_gate(gate(COVERAGE), {"coverage": 80})
        assert result.verdict == "PASS"

    def test_just_below_threshold_fails(self):
        result = evaluate_gate(gate(COVERAGE), {"coverage": 79.99})
        assert result.verdict == "FAIL"

    def test_equality_operator(self):
        zero_failed = Rule(
            metric="tests_failed", operator="==", threshold=0, severity="blocking"
        )
        assert evaluate_gate(gate(zero_failed), {"tests_failed": 0}).verdict == "PASS"
        assert evaluate_gate(gate(zero_failed), {"tests_failed": 1}).verdict == "FAIL"


class TestRationale:
    def test_rationale_names_every_rule_and_verdict(self):
        result = evaluate_gate(
            gate(COVERAGE, MUTATION), {"coverage": 60, "mutation": 75}
        )
        text = result.rationale()
        assert "FAIL" in text
        assert "coverage" in text
        assert "mutation" in text

    def test_rationale_marks_missing_evidence(self):
        result = evaluate_gate(gate(COVERAGE), {})
        assert "MISSING EVIDENCE" in result.rationale()
