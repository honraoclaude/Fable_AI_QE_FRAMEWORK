# Quality Report: <workflow> — <subject (PR #, release, eval cycle)>

> Produced by `qe-quality-gatekeeper` at the end of every workflow run. This is the
> audit artifact: a reader must be able to reconstruct the verdict from this document
> alone. Delete guidance blockquotes when filling in.

**Run ID:** <id> · **Date:** <YYYY-MM-DD HH:MM> · **Workflow:** <name> · **Gate:** <name>

## Verdict

# <PASS / WARN / FAIL>

> One-paragraph summary leading with what failed (or what was closest to failing) and
> why it matters. Not a restatement of the table.

## Rule-by-rule evidence

| Metric | Actual | Rule | Severity | Outcome |
|--------|--------|------|----------|---------|
| line_coverage_pct | 83.4 | >= 80 | blocking | ✅ pass |
| tests_failed | 2 | == 0 | blocking | ❌ **FAIL** |
| mutation_score_pct | — missing — | >= 60 | warning | ⚠️ missing evidence |

> Missing evidence is listed as missing, never inferred. Blocking + missing ⇒ FAIL.

## Step summary

| Step (agent · action) | Outcome | Key output |
|-----------------------|---------|------------|
| qe-defect-predictor · analyze_change_risk | ok | top risk: <module> |
| qe-test-executor · run_tests | ok | 142 passed, 2 failed (classified: regression) |

## Failures & findings detail

> For each blocking failure: what, evidence (logs/repro), suspected cause, owner.

### F1: <title>
- **Evidence:**
- **Reproduction:**
- **Suspected cause:**
- **Owner / next step:**

## Residual risk

> What this run did NOT cover and what ships untested if this verdict is acted on.
> Mandatory for release-readiness runs.

## Human checkpoint record

| Field | Value |
|-------|-------|
| Checkpoint policy | always / on_fail / never |
| Reviewed by | <name> |
| Decision | GO / NO-GO / GO-with-conditions |
| Conditions / waivers | <waived rule + written rationale, or "none"> |
| Date | |

> Waivers never alter the computed verdict above — they are recorded here as a human
> decision layered on top of it.

## Trend note

> One line vs. the previous run of this workflow: better / worse / flat, on what.
