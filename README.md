# AI Agentic Quality Engineering Framework (AQEF)

A framework for engineering quality with AI agents: a methodology grounded in **PACT**
(Proactive, Autonomous, Collaborative, Targeted), a fleet of ten specialized QE agent
roles, machine-enforceable quality gates, and a small tested Python reference
implementation that turns the configuration into GO/NO-GO decisions.

> Agents amplify human quality expertise — they do not replace it. Every part of this
> framework assumes a human partner sets the guardrails and owns the critical decisions.

---

## What's in the box

| Path | Contents |
|------|----------|
| [framework.yaml](framework.yaml) | Machine-readable definition of the fleet, quality gates, workflows, and trust model |
| [docs/](docs/) | Methodology: principles, architecture, quality gates, metrics, adoption roadmap |
| [agents/](agents/) | Ten agent role specifications (Claude Code–compatible frontmatter, deployable to `.claude/agents/`) |
| [workflows/](workflows/) | Four end-to-end quality workflows (PR gate, regression, release readiness, AI system evaluation) |
| [templates/](templates/) | Working artifacts: test plan, quality report, risk assessment, eval rubric |
| [src/aqef/](src/aqef/) | Reference implementation: config loader/validator, gate engine, workflow orchestrator, CLI |
| [tests/](tests/) | pytest suite for the reference implementation |
| [examples/](examples/) | Sample metrics payload for offline gate evaluation |

## Quickstart

```bash
cd src

# Validate the framework configuration
python -m aqef validate ../framework.yaml

# List the agent fleet
python -m aqef list-agents --config ../framework.yaml

# Evaluate a quality gate against collected metrics (offline, CI-friendly)
python -m aqef gate pr-gate --config ../framework.yaml --metrics ../examples/sample-metrics.json

# Run the test suite
python -m pytest ../tests -q
```

The `gate` command exits `0` on PASS/WARN and `1` on FAIL, so it can be dropped straight
into a CI pipeline as a blocking step.

## The 30-second model

```
                    ┌─────────────────────────────┐
                    │   Human Quality Engineer     │  sets guardrails, owns
                    │   (guardrails & judgment)    │  critical decisions
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │       qe-orchestrator        │  plans, routes, escalates
                    └──────────────┬──────────────┘
          ┌────────────┬───────────┼────────────┬─────────────┐
          ▼            ▼           ▼            ▼             ▼
   test-strategist  test-gen  test-executor  coverage    security /
   defect-predictor            exploratory   analyzer    performance
          └────────────┴───────────┼────────────┴─────────────┘
                                   ▼
                    ┌─────────────────────────────┐
                    │     qe-quality-gatekeeper    │  evaluates gates →
                    │   (PASS / WARN / FAIL)       │  GO / NO-GO + rationale
                    └─────────────────────────────┘
```

Every workflow ends at a **quality gate**: a set of metric rules with `blocking`,
`warning`, or `info` severity. Blocking rules fail closed — a missing metric is a
failure, never a silent pass.

## PACT in one table

| Principle | Agent behavior | Human role |
|-----------|----------------|------------|
| **P**roactive | Analyze before merge; predict risk before defects escape | Set guardrails and risk appetite |
| **A**utonomous | Execute, retry, stabilize within the granted trust tier | Review per the trust model |
| **C**ollaborative | Share state through the coordination memory; hand off cleanly | Provide business context |
| **T**argeted | Spend effort where risk concentrates, not uniformly | Define what "critical" means here |

See [docs/01-principles.md](docs/01-principles.md) for the full treatment, including the
integrity rules (no fabricated results, no claimed-but-unverified passes).

## Trust progression

Autonomy is earned, not granted. Each agent operates at a trust tier, configured in
`framework.yaml` and enforced by the orchestrator's human checkpoints:

| Tier | Name | Meaning |
|------|------|---------|
| 1 | `suggest` | Agent proposes; human decides |
| 2 | `act_with_review` | Agent acts; human reviews after |
| 3 | `autonomous_low_risk` | Agent is autonomous on low-risk work |
| 4 | `autonomous_with_oversight` | Agent handles critical work with sampled oversight |

Start every new agent at tier 1. Promotion criteria live in
[docs/05-adoption-roadmap.md](docs/05-adoption-roadmap.md).

## Using the agent specs with Claude Code

Each file in [agents/](agents/) uses Claude Code agent frontmatter. To deploy the fleet
into a project:

```bash
cp agents/*.md <your-project>/.claude/agents/
```

Then spawn them as subagents (e.g., `qe-test-generator`) from your sessions or CI
automation. The specs define each agent's mission, inputs/outputs, PACT behaviors,
guardrails, and handoff contracts.

## Design decisions

- **Fail-closed gates.** A blocking rule with a missing metric fails the gate. Quality
  decisions are never made on absent evidence.
- **Verdicts carry rationale.** Gate results enumerate every rule with actual vs.
  threshold, so a NO-GO is always explainable.
- **Methodology and mechanism are separated.** The docs describe *why*; `framework.yaml`
  describes *what*; `src/aqef` mechanically enforces it. You can adopt the methodology
  without the code, or vice versa.
- **Start small.** One agent, one use case, measured impact — then scale. Deploying the
  whole fleet on day one is an anti-pattern this framework explicitly rejects.

## License

MIT — use it, fork it, adapt it to your context. Context-driven: there are no
best practices, only practices good in context.
