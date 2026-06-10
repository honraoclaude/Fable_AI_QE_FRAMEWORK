"""Run history and trend analysis.

Each stored run is one JSON line in an append-only history file (default
.aqef/history.jsonl): human-inspectable, diff-friendly, no database required.
Past records are never mutated — history is evidence, and evidence is immutable.
Trends are computed on read.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from aqef.compare import assess_change
from aqef.config import Rule
from aqef.gates import GateResult
from aqef.report import gate_result_to_dict

DEFAULT_HISTORY = str(Path(".aqef") / "history.jsonl")


@dataclass(frozen=True)
class RunRecord:
    timestamp: str
    gate: str
    verdict: str
    subject: str
    workflow: str | None
    metrics: dict
    rules: list


def append_run(
    path: str | Path,
    gate_result: GateResult,
    metrics: Mapping[str, float],
    *,
    workflow: str | None = None,
    subject: str = "",
    timestamp: datetime | None = None,
) -> RunRecord:
    record = RunRecord(
        timestamp=(timestamp or datetime.now(timezone.utc)).isoformat(
            timespec="seconds"
        ),
        gate=gate_result.gate,
        verdict=gate_result.verdict,
        subject=subject,
        workflow=workflow,
        metrics={str(k): float(v) for k, v in metrics.items()},
        rules=gate_result_to_dict(gate_result)["rules"],
    )
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(record)) + "\n")
    return record


def load_runs(path: str | Path, gate: str | None = None) -> list[RunRecord]:
    file_path = Path(path)
    if not file_path.exists():
        return []
    runs = []
    for line in file_path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line:
            continue
        record = RunRecord(**json.loads(line))
        if gate is None or record.gate == gate:
            runs.append(record)
    runs.sort(key=lambda r: r.timestamp)
    return runs


def last_good_metrics(path: str | Path, gate: str) -> dict | None:
    """Metrics of the most recent PASS run for a gate — the 'last known good'
    baseline. Returns None when no PASS run is recorded."""
    for run in reversed(load_runs(path, gate=gate)):
        if run.verdict == "PASS":
            return dict(run.metrics)
    return None


def compute_trend(runs: list[RunRecord]) -> dict:
    """Verdict distribution and per-metric movement, oldest -> newest."""
    if not runs:
        return {"runs": 0, "verdicts": {}, "metrics": {}}

    verdicts: dict[str, int] = {}
    for run in runs:
        verdicts[run.verdict] = verdicts.get(run.verdict, 0) + 1

    # Direction semantics come from the most recent run's rule definitions.
    rules_by_metric = {
        rule["metric"]: Rule(
            metric=rule["metric"],
            operator=rule["operator"],
            threshold=float(rule["threshold"]),
            severity=rule["severity"],
        )
        for rule in runs[-1].rules
    }

    # Ordered unique metric keys across all runs.
    keys: list[str] = []
    for run in runs:
        for key in run.metrics:
            if key not in keys:
                keys.append(key)

    metrics: dict[str, dict] = {}
    for key in keys:
        series = [run.metrics[key] for run in runs if key in run.metrics]
        first, last = series[0], series[-1]
        delta = last - first
        rule = rules_by_metric.get(key)
        if len(series) < 2:
            assessment = "single data point"
        elif rule is None:
            assessment = "flat" if delta == 0 else "changed"  # metric has no rule
        else:
            assessment = assess_change(rule, first, last)
        metrics[key] = {
            "observations": len(series),
            "first": first,
            "last": last,
            "min": min(series),
            "max": max(series),
            "delta": delta,
            "assessment": assessment,
        }

    return {"runs": len(runs), "verdicts": verdicts, "metrics": metrics}


def format_trend(gate: str, trend: dict) -> str:
    if trend["runs"] == 0:
        return f"No runs recorded for gate {gate!r}."
    verdict_text = ", ".join(
        f"{count}× {verdict}" for verdict, count in sorted(trend["verdicts"].items())
    )
    lines = [
        f"Trend for gate {gate!r} over {trend['runs']} run(s): {verdict_text}",
        "",
        f"{'metric':<32} {'first':>10} {'last':>10} {'delta':>10} assessment",
    ]
    for key, m in trend["metrics"].items():
        lines.append(
            f"{key:<32} {m['first']:>10g} {m['last']:>10g} "
            f"{m['delta']:>+10g} {m['assessment']}"
        )
    return "\n".join(lines)
