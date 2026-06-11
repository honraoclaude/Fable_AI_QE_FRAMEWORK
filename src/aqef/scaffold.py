"""Project scaffolding: `aqef init` writes a minimal, valid starting point.

The starter is deliberately smaller than the full shipped framework.yaml —
adoption guidance says start with one or two agents and one enforced gate,
so that is exactly what the scaffold provides. Generated files are validated
with the framework's own loaders before being reported as created.
"""

from __future__ import annotations

from pathlib import Path

STARTER_FRAMEWORK = """\
# AQEF starter configuration — tune thresholds to your context.
# Docs: https://github.com/honraoclaude/Fable_AI_QE_FRAMEWORK
version: "1.0"
name: my-project quality framework

trust:
  default_tier: 1
  tiers:
    1: suggest                    # agent proposes; human decides
    2: act_with_review            # agent acts; human reviews after
    3: autonomous_low_risk

agents:
  qe-test-generator:
    role: test-creation
    trust_tier: 1                 # start at suggest; promote on evidence
    spec: agents/qe-test-generator.md
  qe-test-executor:
    role: execution
    trust_tier: 2
    spec: agents/qe-test-executor.md
  qe-coverage-analyzer:
    role: analysis
    trust_tier: 2
    spec: agents/qe-coverage-analyzer.md
  qe-quality-gatekeeper:
    role: gating
    trust_tier: 2
    spec: agents/qe-quality-gatekeeper.md

gates:
  pr-gate:
    description: Pre-merge gate. Run report-only for 2 weeks, then enforce.
    rules:
      - metric: tests_failed
        operator: "=="
        threshold: 0
        severity: blocking
      - metric: line_coverage_pct
        operator: ">="
        threshold: 80
        severity: blocking
      - metric: flaky_test_rate_pct
        operator: "<="
        threshold: 2
        severity: warning

workflows:
  pr-quality-gate:
    description: Quality pipeline for every pull request.
    steps:
      - agent: qe-test-generator
        action: generate_targeted_tests
      - agent: qe-test-executor
        action: run_tests
      - agent: qe-coverage-analyzer
        action: analyze_coverage
    gate: pr-gate
    human_checkpoint: on_fail
"""

STARTER_RISK_REGISTER = """\
# Product risk register — drives risk-based regression selection.
# Score = likelihood x impact (1-5 each). Tiers: critical >= 15, high >= 10,
# medium >= 5, low < 5. Humans own likelihood/impact; keep areas and tests
# in sync with the codebase. Usage:
#   aqef risks --register risk-register.yaml
#   aqef select-tests --register risk-register.yaml --changed <files...>
version: "1.0"
product: my-project

risks:
  - id: R-001
    title: "EXAMPLE: replace with your highest-impact failure mode"
    description: >
      What breaks, who it hurts, and why it matters. Past incidents count
      double.
    areas: ["src/critical_module/*"]
    likelihood: 3
    impact: 5
    tests:
      - "tests/critical_module/"
    owner: your-team
    review_by: "2026-12-01"
"""

NEXT_STEPS = """\
Created:
{created}

Next steps:
  1. Edit framework.yaml — tune gate thresholds to your risk appetite
     (run the gate report-only for ~2 weeks first to baseline your metrics).
  2. Replace the example risk in risk-register.yaml with your real top risks.
  3. Copy the agent specs you plan to use into .claude/agents/ (see the
     framework repo's agents/ directory).
  4. Wire the gate into CI:
       aqef gate pr-gate --config framework.yaml --metrics metrics.json
  5. Validate any time:
       aqef validate framework.yaml
       aqef risks --register risk-register.yaml
"""


def init_project(directory: str | Path, force: bool = False) -> list[Path]:
    """Write starter files into `directory`. Refuses to overwrite unless force.
    Returns the list of created paths."""
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)

    files = {
        target / "framework.yaml": STARTER_FRAMEWORK,
        target / "risk-register.yaml": STARTER_RISK_REGISTER,
    }

    if not force:
        existing = [str(p) for p in files if p.exists()]
        if existing:
            raise FileExistsError(
                "refusing to overwrite existing files (use --force): "
                + ", ".join(existing)
            )

    created = []
    for path, content in files.items():
        path.write_text(content, encoding="utf-8")
        created.append(path)

    # Dogfood: the scaffold must pass the framework's own validation.
    from aqef.config import load_config
    from aqef.risks import load_register

    load_config(target / "framework.yaml")
    load_register(target / "risk-register.yaml")

    return created
