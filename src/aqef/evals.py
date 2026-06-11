"""Eval datasets: golden cases for AI features, and scoring into gate metrics.

Testing AI systems runs on evals, not assertions (see
workflows/ai-system-evaluation.md). This module makes the dataset a validated,
versionable artifact and turns raw scoring results into the metric keys the
ai-eval-gate consumes — with the framework's fail-closed posture: cases that
were never scored are reported as missing evidence, not silently dropped.

Dataset shape (YAML):
    version: "1.0"
    feature: support-bot
    dimensions:
      - name: correctness
        weight: 3
        rubric: templates/eval-rubric.md
        pass_threshold: 3        # rubric score (1-5) required to pass a run
        runs_per_case: 3         # non-determinism: single runs are anecdotes
    cases:
      - id: E-001
        dimension: correctness
        input: "..."
        expected: "..."          # or rubric anchor notes
        source: production-failure   # golden | production-failure | adversarial | edge
        tags: [refunds]

Results shape (JSONL, one object per scored run):
    {"case_id": "E-001", "score": 4}
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import yaml

VALID_SOURCES = {"golden", "production-failure", "adversarial", "edge"}


class EvalError(ValueError):
    """Raised when an eval dataset or results file is invalid."""


@dataclass(frozen=True)
class Dimension:
    name: str
    weight: int
    rubric: str
    pass_threshold: int
    runs_per_case: int


@dataclass(frozen=True)
class EvalCase:
    id: str
    dimension: str
    input: str
    expected: str
    source: str
    tags: tuple[str, ...]


@dataclass(frozen=True)
class EvalDataset:
    feature: str
    dimensions: dict[str, Dimension]
    cases: tuple[EvalCase, ...]


def load_dataset(path: str | Path) -> EvalDataset:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise EvalError(f"{path}: top level must be a mapping")

    dims_raw = data.get("dimensions")
    if not isinstance(dims_raw, list) or not dims_raw:
        raise EvalError(f"{path}: must define a non-empty 'dimensions' list")
    dimensions: dict[str, Dimension] = {}
    for i, entry in enumerate(dims_raw):
        where = f"dimension #{i + 1}"
        name = entry.get("name") if isinstance(entry, dict) else None
        if not name:
            raise EvalError(f"{where}: 'name' is required")
        if name in dimensions:
            raise EvalError(f"{where}: duplicate dimension {name!r}")
        threshold = entry.get("pass_threshold", 3)
        if not isinstance(threshold, int) or not 1 <= threshold <= 5:
            raise EvalError(f"dimension {name!r}: pass_threshold must be 1-5")
        runs = entry.get("runs_per_case", 1)
        if not isinstance(runs, int) or runs < 1:
            raise EvalError(f"dimension {name!r}: runs_per_case must be >= 1")
        dimensions[name] = Dimension(
            name=name,
            weight=int(entry.get("weight", 1)),
            rubric=str(entry.get("rubric", "")),
            pass_threshold=threshold,
            runs_per_case=runs,
        )

    cases_raw = data.get("cases")
    if not isinstance(cases_raw, list) or not cases_raw:
        raise EvalError(f"{path}: must define a non-empty 'cases' list")
    cases = []
    seen: set[str] = set()
    for i, entry in enumerate(cases_raw):
        where = f"case #{i + 1}"
        if not isinstance(entry, dict):
            raise EvalError(f"{where}: must be a mapping")
        case_id = entry.get("id")
        if not case_id:
            raise EvalError(f"{where}: 'id' is required")
        if case_id in seen:
            raise EvalError(f"{where}: duplicate id {case_id!r}")
        seen.add(case_id)
        dimension = entry.get("dimension")
        if dimension not in dimensions:
            raise EvalError(
                f"case {case_id!r}: unknown dimension {dimension!r} "
                f"(defined: {sorted(dimensions)})"
            )
        source = entry.get("source", "golden")
        if source not in VALID_SOURCES:
            raise EvalError(
                f"case {case_id!r}: source {source!r} not in {sorted(VALID_SOURCES)}"
            )
        cases.append(
            EvalCase(
                id=str(case_id),
                dimension=str(dimension),
                input=str(entry.get("input", "")),
                expected=str(entry.get("expected", "")),
                source=str(source),
                tags=tuple(str(t) for t in entry.get("tags", [])),
            )
        )

    return EvalDataset(
        feature=str(data.get("feature", "unnamed")),
        dimensions=dimensions,
        cases=tuple(cases),
    )


def dataset_stats(dataset: EvalDataset) -> dict:
    """Composition stats and hygiene warnings for the dataset."""
    per_dimension: dict[str, int] = {name: 0 for name in dataset.dimensions}
    per_source: dict[str, int] = {}
    for case in dataset.cases:
        per_dimension[case.dimension] += 1
        per_source[case.source] = per_source.get(case.source, 0) + 1

    warnings = []
    for name, count in per_dimension.items():
        if count < 5:
            warnings.append(
                f"dimension '{name}' has only {count} case(s) — thin coverage "
                "makes pass rates noisy"
            )
    if per_source.get("production-failure", 0) == 0:
        warnings.append(
            "no production-failure cases — golden sets built only from synthetic "
            "examples drift from reality; distill real failures into cases"
        )
    if per_source.get("adversarial", 0) == 0:
        warnings.append(
            "no adversarial cases — prompt injection and jailbreak resistance "
            "are untested"
        )

    return {
        "feature": dataset.feature,
        "total_cases": len(dataset.cases),
        "per_dimension": per_dimension,
        "per_source": per_source,
        "warnings": warnings,
    }


def load_results(path: str | Path) -> list[dict]:
    """JSONL of {"case_id": ..., "score": 1-5}, one line per scored run."""
    results = []
    for line_number, line in enumerate(
        Path(path).read_text(encoding="utf-8-sig").splitlines(), start=1
    ):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvalError(f"{path}:{line_number}: not valid JSON: {exc}") from exc
        if not isinstance(entry, dict) or "case_id" not in entry or "score" not in entry:
            raise EvalError(
                f"{path}:{line_number}: each line needs 'case_id' and 'score'"
            )
        results.append(entry)
    return results


def score_results(dataset: EvalDataset, results: list[dict]) -> dict:
    """Aggregate scored runs into gate-ready metrics.

    A run passes when its score meets its dimension's pass_threshold.
    eval_pass_rate_pct is run-level across all scored runs. Cases with no
    results and unknown case ids are surfaced — wire
    `eval_cases_missing_results == 0` as a blocking rule to stay fail-closed.
    """
    known_ids = {case.id: case for case in dataset.cases}
    unknown_ids = sorted({r["case_id"] for r in results} - set(known_ids))

    runs_total = 0
    runs_passed = 0
    per_dimension: dict[str, dict[str, int]] = {
        name: {"runs": 0, "passed": 0} for name in dataset.dimensions
    }
    scored_cases: set[str] = set()
    for entry in results:
        case = known_ids.get(entry["case_id"])
        if case is None:
            continue
        scored_cases.add(case.id)
        dim = dataset.dimensions[case.dimension]
        runs_total += 1
        per_dimension[case.dimension]["runs"] += 1
        if float(entry["score"]) >= dim.pass_threshold:
            runs_passed += 1
            per_dimension[case.dimension]["passed"] += 1

    missing = sorted(set(known_ids) - scored_cases)
    pass_rate = round(100.0 * runs_passed / runs_total, 2) if runs_total else 0.0

    dimension_rates = {
        name: (
            round(100.0 * counts["passed"] / counts["runs"], 2)
            if counts["runs"]
            else None
        )
        for name, counts in per_dimension.items()
    }

    return {
        "eval_pass_rate_pct": pass_rate,
        "eval_runs_total": runs_total,
        "eval_cases_missing_results": len(missing),
        "missing_case_ids": missing,
        "unknown_case_ids": unknown_ids,
        "per_dimension_pass_rate_pct": dimension_rates,
    }
