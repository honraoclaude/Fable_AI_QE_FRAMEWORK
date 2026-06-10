# Test Plan: <feature / epic / release>

> Produced by `qe-test-strategist` (tier 1: this is a proposal until a human accepts it).
> Delete the guidance blockquotes when filling in.

**Author:** <agent + human reviewer> · **Date:** <YYYY-MM-DD> · **Status:** draft | accepted

## 1. Scope & objective

> One paragraph: what is being delivered, and what quality question this plan answers.

## 2. Risk summary

> From the risk assessment (templates/risk-assessment.md) and qe-defect-predictor.
> Top 3 risks get disproportionate depth below — show that they do.

| # | Risk area | Likelihood | Impact | Driver (why risky) |
|---|-----------|------------|--------|--------------------|
| 1 | | H/M/L | H/M/L | |
| 2 | | | | |
| 3 | | | | |

## 3. Test approach by level

| Level | Target areas | Techniques | Depth | Owner |
|-------|--------------|------------|-------|-------|
| Unit | | boundary / equivalence / state | | qe-test-generator |
| Integration | | contract / data-flow / error-path | | |
| E2E | | critical user journeys | | |
| Exploratory | | charters (list below) | session-based | qe-exploratory-tester + human |
| Non-functional | | load profile / security scan scope | | |

### Exploratory charters

> One line each: "Explore <area> with <resources> to discover <risk question>."

1.
2.

## 4. AI features (if applicable)

> Eval dimensions and weights for the ai-system-evaluation workflow.

| Dimension | Weight | Rubric ref | Run count |
|-----------|--------|------------|-----------|
| correctness | | eval-rubric.md#... | |
| groundedness | | | |
| safety / injection resistance | | | |

## 5. NOT testing (mandatory)

> A plan without explicit exclusions is incomplete. For each exclusion: what, why,
> and who accepted the risk.

| Excluded | Rationale | Risk accepted by |
|----------|-----------|------------------|
| | | |

## 6. Evidence & gates

- Workflow(s): <pr-quality-gate / release-readiness / ...>
- Gate(s): <pr-gate / release-gate> — thresholds per framework.yaml
- Metrics this plan must produce: <list the metric keys>

## 7. Dependencies & environment

> Test data needs, environment fidelity notes, third-party stubs/contracts.

## 8. Sign-off

| Role | Name | Date | Decision |
|------|------|------|----------|
| Human quality owner | | | accepted / revise |
