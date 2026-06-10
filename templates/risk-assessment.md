# Risk Assessment: <feature / release / system>

> Input to the test strategist and the defect predictor. Humans own business impact;
> agents contribute the technical evidence columns. Delete guidance when filling in.

**Date:** <YYYY-MM-DD> · **Assessed by:** <humans + agents> · **Review due:** <date>

## 1. Risk register

> Score = Likelihood (1–5) × Impact (1–5). Anything ≥ 15 must appear in the test plan's
> top-depth tier; anything ≤ 4 may be explicitly excluded.

| # | Risk | L | I | Score | Technical evidence (agent) | Business impact (human) |
|---|------|---|---|-------|----------------------------|--------------------------|
| 1 | | | | | change freq, complexity, defect history | |
| 2 | | | | | | |

## 2. Technical risk signals (qe-defect-predictor)

> Auto-populated factors — keep the evidence, not just the score.

| Module / area | Change freq (90d) | Complexity | Past defects | Fan-in | Risk rank |
|---------------|-------------------|------------|--------------|--------|-----------|
| | | | | | |

## 3. Quality-attribute risks

> Beyond functional: which non-functional attributes are at stake here?

| Attribute | At risk? | Why | Covered by |
|-----------|----------|-----|------------|
| Security | | | qe-security-scanner scope |
| Performance | | | load profile |
| Reliability / resilience | | | chaos/failover tests |
| Data integrity | | | migration/DB tests |
| Compliance / privacy | | | compliance checklist |
| Accessibility | | | a11y scan |

## 4. AI-specific risks (if applicable)

| Risk | Present? | Mitigation / eval dimension |
|------|----------|------------------------------|
| Hallucination on domain facts | | groundedness evals |
| Prompt injection (direct/indirect) | | adversarial_probe |
| Eval-set overfitting | | held-out set rotation |
| Cost/latency regression | | cost + latency dimensions |
| Judge drift (LLM-as-judge) | | judge agreement sampling |

## 5. Assumptions & unknowns

> Every assumption is a risk wearing a disguise. List what is being assumed true and
> what would change this assessment if false.

1.
2.

## 6. Risk appetite statement (human)

> The human quality owner's line: what classes of failure are acceptable for this
> release, and what are never acceptable. The gates encode this; write it in words too.
