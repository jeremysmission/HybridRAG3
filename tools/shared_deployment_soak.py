from __future__ import annotations

import argparse

from src.tools.shared_deployment_soak import (
    format_soak_console_summary,
    load_soak_questions,
    run_shared_deployment_soak,
    write_shared_soak_report,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a shared-deployment soak pass against the HybridRAG API and save a timestamped JSON report.",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base URL for the shared HybridRAG API.",
    )
    parser.add_argument(
        "--questions",
        default="docs/04_demo/DEMO_REHEARSAL_PACK.json",
        help="Text or JSON file containing soak questions.",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=1,
        help="How many times to replay the question list.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Maximum concurrent in-flight queries.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Per-request timeout in seconds.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=0.5,
        help="Queue snapshot poll interval in seconds. Use 0 to disable background polling.",
    )
    parser.add_argument(
        "--auth-token",
        default="",
        help="Optional API bearer token for protected deployments.",
    )
    parser.add_argument(
        "--proxy-user-header",
        default="",
        help="Optional trusted proxy user header name, for example X-Forwarded-User.",
    )
    parser.add_argument(
        "--proxy-identity-secret",
        default="",
        help="Optional trusted proxy identity secret value.",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Print the summary without writing a timestamped JSON report.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    questions = load_soak_questions(args.questions)
    report = run_shared_deployment_soak(
        base_url=args.base_url,
        questions=questions,
        concurrency=args.concurrency,
        rounds=args.rounds,
        timeout_seconds=args.timeout,
        auth_token=args.auth_token,
        proxy_user_header=args.proxy_user_header,
        proxy_identity_secret=args.proxy_identity_secret,
        poll_interval_seconds=args.poll_seconds,
    )
    print(format_soak_console_summary(report))
    if not args.no_report:
        path = write_shared_soak_report(report)
        print("Saved report: {}".format(path))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
