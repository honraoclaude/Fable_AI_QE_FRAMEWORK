# Architecture

The framework is organized in five layers. Each layer can be adopted independently, but
they are designed to compose.

```
┌──────────────────────────────────────────────────────────────┐
│ L5  GOVERNANCE      trust tiers, human checkpoints,           │
│                     integrity rules, audit trail              │
├──────────────────────────────────────────────────────────────┤
│ L4  QUALITY GATES   rule engine over metrics →                │
│                     PASS / WARN / FAIL with rationale         │
├──────────────────────────────────────────────────────────────┤
│ L3  ORCHESTRATION   workflows: ordered agent steps,           │
│                     coordination memory, handoff contracts    │
├──────────────────────────────────────────────────────────────┤
│ L2  AGENT FLEET     ten specialized roles (strategy, risk,    │
│                     generation, execution, analysis, gating)  │
├──────────────────────────────────────────────────────────────┤
│ L1  FOUNDATION      the systems under test, test frameworks,  │
│                     scanners, CI/CD, metrics collection       │
└──────────────────────────────────────────────────────────────┘
```

## L1 — Foundation

Everything the agents operate *on*: the codebase, test runners (pytest, Vitest,
Playwright, …), scanners (SAST/DAST), load tools (k6, JMeter), CI/CD, and the metrics
they emit. The framework is deliberately tool-agnostic — agents adapt to the tools in
context rather than mandating a stack.

## L2 — Agent fleet

Ten roles, each with a written spec in [agents/](../agents/) declaring mission, inputs,
outputs, PACT behaviors, guardrails, and handoffs:

| Agent | Role | Default trust tier |
|-------|------|--------------------|
| `qe-orchestrator` | Plans workflows, routes work, escalates to humans | 2 |
| `qe-test-strategist` | Turns requirements + risk into a test strategy | 1 |
| `qe-defect-predictor` | Predicts defect-prone areas from change + history | 2 |
| `qe-test-generator` | Generates risk-targeted tests | 2 |
| `qe-test-executor` | Runs suites, retries, classifies flakes | 3 |
| `qe-coverage-analyzer` | Risk-weighted coverage gap analysis | 3 |
| `qe-security-scanner` | SAST/DAST/dependency + adversarial probing | 2 |
| `qe-performance-tester` | Load profiles, latency/throughput verdicts | 2 |
| `qe-exploratory-tester` | Session-based charters for the unknown unknowns | 1 |
| `qe-quality-gatekeeper` | Evaluates gates, writes the GO/NO-GO rationale | 2 |

**Why ten and not nineteen:** each role earns its place by having a distinct input/output
contract. Start with one or two (typically `qe-test-generator` + `qe-test-executor`) and
add roles as trust and need grow.

## L3 — Orchestration

### Coordination patterns

```
Hierarchical (default): orchestrator → specialists → gatekeeper
Sequential:             predictor → generator → executor → analyzer → gate
Mesh (advanced):        generator ↔ coverage ↔ gatekeeper as peers
```

Hierarchical is the default because it gives one accountable point (the orchestrator)
for escalation and audit. Use mesh only after the fleet has tier-3 trust.

### Coordination memory

Agents share state through namespaced memory rather than private context:

| Namespace | Contents |
|-----------|----------|
| `aqe/test-plan/*` | Strategy and planning decisions |
| `aqe/coverage/*` | Coverage analyses |
| `aqe/quality/*` | Gate results and quality metrics |
| `aqe/learning/*` | Patterns worth reusing across runs |
| `aqe/coordination/*` | Live task state (STATUS → PROGRESS → COMPLETE) |

### Handoff contracts

Every workflow step consumes the metrics/artifacts of prior steps and emits its own.
The reference implementation models this directly: each step returns a metrics dict that
is merged into the workflow context and ultimately evaluated by the gate.

## L4 — Quality gates

A gate is a named set of rules: `metric, operator, threshold, severity`.

- `blocking` — failure (or a missing metric) ⇒ gate **FAIL** (fail closed).
- `warning` — failure (or a missing metric) ⇒ gate **WARN** at best.
- `info` — recorded, never affects the verdict.

Verdict precedence: any blocking failure ⇒ `FAIL`; else any warning failure ⇒ `WARN`;
else `PASS`. Every verdict carries the full rule-by-rule evidence so a NO-GO is always
explainable to a human. See [03-quality-gates.md](03-quality-gates.md).

## L5 — Governance

- **Trust tiers** (1–4) per agent, configured in `framework.yaml`, promoted/demoted on
  measured outcomes.
- **Human checkpoints** per workflow: `always`, `on_fail`, or `never`. Release-affecting
  workflows are `always`.
- **Audit trail**: workflow results (steps, metrics, verdicts, rationale) are durable
  artifacts — the quality report template formalizes this.
- **Integrity rules** from [01-principles.md](01-principles.md) apply at every layer.

## Reference implementation mapping

| Concept | Code |
|---------|------|
| framework.yaml schema + validation | `src/aqef/config.py` |
| Gate rule engine, verdicts, fail-closed semantics | `src/aqef/gates.py` |
| Workflow runner, agent adapters, checkpoints | `src/aqef/orchestrator.py` |
| CI-friendly CLI (`validate`, `gate`, `run`, `list-agents`) | `src/aqef/cli.py` |

The code is intentionally small (~400 lines): it is the *mechanical* part of the
framework. The judgment lives in the agent specs and the humans operating them.
