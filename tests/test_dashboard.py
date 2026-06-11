"""Dashboard: data assembly and the local HTTP server."""

import json
import threading
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from aqef.config import load_config
from aqef.dashboard import build_dashboard_data, create_server
from aqef.gates import evaluate_gate
from aqef.history import append_run

FRAMEWORK_YAML = Path(__file__).parents[1] / "framework.yaml"
REGISTER_YAML = Path(__file__).parents[1] / "examples" / "risk-register.yaml"

GOOD = {
    "line_coverage_pct": 90.0,
    "tests_failed": 0,
    "new_critical_vulnerabilities": 0,
    "mutation_score_pct": 72.0,
    "flaky_test_rate_pct": 1.0,
    "avg_cyclomatic_complexity": 7.0,
}
BAD = dict(GOOD, line_coverage_pct=70.0, tests_failed=2)


def seed_history(path, day_metrics):
    config = load_config(FRAMEWORK_YAML)
    gate = config.gates["pr-gate"]
    for day, metrics in day_metrics:
        append_run(
            path,
            evaluate_gate(gate, metrics),
            metrics,
            workflow="pr-quality-gate",
            subject=f"PR #{day}",
            timestamp=datetime(2026, 6, day, tzinfo=timezone.utc),
        )


class TestBuildData:
    def test_full_payload(self, tmp_path):
        history = tmp_path / "h.jsonl"
        seed_history(history, [(1, BAD), (2, GOOD)])
        data = build_dashboard_data(
            str(FRAMEWORK_YAML), str(history), str(REGISTER_YAML)
        )
        assert data["config"]["name"] == "AI Agentic Quality Engineering Framework"
        assert len(data["runs"]) == 2
        assert data["runs"][0]["verdict"] == "FAIL"
        assert data["trends"]["pr-gate"]["runs"] == 2
        assert (
            data["trends"]["pr-gate"]["metrics"]["line_coverage_pct"]["assessment"]
            == "improving"
        )
        assert data["register"]["product"] == "example-commerce-platform"
        assert data["errors"] == []

    def test_missing_sources_degrade_gracefully(self, tmp_path):
        data = build_dashboard_data(
            str(tmp_path / "no.yaml"), str(tmp_path / "no.jsonl"), None
        )
        assert data["config"] is None
        assert data["runs"] == []
        assert data["register"] is None
        assert data["errors"] == []

    def test_coverage_section_when_report_provided(self, tmp_path):
        coverage = tmp_path / "cov.json"
        coverage.write_text(
            json.dumps({
                "files": {
                    "src/payments/capture.py": {
                        "summary": {"percent_covered": 50.0, "num_statements": 300}
                    }
                }
            }),
            encoding="utf-8",
        )
        data = build_dashboard_data(
            None, None, str(REGISTER_YAML), str(coverage)
        )
        rc = data["risk_coverage"]
        assert rc is not None
        assert "R-001" in rc["undercovered_high_risk"]
        top = rc["risk_coverage"][0]
        assert top["risk_id"] == "R-001"
        assert top["coverage_pct"] == 50.0

    def test_coverage_requires_register(self, tmp_path):
        coverage = tmp_path / "cov.json"
        coverage.write_text(json.dumps({"files": {}}), encoding="utf-8")
        data = build_dashboard_data(None, None, None, str(coverage))
        assert data["risk_coverage"] is None

    def test_broken_register_reported_not_swallowed(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("risks: []\n", encoding="utf-8")
        data = build_dashboard_data(None, None, str(bad))
        assert any("register:" in e for e in data["errors"])


class TestServer:
    def test_serves_page_api_and_404(self, tmp_path):
        history = tmp_path / "h.jsonl"
        seed_history(history, [(1, GOOD)])
        server = create_server(
            str(FRAMEWORK_YAML), str(history), str(REGISTER_YAML), port=0
        )
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as resp:
                assert resp.status == 200
                assert b"AQEF quality dashboard" in resp.read()
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/data") as resp:
                payload = json.loads(resp.read())
                assert payload["runs"][0]["subject"] == "PR #1"
                assert payload["register"]["risks"][0]["id"] == "R-003"  # top score
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/nope")
                raise AssertionError("expected 404")
            except urllib.error.HTTPError as exc:
                assert exc.code == 404
        finally:
            server.shutdown()
            server.server_close()

    def test_api_reads_live_data_per_request(self, tmp_path):
        history = tmp_path / "h.jsonl"
        seed_history(history, [(1, GOOD)])
        server = create_server(None, str(history), None, port=0)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/data") as resp:
                assert len(json.loads(resp.read())["runs"]) == 1
            seed_history(history, [(2, BAD)])  # store another run while serving
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/data") as resp:
                assert len(json.loads(resp.read())["runs"]) == 2
        finally:
            server.shutdown()
            server.server_close()
