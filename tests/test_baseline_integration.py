"""Baseline-from-history and baseline sections in rendered reports."""

import json
from datetime import datetime, timezone
from pathlib import Path

from aqef.cli import main
from aqef.compare import compare_metrics
from aqef.config import load_config
from aqef.gates import evaluate_gate
from aqef.history import append_run, last_good_metrics
from aqef.report import render_html_report, render_markdown_report

FRAMEWORK_YAML = Path(__file__).parents[1] / "framework.yaml"
SAMPLE_METRICS = Path(__file__).parents[1] / "examples" / "sample-metrics.json"
FAILING_METRICS = Path(__file__).parents[1] / "examples" / "failing-metrics.json"

GOOD = {
    "line_coverage_pct": 95.0,
    "tests_failed": 0,
    "new_critical_vulnerabilities": 0,
    "mutation_score_pct": 80.0,
    "flaky_test_rate_pct": 0.5,
    "avg_cyclomatic_complexity": 7.0,
}
BAD = {
    "line_coverage_pct": 70.0,
    "tests_failed": 3,
    "new_critical_vulnerabilities": 1,
    "mutation_score_pct": 50.0,
    "flaky_test_rate_pct": 6.0,
    "avg_cyclomatic_complexity": 12.0,
}


def store(history, config, metrics, day):
    gate = config.gates["pr-gate"]
    append_run(
        history,
        evaluate_gate(gate, metrics),
        metrics,
        timestamp=datetime(2026, 6, day, tzinfo=timezone.utc),
    )


class TestLastGoodMetrics:
    def test_returns_most_recent_pass(self, tmp_path):
        config = load_config(FRAMEWORK_YAML)
        history = tmp_path / "h.jsonl"
        earlier_good = dict(GOOD, line_coverage_pct=90.0)
        store(history, config, earlier_good, day=1)   # PASS
        store(history, config, GOOD, day=2)           # PASS (most recent)
        store(history, config, BAD, day=3)            # FAIL
        baseline = last_good_metrics(history, "pr-gate")
        assert baseline["line_coverage_pct"] == 95.0  # day-2 run, not day-1

    def test_none_when_no_pass_recorded(self, tmp_path):
        config = load_config(FRAMEWORK_YAML)
        history = tmp_path / "h.jsonl"
        store(history, config, BAD, day=1)
        assert last_good_metrics(history, "pr-gate") is None
        assert last_good_metrics(tmp_path / "missing.jsonl", "pr-gate") is None


class TestReportBaselineSection:
    def test_markdown_contains_comparison_table(self):
        config = load_config(FRAMEWORK_YAML)
        gate = config.gates["pr-gate"]
        result = evaluate_gate(gate, BAD)
        deltas = compare_metrics(gate, BAD, GOOD)
        text = render_markdown_report(result, deltas=deltas)
        assert "## Baseline comparison" in text
        assert "**worsening**" in text

    def test_markdown_omits_section_without_deltas(self):
        config = load_config(FRAMEWORK_YAML)
        gate = config.gates["pr-gate"]
        result = evaluate_gate(gate, GOOD)
        assert "Baseline comparison" not in render_markdown_report(result)

    def test_html_contains_comparison_table(self):
        config = load_config(FRAMEWORK_YAML)
        gate = config.gates["pr-gate"]
        result = evaluate_gate(gate, BAD)
        deltas = compare_metrics(gate, BAD, GOOD)
        page = render_html_report(result, deltas=deltas)
        assert "<h2>Baseline comparison</h2>" in page
        assert "worsening" in page


class TestCli:
    def test_gate_baseline_from_history(self, tmp_path, capsys):
        history = str(tmp_path / "h.jsonl")
        # First, store a PASS run as the baseline...
        code = main(
            [
                "gate", "pr-gate",
                "--config", str(FRAMEWORK_YAML),
                "--metrics", str(SAMPLE_METRICS),
                "--store", "--history", history,
            ]
        )
        assert code == 0
        capsys.readouterr()
        # ...then a worse run must trip --fail-on-regression against it.
        bad_file = tmp_path / "bad.json"
        bad_file.write_text(json.dumps(BAD), encoding="utf-8")
        code = main(
            [
                "gate", "pr-gate",
                "--config", str(FRAMEWORK_YAML),
                "--metrics", str(bad_file),
                "--baseline-from-history", "--history", history,
                "--fail-on-regression",
            ]
        )
        assert code == 1
        assert "BASELINE REGRESSION" in capsys.readouterr().err

    def test_baseline_from_history_without_pass_run_errors(self, tmp_path, capsys):
        code = main(
            [
                "gate", "pr-gate",
                "--config", str(FRAMEWORK_YAML),
                "--metrics", str(SAMPLE_METRICS),
                "--baseline-from-history",
                "--history", str(tmp_path / "empty.jsonl"),
            ]
        )
        assert code == 2
        assert "no PASS run recorded" in capsys.readouterr().err

    def test_stored_run_cannot_be_its_own_baseline(self, tmp_path, capsys):
        # --store and --baseline-from-history together: the baseline must be
        # resolved BEFORE the current run is appended.
        history = str(tmp_path / "h.jsonl")
        code = main(
            [
                "gate", "pr-gate",
                "--config", str(FRAMEWORK_YAML),
                "--metrics", str(SAMPLE_METRICS),
                "--store", "--history", history,
                "--baseline-from-history",
            ]
        )
        # No prior PASS run exists, so this errors even though the current
        # (passing) run gets stored in other scenarios.
        assert code == 2
        assert "no PASS run recorded" in capsys.readouterr().err

    def test_report_with_baseline_file(self, tmp_path, capsys):
        good_file = tmp_path / "good.json"
        good_file.write_text(json.dumps(GOOD), encoding="utf-8")
        code = main(
            [
                "report", "pr-quality-gate",
                "--config", str(FRAMEWORK_YAML),
                "--metrics", str(SAMPLE_METRICS),
                "--baseline", str(good_file),
            ]
        )
        assert code == 0
        out = capsys.readouterr().out
        assert "## Baseline comparison" in out

    def test_baseline_flags_are_mutually_exclusive(self, capsys):
        try:
            main(
                [
                    "gate", "pr-gate",
                    "--config", str(FRAMEWORK_YAML),
                    "--metrics", str(SAMPLE_METRICS),
                    "--baseline", "x.json",
                    "--baseline-from-history",
                ]
            )
        except SystemExit as exc:
            assert exc.code == 2
        else:
            raise AssertionError("expected argparse to reject the combination")
