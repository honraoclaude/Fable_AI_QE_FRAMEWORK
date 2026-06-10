# Workflow: PR Quality Gate

**Trigger:** pull request opened or updated
**Gate:** `pr-gate` · **Human checkpoint:** `on_fail`
**Config:** `framework.yaml → workflows.pr-quality-gate`

The everyday workhorse: every PR gets a risk-targeted quality pipeline that finishes in
minutes and ends in an explainable verdict.

## Flow

```
PR event
   │
   ▼
qe-defect-predictor ──── analyze_change_risk
   │   ranked risk list (files × risk factors)
   ▼
qe-test-generator ────── generate_targeted_tests
   │   new tests, executed once, idiomatic to the suite
   ▼
qe-test-executor ─────── run_tests
   │   tests_failed, flaky_test_rate_pct, classified failures
   ▼
qe-coverage-analyzer ─── analyze_coverage
   │   line_coverage_pct (+delta vs base), risk-weighted gaps
   ▼
qe-security-scanner ──── scan_diff
   │   new_critical_vulnerabilities, validated findings
   ▼
qe-quality-gatekeeper ── evaluate pr-gate
   │
   ├─ PASS → merge unblocked; quality report attached to PR
   ├─ WARN → merge unblocked; warnings posted as PR review comments
   └─ FAIL → merge blocked; human checkpoint fires with the rationale
```

## Step contracts

| Step | Consumes | Emits (metric keys) |
|------|----------|---------------------|
| `analyze_change_risk` | diff, git history | risk ranking (artifact) |
| `generate_targeted_tests` | risk ranking, strategy | tests (artifact), generation stats |
| `run_tests` | suite incl. new tests | `tests_failed`, `flaky_test_rate_pct` |
| `analyze_coverage` | run data, risk weights | `line_coverage_pct`, gap list |
| `scan_diff` | diff, manifests | `new_critical_vulnerabilities` |

## Operating notes

- **Time budget:** target < 10 minutes end-to-end. If the budget is exceeded, the
  orchestrator drops `info`-level analysis first — never blocking evidence.
- **Generated tests on a failing PR:** if generated tests fail, that is signal, not
  noise. The executor classifies; a deterministic failure on changed code is exactly
  what the pipeline exists to catch.
- **FAIL handling:** the checkpoint presents the gatekeeper's rule-by-rule rationale.
  The human either fixes, or records a waiver (with written reason) in the quality
  report. Waivers are tracked; the gate result itself is never edited.
- **Report-only mode:** during adoption phase 1–2, run this workflow with the gate
  non-enforcing to build the metric baseline (see docs/05-adoption-roadmap.md).

## CI integration

```bash
# after metrics collection steps:
python -m aqef gate pr-gate --config framework.yaml --metrics build/metrics.json
# exit 0 = PASS/WARN, exit 1 = FAIL → fails the CI job
```
