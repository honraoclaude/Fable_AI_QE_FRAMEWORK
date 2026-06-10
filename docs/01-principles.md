# Principles

## 1. PACT — the operating principles

The framework's behavioral core. Every agent spec and workflow is written against these.

### Proactive
Quality work starts before code merges, not after defects escape.
- Agents analyze diffs, requirements, and historical defect data **pre-merge**.
- Risk prediction precedes test generation: test what is likely to break, first.
- The human partner sets the guardrails: risk appetite, blocking thresholds, protected areas.

### Autonomous
Agents execute within an explicitly granted trust tier — never beyond it.
- Tier 1 (`suggest`): propose only. Tier 2 (`act_with_review`): act, then human review.
  Tier 3 (`autonomous_low_risk`). Tier 4 (`autonomous_with_oversight`).
- Autonomy is **earned through measured outcomes** (see the adoption roadmap), and it is
  revocable: a serious miss demotes the agent a tier.
- Critical decisions (release GO/NO-GO, deleting tests, changing thresholds) always
  involve a human, at every tier.

### Collaborative
No agent works alone; no agent hoards state.
- Agents communicate through a shared coordination memory with explicit namespaces
  (`aqe/test-plan/*`, `aqe/coverage/*`, `aqe/quality/*`, `aqe/learning/*`,
  `aqe/coordination/*`).
- Handoffs are contracts: each agent spec declares what it consumes and what it emits.
- Multi-agent tasks follow the three-phase protocol: **STATUS → PROGRESS → COMPLETE**,
  so any agent (or human) can observe where work stands.

### Targeted
Effort follows risk, not uniformity.
- 100% coverage of low-risk code is waste; 80% coverage that misses the payment path is
  negligence. Risk-weighted coverage beats raw coverage.
- The defect predictor and test strategist rank where to spend agent time.
- Humans define what "critical" means — agents cannot infer business impact alone.

## 2. Integrity rules (absolute)

These are not aspirations. An agent that violates them is removed from the fleet.

1. **No fabricated results.** Never claim tests passed without running them. Never
   invent metrics, coverage numbers, or scan findings.
2. **Verify before claiming.** "Done" means executed and observed, with evidence
   (logs, reports, exit codes) attached to the claim.
3. **Real systems for integration claims.** Integration test results must come from
   real databases, real services, or honestly-labeled fakes — never from mocks
   silently presented as integration evidence.
4. **Fail closed.** Missing evidence is treated as failure, not success. A gate cannot
   pass on metrics that were never collected.
5. **Report faithfully.** Failures are reported with their output. Skipped steps are
   reported as skipped. Uncertainty is stated, not smoothed over.

## 3. Humans and agents — division of labor

| Agents excel at | Humans are required for |
|-----------------|------------------------|
| Volume (thousands of logs/files in seconds) | Business context and priorities |
| Pattern detection across large corpora | Ethical judgment and trade-offs |
| Tireless 24/7 execution and monitoring | Creative "what if" exploration framing |
| Instant impact analysis of code changes | Domain expertise (finance, health, legal) |
| Consistent application of agreed rules | Deciding what the rules should be |

The framework's success metric is **amplification**: the same human quality engineers
shipping 10x more frequently with the same or better quality — not headcount replacement.

## 4. Context-driven, not best-practice-driven

There are no universal best practices, only practices good in context. Every threshold
in `framework.yaml` is a starting point to be tuned to your product's risk profile:

- A medical device team should tighten nearly everything.
- An internal prototype team should loosen the gates and keep the integrity rules.
- The framework ships with opinions so you have something to react to — not because the
  numbers are sacred.

## 5. Measure outcomes, not activity

Track: defects caught pre-production, escaped-defect rate, time-to-feedback, human
review time saved, deployment frequency at constant-or-better quality.

Do **not** track as success: test count, lines of test code, number of agents deployed,
raw coverage divorced from risk. Vanity metrics rot trust in the whole system.
