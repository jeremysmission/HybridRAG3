from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path

from src.security.shared_deployment_auth import (
    SHARED_API_AUTH_TOKEN_ENV,
    apply_shared_launch_profile,
    clear_shared_api_auth_tokens,
    format_shared_launch_snapshot,
    load_shared_launch_snapshot,
    store_shared_api_auth_token,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Readiness checker for the shared HybridRAG launch posture."
    )
    parser.add_argument(
        "--project-root",
        default=".",
        help="HybridRAG project root to inspect (default: current directory).",
    )
    parser.add_argument(
        "--apply-online",
        action="store_true",
        help="Persist mode=online before reporting readiness.",
    )
    parser.add_argument(
        "--apply-production",
        action="store_true",
        help="Persist security.deployment_mode=production before reporting readiness.",
    )
    parser.add_argument(
        "--prompt-shared-token",
        action="store_true",
        help="Prompt securely and store the shared API token in Credential Manager.",
    )
    parser.add_argument(
        "--prompt-previous-token",
        action="store_true",
        help="Prompt securely and store the previous shared API token in Credential Manager.",
    )
    parser.add_argument(
        "--clear-stored-tokens",
        action="store_true",
        help="Delete stored shared API tokens from Credential Manager before reporting readiness.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of text.",
    )
    parser.add_argument(
        "--fail-if-blocked",
        action="store_true",
        help="Exit non-zero when launch readiness is blocked.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = Path(args.project_root).expanduser().resolve()

    if args.clear_stored_tokens:
        clear_shared_api_auth_tokens()

    if args.prompt_shared_token:
        token = getpass.getpass(
            "Shared API token (stored as {} or Credential Manager): ".format(
                SHARED_API_AUTH_TOKEN_ENV
            )
        )
        store_shared_api_auth_token(token)

    if args.prompt_previous_token:
        token = getpass.getpass("Previous shared API token: ")
        store_shared_api_auth_token(token, previous=True)

    if args.apply_online or args.apply_production:
        snapshot = apply_shared_launch_profile(
            project_root,
            set_online=bool(args.apply_online),
            set_production=bool(args.apply_production),
        )
    else:
        snapshot = load_shared_launch_snapshot(project_root)

    if args.json:
        print(json.dumps(snapshot.__dict__, indent=2, sort_keys=True))
    else:
        print(format_shared_launch_snapshot(snapshot))

    if args.fail_if_blocked and not snapshot.ready_for_shared_launch:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
