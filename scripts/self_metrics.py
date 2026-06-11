"""Build the framework's own gate metrics from real CI evidence.

Reads the coverage JSON produced by pytest-cov and the JUnit XML produced by
pytest, and emits the metrics file consumed by `aqef gate self-gate`. Only
metrics with actual evidence are emitted — the gate fails closed on anything
missing, which is exactly the behavior the framework prescribes.

Usage:
    python scripts/self_metrics.py --coverage coverage.json \
        --junit junit.xml --out build/self-metrics.json
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def coverage_pct(coverage_json: Path) -> float:
    data = json.loads(coverage_json.read_text(encoding="utf-8-sig"))
    return float(data["totals"]["percent_covered"])


def junit_counts(junit_xml: Path) -> tuple[int, int]:
    """(tests_failed, tests_passed) from a pytest JUnit report."""
    root = ET.parse(junit_xml).getroot()
    suites = root.iter("testsuite") if root.tag == "testsuites" else [root]
    failed = passed = 0
    for suite in suites:
        total = int(suite.get("tests", 0))
        failures = int(suite.get("failures", 0)) + int(suite.get("errors", 0))
        skipped = int(suite.get("skipped", 0))
        failed += failures
        passed += total - failures - skipped
    return failed, passed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage", required=True, help="pytest-cov JSON report")
    parser.add_argument("--junit", required=True, help="pytest JUnit XML report")
    parser.add_argument("--out", required=True, help="metrics JSON to write")
    args = parser.parse_args(argv)

    metrics = {}
    try:
        metrics["line_coverage_pct"] = round(coverage_pct(Path(args.coverage)), 2)
    except (FileNotFoundError, KeyError, json.JSONDecodeError) as exc:
        # Emit nothing for this metric: the gate fails closed, as it should.
        print(f"warning: coverage evidence unavailable ({exc})", file=sys.stderr)
    try:
        failed, passed = junit_counts(Path(args.junit))
        metrics["tests_failed"] = failed
        metrics["tests_passed"] = passed
    except (FileNotFoundError, ET.ParseError) as exc:
        print(f"warning: test result evidence unavailable ({exc})", file=sys.stderr)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}: {metrics}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
