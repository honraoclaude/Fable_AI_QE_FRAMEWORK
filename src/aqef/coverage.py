"""Risk-weighted coverage: join a coverage report with the risk register.

Raw coverage percentages treat every line as equally important. They aren't:
80% overall coverage that misses the payment path is worse than 70% that
covers it. This module maps covered files onto the risk register's areas and
ranks the gaps by how much risk sits behind them.

Supported coverage formats (auto-detected):
- coverage.py JSON (`coverage json`): {"files": {path: {"summary": ...}}}
- Istanbul/c8 json-summary: {path: {"lines": {"pct": ..., "total": ...}}}
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from aqef.risks import Risk, RiskRegister


class CoverageError(ValueError):
    """Raised when a coverage report cannot be parsed."""


def load_coverage(path: str | Path) -> dict[str, tuple[float, int]]:
    """Per-file coverage: {file: (percent_covered, statement_count)}."""
    raw = Path(path).read_text(encoding="utf-8-sig")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CoverageError(f"{path}: not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise CoverageError(f"{path}: expected a JSON object")

    if "files" in data and isinstance(data["files"], dict):
        # coverage.py format
        result = {}
        for file_path, info in data["files"].items():
            summary = info.get("summary", {})
            result[file_path] = (
                float(summary.get("percent_covered", 0.0)),
                int(summary.get("num_statements", 0)),
            )
        return result

    # Istanbul/c8 json-summary: file keys at top level, "total" is the rollup
    result = {}
    for file_path, info in data.items():
        if file_path == "total" or not isinstance(info, dict):
            continue
        lines = info.get("lines")
        if isinstance(lines, dict) and "pct" in lines:
            result[file_path] = (float(lines["pct"]), int(lines.get("total", 0)))
    if not result:
        raise CoverageError(
            f"{path}: unrecognized coverage format (expected coverage.py JSON "
            "or Istanbul/c8 json-summary)"
        )
    return result


@dataclass(frozen=True)
class RiskCoverage:
    risk: Risk
    files: tuple[str, ...]
    coverage_pct: float | None  # statement-weighted; None when no files matched
    gap_score: float            # risk score x uncovered fraction

    @property
    def unmatched(self) -> bool:
        return not self.files


def analyze_risk_coverage(
    register: RiskRegister,
    file_coverage: dict[str, tuple[float, int]],
) -> list[RiskCoverage]:
    """One entry per risk, ranked by gap score (most risk-uncovered first).
    A risk whose area globs match no covered files is reported as unmatched —
    stale globs are a finding, not something to skip silently."""
    results = []
    for risk in register.risks:
        matched = [f for f in file_coverage if risk.matches_changed([f])]
        if not matched:
            results.append(
                RiskCoverage(risk=risk, files=(), coverage_pct=None, gap_score=0.0)
            )
            continue
        total_statements = sum(file_coverage[f][1] for f in matched)
        if total_statements > 0:
            pct = (
                sum(file_coverage[f][0] * file_coverage[f][1] for f in matched)
                / total_statements
            )
        else:
            pct = sum(file_coverage[f][0] for f in matched) / len(matched)
        gap = risk.score * (100.0 - pct) / 100.0
        results.append(
            RiskCoverage(
                risk=risk,
                files=tuple(sorted(matched)),
                coverage_pct=round(pct, 2),
                gap_score=round(gap, 2),
            )
        )
    results.sort(key=lambda rc: -rc.gap_score)
    return results


def undercovered(
    results: list[RiskCoverage],
    threshold: float,
    tiers: tuple[str, ...] = ("high", "critical"),
) -> list[RiskCoverage]:
    """High-tier risk areas whose coverage is below the threshold."""
    return [
        rc
        for rc in results
        if rc.risk.tier in tiers
        and rc.coverage_pct is not None
        and rc.coverage_pct < threshold
    ]


def format_risk_coverage(results: list[RiskCoverage], threshold: float) -> str:
    lines = [f"Risk-weighted coverage (threshold {threshold:g}% for high/critical):"]
    for rc in results:
        if rc.unmatched:
            lines.append(
                f"  {rc.risk.id}  ({rc.risk.tier:<8})  NO FILES MATCHED — "
                "are the area globs stale?"
            )
            continue
        flag = (
            "  <-- UNDER THRESHOLD"
            if rc.risk.tier in ("high", "critical") and rc.coverage_pct < threshold
            else ""
        )
        lines.append(
            f"  {rc.risk.id}  ({rc.risk.tier:<8})  coverage {rc.coverage_pct:6.2f}%  "
            f"gap score {rc.gap_score:6.2f}  [{len(rc.files)} file(s)]{flag}"
        )
    return "\n".join(lines)


def risk_coverage_to_dict(results: list[RiskCoverage]) -> dict:
    return {
        "risk_coverage": [
            {
                "risk_id": rc.risk.id,
                "tier": rc.risk.tier,
                "score": rc.risk.score,
                "coverage_pct": rc.coverage_pct,
                "gap_score": rc.gap_score,
                "files": list(rc.files),
                "unmatched": rc.unmatched,
            }
            for rc in results
        ]
    }
