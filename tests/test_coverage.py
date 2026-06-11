"""Risk-weighted coverage: format parsing, weighting, gap ranking, CLI."""

import json
from pathlib import Path

import pytest

from aqef.cli import main
from aqef.coverage import (
    CoverageError,
    analyze_risk_coverage,
    load_coverage,
    undercovered,
)
from aqef.risks import Risk, RiskRegister

REGISTER_YAML = Path(__file__).parents[1] / "examples" / "risk-register.yaml"


def make_risk(rid, area, L, I):
    return Risk(
        id=rid, title=rid, description="", areas=(area,),
        likelihood=L, impact=I, tests=(), owner="", review_by="",
    )


REGISTER = RiskRegister(
    product="p",
    risks=(
        make_risk("R-PAY", "src/payments/*", 3, 5),    # critical, 15
        make_risk("R-SEARCH", "src/search/*", 3, 3),   # medium, 9
        make_risk("R-GHOST", "src/legacy/*", 4, 4),    # critical, no files
    ),
)


class TestLoadCoverage:
    def test_coverage_py_format(self, tmp_path):
        report = tmp_path / "cov.json"
        report.write_text(json.dumps({
            "files": {
                "src/payments/capture.py": {
                    "summary": {"percent_covered": 75.0, "num_statements": 200}
                },
            },
            "totals": {"percent_covered": 75.0},
        }), encoding="utf-8")
        cov = load_coverage(report)
        assert cov["src/payments/capture.py"] == (75.0, 200)

    def test_istanbul_json_summary_format(self, tmp_path):
        report = tmp_path / "cov.json"
        report.write_text(json.dumps({
            "total": {"lines": {"pct": 80, "total": 500}},
            "src/search/index.js": {"lines": {"pct": 60.5, "total": 120}},
        }), encoding="utf-8")
        cov = load_coverage(report)
        assert cov == {"src/search/index.js": (60.5, 120)}

    def test_unrecognized_format_rejected(self, tmp_path):
        report = tmp_path / "cov.json"
        report.write_text(json.dumps({"something": "else"}), encoding="utf-8")
        with pytest.raises(CoverageError, match="unrecognized"):
            load_coverage(report)


class TestAnalyze:
    def coverage(self):
        return {
            "src/payments/capture.py": (50.0, 300),   # heavy, badly covered
            "src/payments/refund.py": (90.0, 100),    # light, well covered
            "src/search/index.py": (95.0, 200),
        }

    def test_statement_weighted_average(self):
        results = analyze_risk_coverage(REGISTER, self.coverage())
        pay = next(rc for rc in results if rc.risk.id == "R-PAY")
        # (50*300 + 90*100) / 400 = 60.0 — weighted, not the naive 70
        assert pay.coverage_pct == 60.0
        assert pay.files == ("src/payments/capture.py", "src/payments/refund.py")

    def test_gap_ranking_puts_risky_uncovered_first(self):
        results = analyze_risk_coverage(REGISTER, self.coverage())
        # R-PAY: 15 * 0.40 = 6.0 ; R-SEARCH: 9 * 0.05 = 0.45
        assert results[0].risk.id == "R-PAY"
        assert results[0].gap_score == 6.0

    def test_unmatched_area_is_reported_not_skipped(self):
        results = analyze_risk_coverage(REGISTER, self.coverage())
        ghost = next(rc for rc in results if rc.risk.id == "R-GHOST")
        assert ghost.unmatched
        assert ghost.coverage_pct is None

    def test_undercovered_filters_by_tier_and_threshold(self):
        results = analyze_risk_coverage(REGISTER, self.coverage())
        gaps = undercovered(results, threshold=80)
        assert [rc.risk.id for rc in gaps] == ["R-PAY"]  # search is medium tier


class TestCli:
    def write_coverage(self, tmp_path):
        report = tmp_path / "cov.json"
        report.write_text(json.dumps({
            "files": {
                "src/payments/capture.py": {
                    "summary": {"percent_covered": 50.0, "num_statements": 300}
                },
                "src/orders/state.py": {
                    "summary": {"percent_covered": 95.0, "num_statements": 200}
                },
            }
        }), encoding="utf-8")
        return str(report)

    def test_text_output_and_warning(self, tmp_path, capsys):
        code = main(
            [
                "coverage", "--register", str(REGISTER_YAML),
                "--coverage", self.write_coverage(tmp_path),
            ]
        )
        assert code == 0  # advisory without --enforce
        captured = capsys.readouterr()
        assert "Risk-weighted coverage" in captured.out
        assert "UNDER THRESHOLD" in captured.out
        assert "R-001" in captured.err  # payments at 50% — warned

    def test_enforce_exits_1_on_high_risk_gap(self, tmp_path, capsys):
        code = main(
            [
                "coverage", "--register", str(REGISTER_YAML),
                "--coverage", self.write_coverage(tmp_path),
                "--enforce",
            ]
        )
        assert code == 1

    def test_json_output(self, tmp_path, capsys):
        code = main(
            [
                "coverage", "--register", str(REGISTER_YAML),
                "--coverage", self.write_coverage(tmp_path),
                "--format", "json",
            ]
        )
        assert code == 0
        data = json.loads(capsys.readouterr().out)
        assert "R-001" in data["undercovered_high_risk"]
        top = data["risk_coverage"][0]
        assert top["risk_id"] == "R-001"
        assert top["coverage_pct"] == 50.0

    def test_missing_report_exits_2(self, tmp_path, capsys):
        code = main(
            [
                "coverage", "--register", str(REGISTER_YAML),
                "--coverage", str(tmp_path / "nope.json"),
            ]
        )
        assert code == 2
