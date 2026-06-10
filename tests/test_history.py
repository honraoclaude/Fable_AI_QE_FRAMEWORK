"""History store, trend computation, and the history/trend/html CLI surface."""

import json
from datetime import datetime, timezone
from pathlib import Path

from aqef.cli import main
from aqef.config import Gate, Rule, load_config
from aqef.gates import evaluate_gate
from aqef.history import append_run, compute_trend, format_trend, load_runs
from aqef.report import render_html_report

FRAMEWORK_YAML = Path(__file__).parents[1] / "framework.yaml"
SAMPLE_METRICS = Path(__file__).parents[1] / "examples" / "sample-metrics.json"

COVERAGE = Rule(metric="coverage", operator=">=", threshold=80, severity="blocking")
LATENCY = Rule(metric="latency", operator="<=", threshold=500, severity="warning")
GATE = Gate(name="g", description="", rules=(COVERAGE, LATENCY))


def store_run(path, metrics, when):
    result = evaluate_gate(GATE, metrics)
    return append_run(
        path,
        result,
        metrics,
        timestamp=datetime(2026, 6, when, tzinfo=timezone.utc),
    )


class TestStore:
    def test_append_and_load_round_trip(self, tmp_path):
        history = tmp_path / "history.jsonl"
        store_run(history, {"coverage": 82, "latency": 400}, when=1)
        store_run(history, {"coverage": 85, "latency": 350}, when=2)
        runs = load_runs(history)
        assert len(runs) == 2
        assert runs[0].timestamp < runs[1].timestamp  # sorted oldest first
        assert runs[1].metrics["coverage"] == 85
        assert runs[0].verdict == "PASS"

    def test_history_is_append_only_jsonl(self, tmp_path):
        history = tmp_path / "history.jsonl"
        store_run(history, {"coverage": 82, "latency": 400}, when=1)
        store_run(history, {"coverage": 85, "latency": 350}, when=2)
        lines = history.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        assert all(json.loads(line)["gate"] == "g" for line in lines)

    def test_load_filters_by_gate(self, tmp_path):
        history = tmp_path / "history.jsonl"
        store_run(history, {"coverage": 82, "latency": 400}, when=1)
        assert load_runs(history, gate="other") == []
        assert len(load_runs(history, gate="g")) == 1

    def test_missing_file_loads_empty(self, tmp_path):
        assert load_runs(tmp_path / "nope.jsonl") == []


class TestTrend:
    def test_direction_follows_rule_operator(self, tmp_path):
        history = tmp_path / "history.jsonl"
        # coverage (>=, up is better) rises; latency (<=, down is better) rises
        store_run(history, {"coverage": 80, "latency": 300}, when=1)
        store_run(history, {"coverage": 90, "latency": 450}, when=2)
        trend = compute_trend(load_runs(history))
        assert trend["metrics"]["coverage"]["assessment"] == "improving"
        assert trend["metrics"]["latency"]["assessment"] == "worsening"

    def test_flat_and_verdict_counts(self, tmp_path):
        history = tmp_path / "history.jsonl"
        store_run(history, {"coverage": 85, "latency": 300}, when=1)
        store_run(history, {"coverage": 85, "latency": 300}, when=2)
        store_run(history, {"coverage": 60, "latency": 300}, when=3)  # FAIL
        trend = compute_trend(load_runs(history))
        assert trend["runs"] == 3
        assert trend["verdicts"] == {"PASS": 2, "FAIL": 1}
        assert trend["metrics"]["latency"]["assessment"] == "flat"

    def test_single_run_is_honest(self, tmp_path):
        history = tmp_path / "history.jsonl"
        store_run(history, {"coverage": 85, "latency": 300}, when=1)
        trend = compute_trend(load_runs(history))
        assert trend["metrics"]["coverage"]["assessment"] == "single data point"

    def test_format_trend_text(self, tmp_path):
        history = tmp_path / "history.jsonl"
        store_run(history, {"coverage": 80, "latency": 300}, when=1)
        store_run(history, {"coverage": 90, "latency": 250}, when=2)
        text = format_trend("g", compute_trend(load_runs(history)))
        assert "over 2 run(s)" in text
        assert "improving" in text


class TestHtmlReport:
    def test_standalone_html_with_verdict_and_evidence(self):
        result = evaluate_gate(GATE, {"coverage": 60, "latency": 300})
        page = render_html_report(result, subject="PR #9")
        assert page.startswith("<!doctype html>")
        assert "FAIL" in page
        assert "PR #9" in page
        assert "coverage" in page
        assert "MISSING EVIDENCE" not in page  # nothing missing here

    def test_subject_is_escaped(self):
        result = evaluate_gate(GATE, {"coverage": 90, "latency": 300})
        page = render_html_report(result, subject="<script>alert(1)</script>")
        assert "<script>" not in page
        assert "&lt;script&gt;" in page


class TestCli:
    def test_gate_store_then_history_and_trend(self, tmp_path, capsys):
        history = str(tmp_path / "history.jsonl")
        for _ in range(2):
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

        assert main(["history", "--history", history]) == 0
        out = capsys.readouterr().out
        assert out.count("PASS") == 2

        assert main(["trend", "pr-gate", "--history", history]) == 0
        out = capsys.readouterr().out
        assert "over 2 run(s)" in out
        assert "line_coverage_pct" in out

    def test_trend_without_data_fails_loudly(self, tmp_path, capsys):
        code = main(
            ["trend", "pr-gate", "--history", str(tmp_path / "empty.jsonl")]
        )
        assert code == 2
        assert "no runs recorded" in capsys.readouterr().err

    def test_history_without_data_is_not_an_error(self, tmp_path, capsys):
        code = main(["history", "--history", str(tmp_path / "empty.jsonl")])
        assert code == 0
        assert "no runs recorded" in capsys.readouterr().out

    def test_report_html_to_file_with_store(self, tmp_path, capsys):
        history = str(tmp_path / "history.jsonl")
        out_file = tmp_path / "report.html"
        code = main(
            [
                "report", "pr-quality-gate",
                "--config", str(FRAMEWORK_YAML),
                "--metrics", str(SAMPLE_METRICS),
                "--format", "html",
                "--out", str(out_file),
                "--subject", "PR #11",
                "--store", "--history", history,
            ]
        )
        assert code == 0
        page = out_file.read_text(encoding="utf-8")
        assert page.startswith("<!doctype html>")
        assert "PASS" in page
        runs = load_runs(history)
        assert len(runs) == 1
        assert runs[0].workflow == "pr-quality-gate"
        assert runs[0].subject == "PR #11"
