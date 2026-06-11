"""Eval datasets: schema validation, composition stats, result scoring, CLI."""

import json
from pathlib import Path

import pytest

from aqef.cli import main
from aqef.evals import (
    EvalError,
    dataset_stats,
    load_dataset,
    load_results,
    score_results,
)

DATASET_YAML = Path(__file__).parents[1] / "examples" / "eval-dataset.yaml"
RESULTS_JSONL = Path(__file__).parents[1] / "examples" / "eval-results.jsonl"


class TestLoadDataset:
    def test_example_dataset_loads(self):
        dataset = load_dataset(DATASET_YAML)
        assert dataset.feature == "support-bot"
        assert set(dataset.dimensions) == {"correctness", "groundedness", "safety"}
        assert dataset.dimensions["safety"].pass_threshold == 5
        assert len(dataset.cases) == 7

    def test_duplicate_case_id_rejected(self, tmp_path):
        path = tmp_path / "d.yaml"
        path.write_text(
            "dimensions: [{name: a}]\n"
            "cases:\n"
            "  - {id: E-1, dimension: a}\n"
            "  - {id: E-1, dimension: a}\n",
            encoding="utf-8",
        )
        with pytest.raises(EvalError, match="duplicate id"):
            load_dataset(path)

    def test_unknown_dimension_rejected(self, tmp_path):
        path = tmp_path / "d.yaml"
        path.write_text(
            "dimensions: [{name: a}]\ncases: [{id: E-1, dimension: ghost}]\n",
            encoding="utf-8",
        )
        with pytest.raises(EvalError, match="unknown dimension"):
            load_dataset(path)

    def test_invalid_source_rejected(self, tmp_path):
        path = tmp_path / "d.yaml"
        path.write_text(
            "dimensions: [{name: a}]\n"
            "cases: [{id: E-1, dimension: a, source: vibes}]\n",
            encoding="utf-8",
        )
        with pytest.raises(EvalError, match="source"):
            load_dataset(path)


class TestStats:
    def test_composition_and_warnings(self):
        stats = dataset_stats(load_dataset(DATASET_YAML))
        assert stats["total_cases"] == 7
        assert stats["per_source"]["production-failure"] == 2
        assert stats["per_source"]["adversarial"] == 2
        # every dimension has < 5 cases -> thin-coverage warnings
        assert any("thin coverage" in w for w in stats["warnings"])

    def test_missing_production_failures_warned(self, tmp_path):
        path = tmp_path / "d.yaml"
        path.write_text(
            "dimensions: [{name: a}]\n"
            "cases: [{id: E-1, dimension: a, source: golden}]\n",
            encoding="utf-8",
        )
        stats = dataset_stats(load_dataset(path))
        assert any("production-failure" in w for w in stats["warnings"])
        assert any("adversarial" in w for w in stats["warnings"])


class TestScoring:
    def test_example_results_score(self):
        dataset = load_dataset(DATASET_YAML)
        results = load_results(RESULTS_JSONL)
        metrics = score_results(dataset, results)
        assert metrics["eval_runs_total"] == 25
        # failing runs: E-002 score 2 (<3 correctness), E-004 score 3
        # (<4 groundedness), E-006 score 4 (<5 safety) -> 22/25 = 88%
        assert metrics["eval_pass_rate_pct"] == 88.0
        assert metrics["per_dimension_pass_rate_pct"]["safety"] == 90.0
        assert metrics["eval_cases_missing_results"] == 0

    def test_missing_cases_surfaced_not_dropped(self):
        dataset = load_dataset(DATASET_YAML)
        results = [{"case_id": "E-001", "score": 5}]
        metrics = score_results(dataset, results)
        assert metrics["eval_cases_missing_results"] == 6
        assert "E-005" in metrics["missing_case_ids"]

    def test_unknown_case_ids_flagged(self):
        dataset = load_dataset(DATASET_YAML)
        metrics = score_results(dataset, [{"case_id": "E-999", "score": 5}])
        assert metrics["unknown_case_ids"] == ["E-999"]
        assert metrics["eval_runs_total"] == 0

    def test_threshold_is_per_dimension(self):
        dataset = load_dataset(DATASET_YAML)
        # score 4 passes correctness (>=3) but fails safety (>=5)
        metrics = score_results(
            dataset,
            [{"case_id": "E-001", "score": 4}, {"case_id": "E-005", "score": 4}],
        )
        assert metrics["per_dimension_pass_rate_pct"]["correctness"] == 100.0
        assert metrics["per_dimension_pass_rate_pct"]["safety"] == 0.0


class TestCli:
    def test_validate_and_stats(self, capsys):
        code = main(["evals", "--dataset", str(DATASET_YAML)])
        assert code == 0
        captured = capsys.readouterr()
        assert "support-bot" in captured.out
        assert "WARNING" in captured.err  # thin coverage

    def test_score_and_emit_gate_metrics(self, tmp_path, capsys):
        out = tmp_path / "metrics.json"
        code = main(
            [
                "evals", "--dataset", str(DATASET_YAML),
                "--results", str(RESULTS_JSONL),
                "--out", str(out),
            ]
        )
        assert code == 0
        gate_metrics = json.loads(out.read_text(encoding="utf-8"))
        assert gate_metrics == {
            "eval_pass_rate_pct": 88.0,
            "eval_cases_missing_results": 0,
        }

    def test_out_requires_results(self, tmp_path, capsys):
        code = main(
            [
                "evals", "--dataset", str(DATASET_YAML),
                "--out", str(tmp_path / "m.json"),
            ]
        )
        assert code == 2
        assert "requires --results" in capsys.readouterr().err

    def test_invalid_dataset_exits_2(self, tmp_path, capsys):
        bad = tmp_path / "bad.yaml"
        bad.write_text("dimensions: []\ncases: []\n", encoding="utf-8")
        code = main(["evals", "--dataset", str(bad)])
        assert code == 2
