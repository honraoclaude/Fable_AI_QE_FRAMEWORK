# Quality Report: PR #42

**Generated:** 2026-06-10 06:28 UTC · **Gate:** pr-gate · **Workflow:** pr-quality-gate

## Verdict

# FAIL

2 blocking rule(s) violated: `line_coverage_pct`, `tests_failed`. 2 warning rule(s) violated: `mutation_score_pct`, `flaky_test_rate_pct`. Missing evidence (fail-closed): `mutation_score_pct`.

## Rule-by-rule evidence

| Metric | Actual | Rule | Severity | Outcome |
|--------|--------|------|----------|---------|
| line_coverage_pct | 72 | >= 80 | blocking | **FAIL** |
| tests_failed | 2 | == 0 | blocking | **FAIL** |
| mutation_score_pct | — missing — | >= 60 | warning | **MISSING EVIDENCE** |
| flaky_test_rate_pct | 4 | <= 2 | warning | **FAIL** |
| avg_cyclomatic_complexity | — missing — | <= 10 | info | **MISSING EVIDENCE** |
| new_critical_vulnerabilities | 0 | == 0 | blocking | pass |

## Missing evidence

- `mutation_score_pct` (warning) — metric was never collected
- `avg_cyclomatic_complexity` (info) — metric was never collected

Missing evidence is treated as failure on blocking rules (fail-closed), never inferred.

## Human checkpoint

- **Policy:** on_fail
- **Required for this run:** YES
- **Reviewed by / decision:** _to be recorded by the human quality owner_

## Residual risk

_To be completed by the human quality owner: what this run did NOT cover and what ships untested if this verdict is acted on._
