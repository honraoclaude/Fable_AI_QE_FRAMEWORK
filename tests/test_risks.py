"""Risk register: schema, scoring, matching, selection, and CLI."""

import json
from pathlib import Path

import pytest

from aqef.cli import main
from aqef.risks import (
    Risk,
    RiskRegister,
    RiskRegisterError,
    load_register,
    select_tests,
    tier_for_score,
)

REGISTER_YAML = Path(__file__).parents[1] / "examples" / "risk-register.yaml"


def make_risk(**overrides) -> Risk:
    base = dict(
        id="R-X",
        title="t",
        description="",
        areas=("src/payments/*",),
        likelihood=3,
        impact=4,
        tests=("tests/payments/",),
        owner="",
        review_by="",
    )
    base.update(overrides)
    return Risk(**base)


class TestScoringAndTiers:
    def test_score_is_likelihood_times_impact(self):
        assert make_risk(likelihood=3, impact=4).score == 12

    def test_tier_bands(self):
        assert tier_for_score(25) == "critical"
        assert tier_for_score(15) == "critical"
        assert tier_for_score(14) == "high"
        assert tier_for_score(10) == "high"
        assert tier_for_score(9) == "medium"
        assert tier_for_score(5) == "medium"
        assert tier_for_score(4) == "low"
        assert tier_for_score(1) == "low"


class TestRegisterLoading:
    def test_example_register_loads(self):
        register = load_register(REGISTER_YAML)
        assert register.product == "example-commerce-platform"
        assert len(register.risks) == 6
        r1 = register.risks[0]
        assert r1.id == "R-001"
        assert r1.score == 15
        assert r1.tier == "critical"

    def test_duplicate_ids_rejected(self, tmp_path):
        path = tmp_path / "r.yaml"
        path.write_text(
            "risks:\n"
            "  - {id: R-1, title: a, likelihood: 1, impact: 1}\n"
            "  - {id: R-1, title: b, likelihood: 1, impact: 1}\n",
            encoding="utf-8",
        )
        with pytest.raises(RiskRegisterError, match="duplicate id"):
            load_register(path)

    def test_likelihood_out_of_range_rejected(self, tmp_path):
        path = tmp_path / "r.yaml"
        path.write_text(
            "risks:\n  - {id: R-1, title: a, likelihood: 6, impact: 1}\n",
            encoding="utf-8",
        )
        with pytest.raises(RiskRegisterError, match="likelihood"):
            load_register(path)

    def test_untested_high_risks_detected(self):
        register = RiskRegister(
            product="p",
            risks=(
                make_risk(id="R-1", likelihood=4, impact=4, tests=()),   # high, untested
                make_risk(id="R-2", likelihood=1, impact=2, tests=()),   # low, untested
                make_risk(id="R-3", likelihood=4, impact=4),             # high, tested
            ),
        )
        assert [r.id for r in register.untested(min_tier="high")] == ["R-1"]


class TestChangeMatching:
    def test_changed_file_inside_area_matches(self):
        risk = make_risk(areas=("src/payments/*",))
        assert risk.matches_changed(["src/payments/capture.py"])
        assert risk.matches_changed([r"src\payments\capture.py"])  # windows paths
        assert not risk.matches_changed(["src/search/index.py"])


class TestSelection:
    def register(self):
        return RiskRegister(
            product="p",
            risks=(
                make_risk(
                    id="R-LOW", likelihood=1, impact=2,
                    areas=("src/admin/*",), tests=("tests/admin/",),
                ),
                make_risk(
                    id="R-MED", likelihood=2, impact=3,
                    areas=("src/search/*",), tests=("tests/search/",),
                ),
                make_risk(
                    id="R-CRIT", likelihood=4, impact=4,
                    areas=("src/payments/*",), tests=("tests/payments/",),
                ),
            ),
        )

    def test_pure_risk_based_orders_by_score_and_filters_tier(self):
        items = select_tests(self.register(), min_tier="medium")
        assert [i.selector for i in items] == ["tests/payments/", "tests/search/"]
        assert all(not i.impacted for i in items)  # no change context

    def test_impacted_low_risk_is_always_included_and_first(self):
        items = select_tests(
            self.register(),
            changed_files=["src/admin/export.py"],
            min_tier="medium",
        )
        assert items[0].selector == "tests/admin/"   # impacted beats higher scores
        assert items[0].impacted
        assert [i.selector for i in items] == [
            "tests/admin/", "tests/payments/", "tests/search/",
        ]

    def test_duplicate_selectors_deduped_keeping_priority(self):
        register = RiskRegister(
            product="p",
            risks=(
                make_risk(id="A", likelihood=4, impact=4, tests=("tests/shared/",)),
                make_risk(id="B", likelihood=2, impact=3, tests=("tests/shared/",)),
            ),
        )
        items = select_tests(register, min_tier="low")
        assert len(items) == 1
        assert items[0].risk_id == "A"

    def test_limit_caps_selection(self):
        items = select_tests(self.register(), min_tier="low", limit=1)
        assert len(items) == 1
        assert items[0].selector == "tests/payments/"


class TestCli:
    def test_risks_lists_and_warns_on_untested(self, capsys):
        code = main(["risks", "--register", str(REGISTER_YAML)])
        assert code == 0
        captured = capsys.readouterr()
        assert "R-001" in captured.out
        assert "WARNING" not in captured.err or "R-006" not in captured.err
        # R-006 is low tier, so untested warning (high+) must NOT fire for it
        assert "R-006" not in captured.err

    def test_select_tests_with_changed_files(self, capsys):
        code = main(
            [
                "select-tests", "--register", str(REGISTER_YAML),
                "--changed", "src/notifications/dispatch.py",
            ]
        )
        assert code == 0
        out = capsys.readouterr().out
        first_selector_line = next(l for l in out.splitlines() if "<-" in l)
        assert "IMPACTED" in first_selector_line
        assert "tests/notifications/test_dispatch.py" in first_selector_line

    def test_select_tests_selectors_format_pipes_cleanly(self, capsys):
        code = main(
            [
                "select-tests", "--register", str(REGISTER_YAML),
                "--format", "selectors", "--min-tier", "high",
            ]
        )
        assert code == 0
        lines = capsys.readouterr().out.strip().splitlines()
        assert "tests/payments/" in lines
        assert all("<-" not in line for line in lines)

    def test_select_tests_json(self, capsys):
        code = main(
            [
                "select-tests", "--register", str(REGISTER_YAML),
                "--format", "json", "--min-tier", "critical",
            ]
        )
        assert code == 0
        data = json.loads(capsys.readouterr().out)
        assert "tests/payments/" in data["selectors"]
        assert all(item["tier"] == "critical" for item in data["selection"])

    def test_changed_from_file(self, tmp_path, capsys):
        changed = tmp_path / "changed.txt"
        changed.write_text("src/orders/state.py\n\n", encoding="utf-8")
        code = main(
            [
                "select-tests", "--register", str(REGISTER_YAML),
                "--changed-from", str(changed),
                "--min-tier", "critical",
            ]
        )
        assert code == 0
        out = capsys.readouterr().out
        assert "IMPACTED " in out
        assert "tests/orders/test_state_machine.py" in out

    def test_change_touching_untested_risk_warns(self, capsys):
        # R-006 (admin exports) has no linked tests; a change in its area
        # must produce a loud warning even though nothing can be selected.
        code = main(
            [
                "select-tests", "--register", str(REGISTER_YAML),
                "--changed", "src/admin/exports_csv.py",
                "--min-tier", "critical",
            ]
        )
        assert code == 0
        err = capsys.readouterr().err
        assert "R-006" in err
        assert "NO linked tests" in err

    def test_invalid_register_exits_2(self, tmp_path, capsys):
        bad = tmp_path / "bad.yaml"
        bad.write_text("risks: []\n", encoding="utf-8")
        with pytest.raises(SystemExit) as excinfo:
            main(["risks", "--register", str(bad)])
        assert excinfo.value.code == 2
