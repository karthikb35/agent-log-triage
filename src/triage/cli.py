"""Command-line entrypoint for the triage engine.

Usage::

    triage run --reports .steplog --format md
    triage run --reports .steplog --out out/triage.json --fail-under 0.5

This is what the Kubernetes Job/CronJob executes: ingest the structured
step-logs, run the deterministic multi-agent workflow, emit a report, and exit
non-zero if the automation rate fell below a threshold (so a regression in
triage coverage is visible in CI).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .graph import run_pipeline
from .ingest import extract_failures, load_reports


def _render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Triage report",
        "",
        summary.get("narrative", ""),
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Total failures | {summary['total_failures']} |",
        f"| Incidents | {summary['total_incidents']} |",
        f"| Auto-triaged failures | {summary['auto_triaged_failures']} |",
        f"| Automation rate | {summary['automation_rate'] * 100:.0f}% |",
        f"| Est. minutes saved | {summary['estimated_minutes_saved']} |",
        "",
        "## Incidents",
        "",
        "| Service | Category | Count | Probable cause | Auto |",
        "| --- | --- | --- | --- | --- |",
    ]
    for i in summary["incidents"]:
        lines.append(
            f"| {i['service']} | {i['category']} | {i['count']} | "
            f"{i['probable_cause']} | {'yes' if i['auto_triaged'] else 'NO'} |"
        )
    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    reports = load_reports(args.reports)
    failures = extract_failures(reports)
    result = run_pipeline({"reports": reports, "failures": failures})
    summary = result["summary"]

    if args.format == "md":
        rendered = _render_markdown(summary)
    else:
        rendered = json.dumps(summary, indent=2)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered, encoding="utf-8")
        print(f"wrote {out}")
    else:
        print(rendered)

    rate = summary["automation_rate"]
    if rate < args.fail_under:
        print(
            f"::error:: automation rate {rate:.0%} below threshold {args.fail_under:.0%}",
            file=sys.stderr,
        )
        return 1
    return 0


def serve(args: argparse.Namespace) -> int:
    """Run the async triage API (FastAPI + uvicorn)."""

    try:
        import uvicorn

        from .api import create_app
    except ImportError as exc:  # pragma: no cover - missing optional extra
        print(
            "The API needs the 'serve' extra. Install with: "
            "pip install 'agentic-log-triage[serve]'",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    uvicorn.run(create_app(), host=args.host, port=args.port)
    return 0


def worker(args: argparse.Namespace) -> int:
    """Run a triage worker that consumes tasks from the Redis Stream."""

    try:
        from .worker import main as worker_main
    except ImportError as exc:  # pragma: no cover - missing optional extra
        print(
            "The worker needs the 'serve' extra. Install with: "
            "pip install 'agentic-log-triage[serve]'",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    worker_main()
    return 0



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="triage", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Triage a directory of step-log reports.")
    run_p.add_argument(
        "--reports",
        default=".steplog",
        help="File or directory containing report.json step-logs (default: .steplog).",
    )
    run_p.add_argument("--out", help="Write the report here instead of stdout.")
    run_p.add_argument(
        "--format", choices=["json", "md"], default="json", help="Output format."
    )
    run_p.add_argument(
        "--fail-under",
        type=float,
        default=0.0,
        help="Exit non-zero if the automation rate is below this (0..1).",
    )
    run_p.set_defaults(func=run)

    serve_p = sub.add_parser("serve", help="Run the async triage API server.")
    serve_p.add_argument("--host", default="0.0.0.0", help="Bind host.")
    serve_p.add_argument("--port", type=int, default=8080, help="Bind port.")
    serve_p.set_defaults(func=serve)

    worker_p = sub.add_parser("worker", help="Run a triage queue worker.")
    worker_p.set_defaults(func=worker)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
