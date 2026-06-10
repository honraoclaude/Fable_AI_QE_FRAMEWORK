"""CI-friendly CLI for the framework.

  python -m aqef validate <framework.yaml>
  python -m aqef list-agents --config <framework.yaml>
  python -m aqef list-workflows --config <framework.yaml>
  python -m aqef gate <gate-name> --config <framework.yaml> --metrics <metrics.json>
                     [--format text|json]
  python -m aqef report <gate-or-workflow> --config <framework.yaml>
                     --metrics <metrics.json> [--out report.md] [--subject "PR #42"]

Exit codes: 0 on success (gate PASS/WARN), 1 on gate FAIL, 2 on usage/config error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aqef.config import ConfigError, load_config
from aqef.gates import evaluate_gate
from aqef.report import gate_result_to_dict, render_markdown_report


def _load(config_path: str):
    try:
        return load_config(config_path)
    except FileNotFoundError:
        print(f"error: config file not found: {config_path}", file=sys.stderr)
        raise SystemExit(2)
    except ConfigError as exc:
        print(f"error: invalid configuration: {exc}", file=sys.stderr)
        raise SystemExit(2)


def cmd_validate(args: argparse.Namespace) -> int:
    config = _load(args.config)
    print(
        f"OK: {config.name} v{config.version} — "
        f"{len(config.agents)} agents, {len(config.gates)} gates, "
        f"{len(config.workflows)} workflows"
    )
    return 0


def cmd_list_agents(args: argparse.Namespace) -> int:
    config = _load(args.config)
    width = max(len(name) for name in config.agents)
    for name, agent in sorted(config.agents.items()):
        tier_label = config.trust_tiers[agent.trust_tier]
        print(f"{name:<{width}}  tier {agent.trust_tier} ({tier_label})  {agent.role}")
    return 0


def cmd_list_workflows(args: argparse.Namespace) -> int:
    config = _load(args.config)
    for name, wf in sorted(config.workflows.items()):
        print(f"{name}  gate={wf.gate}  checkpoint={wf.human_checkpoint}")
        for step in wf.steps:
            print(f"  - {step.agent} · {step.action}")
    return 0


def _load_metrics(path: str) -> dict | int:
    """Return the metrics dict, or an exit code on error."""
    metrics_path = Path(path)
    try:
        # utf-8-sig tolerates the BOM that Windows tooling often prepends
        metrics = json.loads(metrics_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        print(f"error: metrics file not found: {metrics_path}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"error: metrics file is not valid JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(metrics, dict):
        print("error: metrics file must contain a JSON object", file=sys.stderr)
        return 2
    return metrics


def cmd_gate(args: argparse.Namespace) -> int:
    config = _load(args.config)
    if args.gate not in config.gates:
        known = ", ".join(sorted(config.gates))
        print(f"error: unknown gate {args.gate!r} (known: {known})", file=sys.stderr)
        return 2

    metrics = _load_metrics(args.metrics)
    if isinstance(metrics, int):
        return metrics

    result = evaluate_gate(config.gates[args.gate], metrics)
    if args.format == "json":
        print(json.dumps(gate_result_to_dict(result), indent=2))
    else:
        print(result.rationale())
    return 1 if result.failed else 0


def cmd_report(args: argparse.Namespace) -> int:
    config = _load(args.config)

    # The target may be a workflow (preferred: provides checkpoint context) or a gate.
    workflow = config.workflows.get(args.target)
    if workflow is not None:
        gate = config.gates[workflow.gate]
    elif args.target in config.gates:
        gate = config.gates[args.target]
    else:
        known = ", ".join(sorted(list(config.workflows) + list(config.gates)))
        print(
            f"error: {args.target!r} is neither a workflow nor a gate (known: {known})",
            file=sys.stderr,
        )
        return 2

    metrics = _load_metrics(args.metrics)
    if isinstance(metrics, int):
        return metrics

    result = evaluate_gate(gate, metrics)
    report = render_markdown_report(result, subject=args.subject, workflow=workflow)

    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"report written: {args.out} (verdict: {result.verdict})")
    else:
        print(report)
    return 1 if result.failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aqef",
        description="AI Agentic Quality Engineering Framework — gate and config tooling",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="validate a framework.yaml")
    p_validate.add_argument("config")
    p_validate.set_defaults(func=cmd_validate)

    p_agents = sub.add_parser("list-agents", help="list the agent fleet")
    p_agents.add_argument("--config", required=True)
    p_agents.set_defaults(func=cmd_list_agents)

    p_workflows = sub.add_parser("list-workflows", help="list workflows and steps")
    p_workflows.add_argument("--config", required=True)
    p_workflows.set_defaults(func=cmd_list_workflows)

    p_gate = sub.add_parser("gate", help="evaluate a gate against collected metrics")
    p_gate.add_argument("gate")
    p_gate.add_argument("--config", required=True)
    p_gate.add_argument("--metrics", required=True, help="JSON file of metric values")
    p_gate.add_argument(
        "--format", choices=("text", "json"), default="text",
        help="output format (default: text)",
    )
    p_gate.set_defaults(func=cmd_gate)

    p_report = sub.add_parser(
        "report", help="render a populated quality report (markdown)"
    )
    p_report.add_argument(
        "target", help="workflow name (preferred, adds checkpoint context) or gate name"
    )
    p_report.add_argument("--config", required=True)
    p_report.add_argument("--metrics", required=True, help="JSON file of metric values")
    p_report.add_argument("--out", help="write the report to this file (default: stdout)")
    p_report.add_argument(
        "--subject", default="", help='report subject, e.g. "PR #42" or "release 2.3.0"'
    )
    p_report.set_defaults(func=cmd_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
