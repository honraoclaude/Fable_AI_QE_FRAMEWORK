# Workflow: Regression Cycle

**Trigger:** scheduled (nightly) or pre-release branch cut
**Gate:** `regression-gate` · **Human checkpoint:** `on_fail`
**Config:** `framework.yaml → workflows.regression-cycle`

Answers one question on a cadence: *does everything that used to work still work?* —
and keeps the answer trustworthy by actively hunting flakes.

## Flow

```
schedule fires
   │
   ▼
qe-test-executor ─────── run_regression_suite
   │   full or impact-selected suite, parallel shards
   ▼
qe-test-executor ─────── retry_and_classify_failures
   │   each failure → regression | flake | environment
   │   regression_pass_rate_pct, flaky_test_rate_pct
   ▼
qe-coverage-analyzer ─── analyze_coverage
   │   regression suite coverage vs. risk map
   ▼
qe-quality-gatekeeper ── evaluate regression-gate
   │
   ├─ PASS → confidence record stored; trend updated
   ├─ WARN → flake debt surfaced to the team backlog
   └─ FAIL → human checkpoint: real regressions with repro commands
```

## Failure classification rules

A failure may only be labeled **flake** when reruns on identical code produce divergent
results. Everything else is:

- **regression** — deterministic failure linked to a change (predictor provides the
  candidate commits)
- **environment** — infra/setup cause identified (and reported as such, not as a pass)

Confirmed flakes generate *quarantine proposals*. Quarantine is a human decision below
executor tier 3, and every quarantined test gets a backlog item — quarantine without
follow-up is silent coverage loss.

## Risk-based test selection

Rerunning everything is the fallback, not the strategy. The product risk register
([examples/risk-register.yaml](../examples/risk-register.yaml)) makes selection
mechanical:

```bash
# Pure risk-based: everything protecting medium+ risks, ranked by score
python -m aqef select-tests --register risk-register.yaml --min-tier medium

# Change-aware: risks whose code areas the diff touches come first, always included
git diff --name-only origin/main... > changed.txt
python -m aqef select-tests --register risk-register.yaml \
  --changed-from changed.txt --min-tier high --format selectors | xargs pytest
```

Selection rules (implemented in `src/aqef/risks.py`):

- Each risk carries likelihood × impact (1–5 each) → score → tier
  (critical ≥ 15, high ≥ 10, medium ≥ 5, low < 5), code `areas` globs, and the
  `tests` selectors that protect it.
- **Impacted risks always run.** A changed file matching a risk's area selects that
  risk's tests first, regardless of tier — a change in low-risk code is still a change.
- Unimpacted risks run when at or above `--min-tier`, ranked by score.
- A change touching a risk area with **no linked tests** triggers a loud warning:
  the change ships unprotected against that risk. `aqef risks` flags high/critical
  risks without tests at any time.
- Humans own the likelihood/impact judgments (see
  [templates/risk-assessment.md](../templates/risk-assessment.md)); agents keep
  `areas` and `tests` in sync with the codebase as it evolves.

## Suite stewardship

The regression cycle is also where the suite itself is maintained:

- **Flake debt:** `flaky_test_rate_pct` above the warning threshold (5%) for two
  consecutive cycles triggers a stabilization charter.
- **Runtime budget:** the `regression_runtime_minutes` info rule tracks creep. When the
  suite outgrows its window, prefer impact-based selection over deleting coverage.
- **Suite-vs-risk drift:** the coverage step compares what the regression suite protects
  against the current risk map; protected-but-dead areas are candidates for pruning,
  hot-but-unprotected areas go to the generator.

## Trend reporting

Each cycle appends to the trend record in `aqe/quality/regression/*`: pass rate, flake
rate, runtime, new quarantines. The monthly fleet review reads this trend — a healthy
regression program shows flat-or-rising pass rate with falling flake rate.
