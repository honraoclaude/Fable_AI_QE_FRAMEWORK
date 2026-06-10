# Workflow: Release Readiness

**Trigger:** release candidate cut
**Gate:** `release-gate` · **Human checkpoint:** `always`
**Config:** `framework.yaml → workflows.release-readiness`

The full-spectrum assessment before software reaches users. The gate informs the
release decision; **a human makes it** — this workflow's checkpoint is `always`,
regardless of verdict.

## Flow

```
release candidate
   │
   ▼
qe-test-strategist ───── assess_open_risk
   │   open defects, untested changes, residual risk summary
   ▼
qe-test-executor ─────── run_full_suite
   │   full functional pass on the RC build
   ▼
qe-security-scanner ──── full_scan
   │   SAST + DAST + dependency audit, validated findings
   ▼
qe-performance-tester ── run_load_profile
   │   p95_latency_ms, error_rate_pct vs. budgets
   ▼
qe-exploratory-tester ── targeted_session
   │   chartered sessions on highest-risk release areas
   ▼
qe-quality-gatekeeper ── evaluate release-gate
   │
   ▼
HUMAN CHECKPOINT (always)
   release owner reviews: verdict + rationale + residual risk
   → GO / NO-GO / GO-with-conditions (all recorded)
```

## What "ready" means here

The release gate is stricter than the PR gate by design (coverage 85 vs. 80, plus
non-functional blockers). The deeper difference is qualitative: the strategist's
`assess_open_risk` step forces an explicit **residual risk statement** — what is *not*
covered, what is shipping with known issues, and why that is acceptable (or isn't).

A release decision made without a residual risk statement is a guess with a green
checkmark.

## The human checkpoint

The release owner receives a single quality report
([templates/quality-report.md](../templates/quality-report.md)) containing:

1. Gate verdict with rule-by-rule evidence
2. Residual risk statement from the strategist
3. Exploratory session debriefs (what was probed, what was found)
4. Open defect list with severity and the team's disposition for each
5. Performance trend vs. the previous release

Decision options, all recorded with rationale and signature:

- **GO** — ship.
- **GO with conditions** — ship behind a flag / to a canary cohort / with a documented
  rollback trigger.
- **NO-GO** — blocked items enumerated; workflow re-runs after fixes.

## Anti-patterns this workflow exists to prevent

- Release decided in a meeting from memory, with the quality data scattered.
- "QA signed off" as a ritual phrase with no auditable evidence behind it.
- Non-functional checks (security, performance) done annually instead of per release.
- Residual risk discovered by users instead of stated by the team.
