# Adoption Roadmap

Deploying the full fleet on day one is the canonical failure mode. Trust is built
agent-by-agent, with measured outcomes at each step.

## Phases

| Phase | Duration | Goal | Fleet size |
|-------|----------|------|------------|
| 1. Experiment | Weeks 1–4 | Validate one use case end-to-end | 1 agent |
| 2. Integrate | Months 2–3 | Wire into CI/CD; first enforced gate | 3–4 agents |
| 3. Scale | Months 4–6 | Multiple workflows; risk-targeted depth | 6–8 agents |
| 4. Evolve | Ongoing | Continuous learning; tier-3/4 autonomy where earned | Full fleet |

### Phase 1 — Experiment (one agent, one use case)

Pick the highest-leverage, lowest-risk starting point. For most teams that is
`qe-test-generator` on pull requests:

1. Week 1: deploy the agent at **tier 1** (suggest only). It proposes tests; humans
   review and commit what's good.
2. Weeks 2–3: run it on ~10 PRs. Track: tests accepted vs. rejected, bugs the proposed
   tests caught, review time per PR.
3. Week 4: decide with data. Continue, adjust, or stop. Promotion to tier 2 requires
   the criteria below.

**Do not** enforce any gate in phase 1. Run `pr-gate` in report-only mode to build the
metric baseline you'll need for threshold tuning.

### Phase 2 — Integrate

- Add `qe-test-executor` and `qe-coverage-analyzer`; wire the `pr-quality-gate`
  workflow into CI with the gate **enforced** (blocking rules only — keep warnings
  advisory until the team trusts the signal).
- Add `qe-quality-gatekeeper` to produce the per-PR quality report.
- Establish the coordination memory and the STATUS → PROGRESS → COMPLETE protocol.

### Phase 3 — Scale

- Add `qe-defect-predictor` to make generation risk-targeted (PACT's "T").
- Add `qe-security-scanner` and `qe-performance-tester`; enable `release-readiness`.
- Begin the `regression-cycle` workflow with flake classification.
- Start the fleet metrics review (precision, override rate) as a monthly ritual.

### Phase 4 — Evolve

- Promote proven agents to tier 3 on low-risk repositories.
- Enable `ai-system-evaluation` if you ship AI features.
- Feed `aqe/learning/*` patterns back into agent prompts; retire rules that no longer
  pull their weight.

## Trust tier promotion criteria

An agent moves up one tier only when **all** of these hold:

1. ≥ 1 month of operation at the current tier.
2. Precision ≥ 90% on findings that would block at the next tier.
3. Human override rate trending down across the period.
4. **Zero integrity incidents** (fabricated results, unverified claims) — ever, at any
   tier. One incident demotes to tier 1 and requires re-earning each step.
5. Explicit, recorded sign-off from the human quality owner.

Demotion is cheap and reversible; quietly tolerating a miscalibrated agent is neither.

## Organizational notes

- **Name a human quality owner.** Tier sign-offs, threshold changes, and gate waivers
  need one accountable person, not a committee or — worse — the agents themselves.
- **Keep waivers expensive.** A gate override requires a written rationale attached to
  the run's quality report. Track the waiver rate; rising waivers mean a broken
  threshold or a broken product.
- **Train the team on the trust model.** The most common adoption failure after
  "too many agents at once" is humans rubber-stamping tier-2 reviews. Sampled audits
  of "reviewed" agent output keep the review real.
- **Budget for the boring parts.** Metrics collection and report plumbing (L1/L4) is
  90% of the integration effort. The agents are the easy 10%.

## Exit criteria (when to stop or shrink)

This framework should also say when *not* to use itself:

- The product is a throwaway prototype → keep the integrity rules, drop the gates.
- The team is < 3 engineers → one agent (test generation) is probably the right size.
- Fleet metrics show precision < 70% after two months of tuning → the codebase or test
  stack may not be ready; fix foundations (L1) first.
