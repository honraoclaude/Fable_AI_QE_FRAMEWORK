# Metrics & Observability

What the framework measures, why, and the traps to avoid. The cardinal rule from the
principles applies throughout: **measure outcomes, not activity.**

## Outcome metrics (the ones that matter)

| Metric | Definition | Healthy direction |
|--------|------------|-------------------|
| Escaped defect rate | Defects found in production / total defects found | ↓ |
| Defects caught pre-merge | Count attributable to agent-generated tests/scans | ↑ |
| Time to feedback | Commit → first quality signal | ↓ (minutes, not hours) |
| MTTR for test failures | Failure observed → root cause identified | ↓ |
| Human review time saved | Measured, not estimated (sample real reviews) | ↑ |
| Deployment frequency | At constant-or-better escaped-defect rate | ↑ |

The last row is the framework's headline success metric: **10x deployment frequency at
the same or better quality.** Frequency gains at degraded quality are a failure, not a
trade-off.

## DORA alignment

The four DORA keys map cleanly and give you industry benchmarks:

- **Deployment frequency** and **lead time for changes** — the speed pair; agentic QE
  should raise both by removing the quality-verification bottleneck.
- **Change failure rate** and **time to restore** — the stability pair; the gates and
  the defect predictor should hold these flat or better while speed rises.

If speed rises and stability falls, the gates are too loose or the fleet is trusted
beyond its tier. Demote and retune.

## Evidence metrics (what the gates consume)

These are inputs to verdicts, not goals in themselves:

| Metric key (as used in framework.yaml) | Source |
|----------------------------------------|--------|
| `line_coverage_pct`, `branch_coverage_pct` | Coverage tooling (lcov, coverage.py, c8) |
| `mutation_score_pct` | Mutation testing (Stryker, mutmut) |
| `tests_failed`, `regression_pass_rate_pct` | Test executor reports |
| `flaky_test_rate_pct` | Executor retry classification |
| `new_critical_vulnerabilities` | SAST/DAST/dependency scanners |
| `p95_latency_ms`, `error_rate_pct` | Load tests / APM |
| `eval_pass_rate_pct`, `hallucination_rate_pct`, `prompt_injection_failures` | AI eval harness |

**Coverage is necessary but insufficient.** Pair it with mutation score: coverage says
the code ran; mutation score says the assertions would notice if it broke.

## Agent fleet metrics (trust management)

Per agent, per month — these drive tier promotions and demotions:

| Metric | Used for |
|--------|----------|
| Precision of findings (true positives / all findings) | Is the agent worth listening to? |
| Human override rate | Is the agent calibrated to this team? |
| Defects caught that humans missed | Amplification evidence |
| Integrity incidents (fabricated/unverified claims) | Immediate demotion; zero tolerance |

A tier promotion requires: ≥ 1 month at current tier, precision ≥ 90% on blocking-class
findings, zero integrity incidents, and explicit human sign-off.

## Vanity metrics (explicitly rejected)

- Test count, lines of test code, number of agents deployed
- Raw coverage % divorced from risk weighting
- Number of agent runs / tokens consumed / "AI usage" dashboards
- Bug counts as a team performance measure (Goodhart's law guarantees gaming)

## Reporting

- Every workflow run produces a quality report
  ([templates/quality-report.md](../templates/quality-report.md)) with the gate verdict,
  rule-by-rule evidence, and the human checkpoint outcome.
- Trend dashboards track the outcome metrics monthly; gate evidence stays per-run.
- Reports are written for the next reader, not the agent that produced them: state what
  was tested, what was found, what was *not* covered, and what the residual risk is.
