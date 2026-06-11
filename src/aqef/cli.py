"""CI-friendly CLI for the framework.

  python -m aqef init [--dir <path>] [--force]
  python -m aqef validate <framework.yaml>
  python -m aqef list-agents --config <framework.yaml>
  python -m aqef list-workflows --config <framework.yaml>
  python -m aqef gate <gate-name> --config <framework.yaml> --metrics <metrics.json>
                     [--format text|json] [--store] [--history <file>]
                     [--baseline <metrics.json> | --baseline-from-history]
                     [--fail-on-regression]
  python -m aqef report <gate-or-workflow> --config <framework.yaml>
                     --metrics <metrics.json> [--format md|html] [--out report.md]
                     [--subject "PR #42"] [--store] [--history <file>]
                     [--baseline <metrics.json> | --baseline-from-history]
  python -m aqef history [--history <file>] [--gate <name>] [--limit N]
  python -m aqef trend <gate-name> [--history <file>]
  python -m aqef decide <gate-or-workflow> --config <framework.yaml>
                     --metrics <metrics.json> [--format text|json]
                     [--baseline <metrics.json> | --baseline-from-history]
  python -m aqef dashboard [--config <file>] [--history <file>]
                     [--register <file>] [--port N] [--open]
  python -m aqef risks --register <risk-register.yaml>
  python -m aqef coverage --register <risk-register.yaml> --coverage <report.json>
                     [--threshold N] [--enforce] [--format text|json]
  python -m aqef select-tests --register <risk-register.yaml>
                     [--changed <file> ...] [--changed-from <list-file>]
                     [--min-tier low|medium|high|critical] [--limit N]
                     [--format text|json|selectors]

Exit codes: 0 on success (gate PASS/WARN), 1 on gate FAIL, 2 on usage/config error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aqef.compare import (
    compare_metrics,
    delta_to_dict,
    format_comparison,
    regressions,
)
from aqef.config import ConfigError, load_config
from aqef.decision import PROMOTE, decision_to_dict, recommend
from aqef.gates import evaluate_gate
from aqef.history import (
    DEFAULT_HISTORY,
    append_run,
    compute_trend,
    format_trend,
    last_good_metrics,
    load_runs,
)
from aqef.report import (
    gate_result_to_dict,
    render_html_report,
    render_markdown_report,
)
from aqef.risks import (
    TIERS,
    RiskRegisterError,
    load_register,
    select_tests,
    selection_to_dict,
)


def _load(config_path: str):
    try:
        return load_config(config_path)
    except FileNotFoundError:
        print(f"error: config file not found: {config_path}", file=sys.stderr)
        raise SystemExit(2)
    except ConfigError as exc:
        print(f"error: invalid configuration: {exc}", file=sys.stderr)
        raise SystemExit(2)


def cmd_init(args: argparse.Namespace) -> int:
    from aqef.scaffold import NEXT_STEPS, init_project

    try:
        created = init_project(args.dir, force=args.force)
    except FileExistsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    created_list = "\n".join(f"  {p}" for p in created)
    print(NEXT_STEPS.format(created=created_list))
    return 0


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


def _resolve_baseline(args: argparse.Namespace, gate_name: str) -> dict | None | int:
    """Baseline metrics from --baseline (file) or --baseline-from-history
    (last PASS run). Returns None when neither was requested, or an exit code
    on error. Must be called BEFORE --store appends the current run, so a
    passing run can never become its own baseline."""
    if args.baseline:
        return _load_metrics(args.baseline)
    if args.baseline_from_history:
        baseline = last_good_metrics(args.history, gate_name)
        if baseline is None:
            print(
                f"error: no PASS run recorded for gate {gate_name!r} in "
                f"{args.history} — nothing to use as baseline",
                file=sys.stderr,
            )
            return 2
        return baseline
    return None


def cmd_gate(args: argparse.Namespace) -> int:
    config = _load(args.config)
    if args.gate not in config.gates:
        known = ", ".join(sorted(config.gates))
        print(f"error: unknown gate {args.gate!r} (known: {known})", file=sys.stderr)
        return 2

    metrics = _load_metrics(args.metrics)
    if isinstance(metrics, int):
        return metrics

    if args.fail_on_regression and not (args.baseline or args.baseline_from_history):
        print(
            "error: --fail-on-regression requires --baseline or "
            "--baseline-from-history",
            file=sys.stderr,
        )
        return 2

    baseline = _resolve_baseline(args, gate_name=args.gate)
    if isinstance(baseline, int):
        return baseline

    result = evaluate_gate(config.gates[args.gate], metrics)
    if args.store:
        record = append_run(args.history, result, metrics)
        print(f"run stored: {args.history} @ {record.timestamp}", file=sys.stderr)

    deltas = None
    regressed = []
    if baseline is not None:
        deltas = compare_metrics(config.gates[args.gate], metrics, baseline)
        regressed = regressions(deltas)

    if args.format == "json":
        payload = gate_result_to_dict(result)
        if deltas is not None:
            payload["baseline"] = {
                "deltas": [delta_to_dict(d) for d in deltas],
                "regressions": [d.metric for d in regressed],
            }
        print(json.dumps(payload, indent=2))
    else:
        print(result.rationale())
        if deltas is not None:
            print(format_comparison(deltas))

    if args.fail_on_regression and regressed:
        names = ", ".join(d.metric for d in regressed)
        print(
            f"BASELINE REGRESSION (--fail-on-regression): {names}", file=sys.stderr
        )
        return 1
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

    baseline = _resolve_baseline(args, gate_name=gate.name)
    if isinstance(baseline, int):
        return baseline

    result = evaluate_gate(gate, metrics)
    if args.store:
        record = append_run(
            args.history,
            result,
            metrics,
            workflow=workflow.name if workflow else None,
            subject=args.subject,
        )
        print(f"run stored: {args.history} @ {record.timestamp}", file=sys.stderr)

    deltas = compare_metrics(gate, metrics, baseline) if baseline is not None else None

    renderer = render_html_report if args.format == "html" else render_markdown_report
    report = renderer(result, subject=args.subject, workflow=workflow, deltas=deltas)

    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"report written: {args.out} (verdict: {result.verdict})")
    else:
        print(report)
    return 1 if result.failed else 0


def cmd_history(args: argparse.Namespace) -> int:
    runs = load_runs(args.history, gate=args.gate)
    if not runs:
        target = f" for gate {args.gate!r}" if args.gate else ""
        print(f"no runs recorded{target} in {args.history}")
        return 0
    for run in runs[-args.limit :]:
        workflow = run.workflow or "-"
        subject = run.subject or "-"
        print(f"{run.timestamp}  {run.verdict:<4}  {run.gate}  {workflow}  {subject}")
    return 0


def cmd_trend(args: argparse.Namespace) -> int:
    runs = load_runs(args.history, gate=args.gate)
    if not runs:
        print(
            f"error: no runs recorded for gate {args.gate!r} in {args.history} "
            "(store runs with: aqef gate/report ... --store)",
            file=sys.stderr,
        )
        return 2
    print(format_trend(args.gate, compute_trend(runs)))
    return 0


def cmd_decide(args: argparse.Namespace) -> int:
    config = _load(args.config)

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

    baseline = _resolve_baseline(args, gate_name=gate.name)
    if isinstance(baseline, int):
        return baseline

    result = evaluate_gate(gate, metrics)
    deltas = compare_metrics(gate, metrics, baseline) if baseline is not None else None
    decision = recommend(result, deltas)

    if args.format == "json":
        payload = decision_to_dict(decision)
        payload["gate"] = gate_result_to_dict(result)
        print(json.dumps(payload, indent=2))
    else:
        print(result.rationale())
        if deltas is not None:
            print(format_comparison(deltas))
        print(decision.describe())

    return 0 if decision.recommendation == PROMOTE else 1


def cmd_dashboard(args: argparse.Namespace) -> int:
    import webbrowser

    from aqef.dashboard import create_server

    try:
        server = create_server(
            args.config, args.history, args.register,
            port=args.port, coverage_path=args.coverage,
        )
    except OSError as exc:
        print(f"error: cannot bind port {args.port}: {exc}", file=sys.stderr)
        return 2
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"AQEF dashboard: {url}  (Ctrl+C to stop)")
    print(f"  config:   {args.config or '—'}")
    print(f"  history:  {args.history}")
    print(f"  register: {args.register or '—'}")
    print(f"  coverage: {args.coverage or '—'}")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0


def _load_register(path: str):
    try:
        return load_register(path)
    except FileNotFoundError:
        print(f"error: risk register not found: {path}", file=sys.stderr)
        raise SystemExit(2)
    except RiskRegisterError as exc:
        print(f"error: invalid risk register: {exc}", file=sys.stderr)
        raise SystemExit(2)


def cmd_risks(args: argparse.Namespace) -> int:
    register = _load_register(args.register)
    print(f"Risk register: {register.product} — {len(register.risks)} risk(s)")
    ordered = sorted(register.risks, key=lambda r: -r.score)
    for risk in ordered:
        tests = f"{len(risk.tests)} test selector(s)" if risk.tests else "NO TESTS"
        print(
            f"  {risk.id}  score {risk.score:>2} ({risk.tier:<8})  "
            f"{risk.title}  [{tests}]"
        )
    untested = register.untested(min_tier="high")
    for risk in untested:
        print(
            f"WARNING: {risk.id} is {risk.tier} (score {risk.score}) "
            "but has no linked tests — untested risk",
            file=sys.stderr,
        )
    return 0


def cmd_coverage(args: argparse.Namespace) -> int:
    from aqef.coverage import (
        CoverageError,
        analyze_risk_coverage,
        format_risk_coverage,
        load_coverage,
        risk_coverage_to_dict,
        undercovered,
    )

    register = _load_register(args.register)
    try:
        file_coverage = load_coverage(args.coverage)
    except FileNotFoundError:
        print(f"error: coverage report not found: {args.coverage}", file=sys.stderr)
        return 2
    except CoverageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    results = analyze_risk_coverage(register, file_coverage)
    gaps = undercovered(results, args.threshold)

    if args.format == "json":
        payload = risk_coverage_to_dict(results)
        payload["undercovered_high_risk"] = [rc.risk.id for rc in gaps]
        print(json.dumps(payload, indent=2))
    else:
        print(format_risk_coverage(results, args.threshold))

    for rc in gaps:
        print(
            f"WARNING: {rc.risk.id} ({rc.risk.tier}, score {rc.risk.score}) is at "
            f"{rc.coverage_pct:g}% coverage — below {args.threshold:g}% in a "
            "high-risk area",
            file=sys.stderr,
        )
    if args.enforce and gaps:
        return 1
    return 0


def cmd_select_tests(args: argparse.Namespace) -> int:
    register = _load_register(args.register)

    changed: list[str] = list(args.changed or [])
    if args.changed_from:
        try:
            content = Path(args.changed_from).read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            print(
                f"error: changed-files list not found: {args.changed_from}",
                file=sys.stderr,
            )
            return 2
        changed += [line.strip() for line in content.splitlines() if line.strip()]

    items = select_tests(
        register,
        changed_files=changed or None,
        min_tier=args.min_tier,
        limit=args.limit,
    )

    # A change inside a risk area that has no linked tests is an unprotected
    # change — the selection can't cover it, so say so loudly.
    if changed:
        for risk in register.risks:
            if not risk.tests and risk.matches_changed(changed):
                print(
                    f"WARNING: change touches {risk.id} ({risk.tier}, "
                    f"'{risk.title}') but the risk has NO linked tests — "
                    "this change ships unprotected against it",
                    file=sys.stderr,
                )

    if args.format == "json":
        print(json.dumps(selection_to_dict(items), indent=2))
    elif args.format == "selectors":
        for item in items:  # bare selectors, one per line — pipe into a runner
            print(item.selector)
    else:
        if not items:
            print("no tests selected (no risks at or above the tier threshold)")
        scope = f"{len(changed)} changed file(s)" if changed else "no change context"
        print(f"Selected {len(items)} selector(s) [{scope}, min tier: {args.min_tier}]")
        for item in items:
            marker = "IMPACTED " if item.impacted else "         "
            print(f"  {marker}{item.selector}    <- {item.reason}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aqef",
        description="AI Agentic Quality Engineering Framework — gate and config tooling",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser(
        "init", help="scaffold a starter framework.yaml and risk-register.yaml"
    )
    p_init.add_argument("--dir", default=".", help="target directory (default: .)")
    p_init.add_argument(
        "--force", action="store_true", help="overwrite existing files"
    )
    p_init.set_defaults(func=cmd_init)

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
    _add_baseline_args(p_gate)
    p_gate.add_argument(
        "--fail-on-regression", action="store_true",
        help="exit 1 if any blocking/warning metric worsened vs. the baseline, "
        "even when all absolute thresholds pass",
    )
    _add_store_args(p_gate)
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
    p_report.add_argument(
        "--format", choices=("md", "html"), default="md",
        help="report format (default: md)",
    )
    _add_baseline_args(p_report)
    _add_store_args(p_report)
    p_report.set_defaults(func=cmd_report)

    p_history = sub.add_parser("history", help="list stored gate runs")
    p_history.add_argument("--history", default=DEFAULT_HISTORY)
    p_history.add_argument("--gate", help="filter by gate name")
    p_history.add_argument("--limit", type=int, default=10)
    p_history.set_defaults(func=cmd_history)

    p_trend = sub.add_parser("trend", help="metric and verdict trend for a gate")
    p_trend.add_argument("gate")
    p_trend.add_argument("--history", default=DEFAULT_HISTORY)
    p_trend.set_defaults(func=cmd_trend)

    p_decide = sub.add_parser(
        "decide",
        help="advisory release recommendation: PROMOTE / HOLD / ROLLBACK",
    )
    p_decide.add_argument(
        "target", help="workflow name (preferred) or gate name"
    )
    p_decide.add_argument("--config", required=True)
    p_decide.add_argument("--metrics", required=True, help="JSON file of metric values")
    p_decide.add_argument(
        "--format", choices=("text", "json"), default="text",
        help="output format (default: text)",
    )
    _add_baseline_args(p_decide)
    p_decide.add_argument(
        "--history", default=DEFAULT_HISTORY,
        help=f"history file for --baseline-from-history (default: {DEFAULT_HISTORY})",
    )
    p_decide.set_defaults(func=cmd_decide)

    p_dash = sub.add_parser(
        "dashboard", help="serve a live local quality dashboard"
    )
    p_dash.add_argument("--config", default="framework.yaml", help="framework config")
    p_dash.add_argument("--history", default=DEFAULT_HISTORY)
    p_dash.add_argument("--register", help="risk register YAML (optional)")
    p_dash.add_argument(
        "--coverage",
        help="coverage report JSON for the risk-weighted coverage view (optional)",
    )
    p_dash.add_argument("--port", type=int, default=8765)
    p_dash.add_argument("--open", action="store_true", help="open in the browser")
    p_dash.set_defaults(func=cmd_dashboard)

    p_risks = sub.add_parser(
        "risks", help="validate and list a product risk register"
    )
    p_risks.add_argument("--register", required=True, help="risk register YAML file")
    p_risks.set_defaults(func=cmd_risks)

    p_cov = sub.add_parser(
        "coverage", help="risk-weighted coverage analysis against the register"
    )
    p_cov.add_argument("--register", required=True, help="risk register YAML file")
    p_cov.add_argument(
        "--coverage", required=True,
        help="coverage report JSON (coverage.py or Istanbul/c8 json-summary)",
    )
    p_cov.add_argument(
        "--threshold", type=float, default=80,
        help="minimum coverage %% for high/critical risk areas (default: 80)",
    )
    p_cov.add_argument(
        "--enforce", action="store_true",
        help="exit 1 when any high/critical risk area is below the threshold",
    )
    p_cov.add_argument(
        "--format", choices=("text", "json"), default="text",
        help="output format (default: text)",
    )
    p_cov.set_defaults(func=cmd_coverage)

    p_select = sub.add_parser(
        "select-tests", help="risk-based regression test selection"
    )
    p_select.add_argument("--register", required=True, help="risk register YAML file")
    p_select.add_argument(
        "--changed", nargs="*",
        help="changed file paths (e.g. from git diff --name-only)",
    )
    p_select.add_argument(
        "--changed-from",
        help="file containing changed paths, one per line",
    )
    p_select.add_argument(
        "--min-tier", choices=TIERS, default="medium",
        help="include unimpacted risks at or above this tier (default: medium); "
        "risks whose areas match changed files are always included",
    )
    p_select.add_argument("--limit", type=int, help="cap the number of selectors")
    p_select.add_argument(
        "--format", choices=("text", "json", "selectors"), default="text",
        help="'selectors' prints bare selectors one per line for piping",
    )
    p_select.set_defaults(func=cmd_select_tests)

    return parser


def _add_baseline_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--baseline",
        help="baseline metrics JSON; reports per-metric movement vs. this snapshot",
    )
    group.add_argument(
        "--baseline-from-history", action="store_true",
        help="use the most recent PASS run from the history file as the baseline",
    )


def _add_store_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--store", action="store_true",
        help="append this run to the history file for trend analysis",
    )
    parser.add_argument(
        "--history", default=DEFAULT_HISTORY,
        help=f"history file path (default: {DEFAULT_HISTORY})",
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
