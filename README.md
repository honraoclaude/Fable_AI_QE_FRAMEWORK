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
| [src/aqef/](src/aqef/) | Reference implementation: config loader/validator, gate engine, workflow orchestrator, report generator, CLI |
| [tests/](tests/) | pytest suite for the reference implementation |
| [examples/](examples/) | Sample metrics payload for offline gate evaluation |

## Quickstart

```bash
# Install (editable) — provides the `aqef` command
pip install -e .

# Validate the framework configuration
aqef validate framework.yaml

# List the agent fleet
aqef list-agents --config framework.yaml

# Evaluate a quality gate against collected metrics (offline, CI-friendly)
aqef gate pr-gate --config framework.yaml --metrics examples/sample-metrics.json

# Same evaluation as machine-readable JSON (for dashboards, PR comments, pipelines)
aqef gate pr-gate --config framework.yaml --metrics examples/sample-metrics.json --format json

# Render a populated quality report (markdown or --format html) for a workflow run
aqef report pr-quality-gate --config framework.yaml --metrics examples/sample-metrics.json --subject "PR #42" --out report.md

# Advisory release recommendation (PROMOTE / HOLD / ROLLBACK) from the evidence
aqef decide pr-quality-gate --config framework.yaml --metrics examples/sample-metrics.json

# Risk-based regression selection from a product risk register
aqef risks --register examples/risk-register.yaml
aqef select-tests --register examples/risk-register.yaml --changed src/payments/capture.py

# Run the test suite
python -m pytest
```

(`python -m aqef …` works identically if you prefer not to install.)

The `gate` and `report` commands exit `0` on PASS/WARN and `1` on FAIL; `decide` exits
`0` only on PROMOTE — all drop straight into a CI pipeline as blocking steps. For the
full wired-together pipeline (selection → gate → recommendation → report artifact), see
[examples/github-actions-quality-gate.yml](examples/github-actions-quality-gate.yml).

## Reporting

Five layers, from machine-readable to human-judgment:

1. **JSON** — `gate --format json` emits the full verdict with per-rule evidence for
   dashboards, PR comment bots, and automation.
2. **Quality reports (markdown or HTML)** — `report <workflow-or-gate>` renders a
   populated report in the [templates/quality-report.md](templates/quality-report.md)
   shape: verdict first, violations on top, missing evidence called out, checkpoint
   policy applied. `--format html` produces a standalone styled page
   ([examples/sample-report.html](examples/sample-report.html)); see
   [examples/sample-report.md](examples/sample-report.md) for a generated FAIL report.
3. **Baseline regression detection** — `gate --baseline last-good.json
   --fail-on-regression` blocks when any blocking/warning metric *worsened* vs. the
   baseline, even if absolute thresholds still pass. Direction follows each rule
   (`==` rules use distance-to-target). With history enabled,
   `--baseline-from-history` compares against the most recent stored PASS run
   automatically. `report --baseline …` adds the comparison table to rendered
   reports. CI wiring example:
   [examples/github-actions-quality-gate.yml](examples/github-actions-quality-gate.yml).
4. **History & trends** — add `--store` to `gate` or `report` to append the run to an
   append-only JSONL history file (default `.aqef/history.jsonl`). Then:

   ```bash
   python -m aqef history --history .aqef/history.jsonl            # recent runs
   python -m aqef trend pr-gate --history .aqef/history.jsonl      # per-metric movement
   ```

   Trends assess each metric against its rule's direction (coverage rising =
   improving; latency rising = worsening) and report verdict distribution over time.
   History records are immutable — past runs are evidence, never edited.
5. **Human sections** — residual risk and the checkpoint decision are emitted as
   explicit placeholders. The renderer never fabricates content a human is supposed
   to supply; that judgment is recorded by the human quality owner.

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
