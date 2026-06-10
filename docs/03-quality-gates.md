# Quality Gates

A quality gate converts collected evidence (metrics) into an explainable decision:
**PASS**, **WARN**, or **FAIL**. Gates are the only place in the framework where a
GO/NO-GO verdict is produced, and they are deliberately boring: declarative rules,
no hidden judgment.

## Rule anatomy

```yaml
- metric: line_coverage_pct   # key looked up in the collected metrics
  operator: ">="              # one of: >=, <=, >, <, ==, !=
  threshold: 80
  severity: blocking          # blocking | warning | info
```

## Verdict semantics

| Situation | blocking | warning | info |
|-----------|----------|---------|------|
| Rule satisfied | contributes to PASS | contributes to PASS | recorded |
| Rule violated | gate **FAIL** | gate **WARN** (at best) | recorded |
| Metric missing | gate **FAIL** (fail closed) | gate **WARN** | recorded as missing |

Precedence: `FAIL` > `WARN` > `PASS`. One blocking violation fails the gate regardless
of how many other rules pass.

**Fail-closed is non-negotiable.** If the coverage report didn't get generated, the
answer is not "assume it's fine." Missing evidence on a blocking rule is a failure —
this single rule prevents the most corrosive failure mode of automated quality systems:
silently passing on absent data.

## Shipped gates

### `pr-gate` — every pull request
Fast, automated, runs on every PR. Blocking: failed tests, coverage < 80%, any new
critical vulnerability. Warning: mutation score < 60%, flake rate > 2%.

### `regression-gate` — scheduled confidence runs
Blocking: regression pass rate < 98%. Warning: flake rate > 5%. Info: runtime budget.

### `release-gate` — release readiness
Stricter than the PR gate, and the associated workflow has `human_checkpoint: always`:
the gate informs the release decision, a human makes it. Adds non-functional blockers
(p95 latency, open critical defects).

### `ai-eval-gate` — AI/LLM systems under test
Testing AI features requires **evals**, not just tests: a deterministic assertion can't
capture "is this answer good?" Blocking: eval pass rate < 90%, hallucination rate > 2%,
any successful prompt injection. Warning: regression vs. the previous baseline. See
[workflows/ai-system-evaluation.md](../workflows/ai-system-evaluation.md).

## Tuning thresholds

The shipped numbers are defensible defaults, not truths. Tune them with this procedure:

1. **Baseline first.** Run the gate in report-only mode for two weeks; collect the
   distribution of each metric.
2. **Set blocking thresholds you can sustain.** A gate the team routinely overrides is
   worse than no gate — it trains everyone to ignore red.
3. **Ratchet, don't leap.** Move coverage 80 → 82 → 85 as the suite improves. Never
   loosen a blocking threshold without a written, dated rationale.
4. **Review quarterly.** Thresholds drift out of relevance as the product changes.

## Baseline comparison (regression vs. last known good)

Absolute thresholds are necessary but not sufficient: a metric can clear its threshold
while sliding toward it. Eval-driven practice (2026 consensus) treats regression below
an established baseline as a blocking signal in its own right.

```bash
python -m aqef gate pr-gate --config framework.yaml \
  --metrics current.json --baseline last-good.json --fail-on-regression
```

- Every gate rule's metric is compared against the baseline snapshot, with direction
  taken from the rule: `>=`/`>` means higher is better, `<=`/`<` lower is better, and
  `==`/`!=` use **distance to target** (e.g. `tests_failed` moving 2 → 0 toward the
  `== 0` target is improving).
- `--fail-on-regression` exits 1 when any **blocking or warning** metric worsened —
  even if every absolute threshold still passes. `info`-severity movement is reported,
  never blocking.
- The comparison appears in text output and in the JSON payload
  (`baseline.deltas`, `baseline.regressions`); metrics absent from either snapshot are
  reported as not comparable, never inferred.
- With run history enabled (`--store`), `--baseline-from-history` uses the most recent
  stored **PASS** run as the baseline automatically — "last known good" without manual
  snapshot management. The baseline is resolved before the current run is stored, so a
  passing run can never become its own baseline.
- `report … --baseline <file>` (or `--baseline-from-history`) adds the comparison
  table to rendered markdown/HTML reports.
- Typical CI wiring: cache the target branch's last metrics snapshot and compare each
  PR against it — see
  [examples/github-actions-quality-gate.yml](../examples/github-actions-quality-gate.yml).

## Release recommendation (PROMOTE / HOLD / ROLLBACK)

`aqef decide <workflow-or-gate>` maps the verdict and baseline movement into an
**advisory** release recommendation with reasons (evidence-driven release management,
arXiv:2603.15676):

| Evidence | Recommendation |
|----------|----------------|
| Gate FAIL (violation or missing blocking evidence) | ROLLBACK |
| Gate WARN | HOLD |
| Gate PASS but regressed vs. baseline | HOLD |
| Gate PASS, no regressions | PROMOTE |

Exit code 0 only on PROMOTE, so CI can block on anything less. Advisory by design:
the framework's release workflows run `human_checkpoint: always` — the recommendation
sharpens the evidence the human decides on; it never ships on its own.

## Adding a gate

1. Define it in `framework.yaml` under `gates:`.
2. Ensure some workflow step (or external CI step) actually emits every metric a
   blocking rule needs — remember fail-closed.
3. Validate: `python -m aqef validate framework.yaml`.
4. Wire it into CI: `python -m aqef gate <name> --config framework.yaml --metrics m.json`
   (exit code 1 on FAIL).

## Anti-patterns

- **Gate theater**: gates whose failures are routinely waived. Fix the threshold or fix
  the product; don't normalize overrides.
- **Single-metric worship**: 100% coverage with assertion-free tests passes a naive
  gate. Pair coverage with mutation score.
- **Gates without rationale**: a bare FAIL teaches nothing. The gatekeeper agent must
  attach the rule-by-rule evidence and a human-readable summary.
- **Per-team threshold forks without history**: if two teams need different bars,
  define two gates with different names — don't quietly edit shared ones.
