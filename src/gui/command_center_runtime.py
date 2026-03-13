"""Shared runtime helpers for the GUI command center."""

from __future__ import annotations

import os
import shlex
import sqlite3
import sys
from dataclasses import dataclass

from src.security.credentials import (
    clear_credentials,
    credential_status,
    invalidate_credential_cache,
    resolve_credentials,
    store_api_key,
    store_api_version,
    store_deployment,
    store_endpoint,
    validate_endpoint,
)
from src.security.shared_deployment_auth import (
    apply_shared_launch_profile,
    format_shared_launch_snapshot,
    load_shared_launch_snapshot,
    store_shared_api_auth_token,
)


@dataclass(frozen=True)
class PreparedCommand:
    """Describe a subprocess command the command center can launch."""

    argv: tuple[str, ...]
    display: str
    long_running: bool = False
    reload_config_after: bool = False
    launch_detached: bool = False


def resolve_project_root() -> str:
    """Return the active project root for subprocess launches."""

    return os.path.abspath(os.environ.get("HYBRIDRAG_PROJECT_ROOT", os.getcwd()))


def resolve_cli_python() -> str:
    """Prefer python.exe when the GUI was launched from pythonw.exe."""

    current = os.path.abspath(sys.executable)
    if current.lower().endswith("pythonw.exe"):
        candidate = current[:-5] + ".exe"
        if os.path.isfile(candidate):
            return candidate
    return current


def build_subprocess_env(project_root: str) -> dict[str, str]:
    """Build an environment for CLI-equivalent subprocess execution."""

    env = os.environ.copy()
    env["HYBRIDRAG_PROJECT_ROOT"] = project_root
    pythonpath = env.get("PYTHONPATH", "")
    if pythonpath:
        env["PYTHONPATH"] = project_root + os.pathsep + pythonpath
    else:
        env["PYTHONPATH"] = project_root
    return env


def build_paths_report(config) -> str:
    """Format the CLI-style path report."""

    paths = getattr(config, "paths", None)
    lines = [
        "HybridRAG Paths",
        "---------------",
        f"Project root: {resolve_project_root()}",
        f"Python:       {resolve_cli_python()}",
        f"Data dir:     {os.environ.get('HYBRIDRAG_DATA_DIR', '(not set)')}",
        f"Source dir:   {getattr(paths, 'source_folder', '') or '(not set)'}",
        f"Database:     {getattr(paths, 'database', '') or '(not set)'}",
        f"Downloads:    {getattr(paths, 'download_folder', '') or '(not set)'}",
        "",
        "Network gate",
        "------------",
        f"HYBRIDRAG_NETWORK_KILL_SWITCH={os.environ.get('HYBRIDRAG_NETWORK_KILL_SWITCH', '(unset)')}",
        f"HYBRIDRAG_OFFLINE={os.environ.get('HYBRIDRAG_OFFLINE', '(unset)')}",
        f"NO_PROXY={os.environ.get('NO_PROXY', '(unset)')}",
    ]
    return "\n".join(lines)


def build_status_report(config) -> str:
    """Format a compact local health report similar to rag-status."""

    paths = getattr(config, "paths", None)
    database_path = getattr(paths, "database", "") if paths is not None else ""
    lines = [
        "HybridRAG Status",
        "----------------",
        f"Python exe: {resolve_cli_python()}",
        f"Mode:       {getattr(config, 'mode', 'unknown')}",
        f"Gate:       {os.environ.get('HYBRIDRAG_NETWORK_KILL_SWITCH', '(unset)')}",
    ]
    if getattr(config, "mode", "") == "online":
        api = getattr(config, "api", None)
        lines.append(f"Online model:  {getattr(api, 'model', '') or '(not set)'}")
        lines.append(f"Deployment:    {getattr(api, 'deployment', '') or '(not set)'}")
    else:
        ollama = getattr(config, "ollama", None)
        lines.append(f"Offline model: {getattr(ollama, 'model', '') or '(not set)'}")

    if database_path and os.path.isfile(database_path):
        try:
            con = sqlite3.connect(database_path)
            try:
                chunk_count = con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
                source_count = con.execute(
                    "SELECT COUNT(DISTINCT source_path) FROM chunks"
                ).fetchone()[0]
            finally:
                con.close()
            lines.extend(
                [
                    f"Database:      {database_path}",
                    f"Chunks:        {chunk_count}",
                    f"Source files:  {source_count}",
                ]
            )
        except Exception as exc:
            lines.extend(
                [
                    f"Database:      {database_path}",
                    f"DB warning:    {type(exc).__name__}: {exc}",
                ]
            )
    else:
        lines.append(f"Database:      {database_path or '(not set)'}")
    return "\n".join(lines)


def build_credential_report() -> str:
    """Format the credential status report for the GUI."""

    status = credential_status()
    creds = resolve_credentials(use_cache=False)
    lines = [
        "Credential Status",
        "-----------------",
        f"API key:      {'STORED' if status['api_key_set'] else 'NOT SET'} ({status['api_key_source']})",
        f"Endpoint:     {'STORED' if status['api_endpoint_set'] else 'NOT SET'} ({status['api_endpoint_source']})",
        f"Deployment:   {'STORED' if status['deployment_set'] else 'NOT SET'} ({status['deployment_source']})",
        f"API version:  {'STORED' if status['api_version_set'] else 'NOT SET'} ({status['api_version_source']})",
        f"Provider:     {status['provider']} ({status['provider_source']})",
        f"Online ready: {creds.is_online_ready}",
    ]
    if status["api_key_set"]:
        lines.append(f"Key preview:   {creds.key_preview}")
    if status["api_endpoint_set"]:
        lines.append(f"Endpoint URL:  {creds.endpoint}")
    if status["deployment_set"]:
        lines.append(f"Deployment:    {creds.deployment}")
    if status["api_version_set"]:
        lines.append(f"API version:   {creds.api_version}")
    return "\n".join(lines)


def build_shared_launch_report(
    *,
    project_root: str = "",
    apply_online: bool = False,
    apply_production: bool = False,
) -> str:
    """Format the shared launch readiness report for the GUI."""

    root = project_root or resolve_project_root()
    if apply_online or apply_production:
        snapshot = apply_shared_launch_profile(
            root,
            set_online=bool(apply_online),
            set_production=bool(apply_production),
        )
    else:
        snapshot = load_shared_launch_snapshot(root)
    return format_shared_launch_snapshot(snapshot)


def store_api_key_from_gui(api_key: str) -> str:
    """Store an API key and return a user-facing summary."""

    key = str(api_key or "").strip()
    if not key:
        raise ValueError("API key is required.")
    store_api_key(key)
    invalidate_credential_cache()
    preview = key[:4] + "..." + key[-4:] if len(key) > 8 else "****"
    return "API key stored in Windows Credential Manager.\nPreview: {}".format(preview)


def store_shared_token_from_gui(shared_token: str, *, previous: bool = False) -> str:
    """Store a shared deployment token and return a user-facing summary."""

    token = str(shared_token or "").strip()
    if not token:
        raise ValueError("Shared deployment token is required.")
    store_shared_api_auth_token(token, previous=previous)
    preview = token[:4] + "..." + token[-4:] if len(token) > 8 else "****"
    label = "previous shared deployment token" if previous else "shared deployment token"
    return "{} stored in Windows Credential Manager.\nPreview: {}".format(
        label.capitalize(),
        preview,
    )


def store_endpoint_bundle_from_gui(
    endpoint: str,
    deployment: str = "",
    api_version: str = "",
) -> str:
    """Store endpoint details and return a user-facing summary."""

    cleaned = validate_endpoint(str(endpoint or "").strip())
    dep = str(deployment or "").strip()
    version = str(api_version or "").strip()
    store_endpoint(cleaned)
    if dep:
        store_deployment(dep)
    if version:
        store_api_version(version)
    invalidate_credential_cache()
    lines = [f"Endpoint stored: {cleaned}"]
    if dep:
        lines.append(f"Deployment stored: {dep}")
    if version:
        lines.append(f"API version stored: {version}")
    return "\n".join(lines)


def clear_credentials_from_gui() -> str:
    """Clear stored credentials and return a status line."""

    clear_credentials()
    invalidate_credential_cache()
    return "All stored credentials were removed from Windows Credential Manager."


def prepare_command(alias: str, values: dict[str, object], project_root: str) -> PreparedCommand:
    """Translate a command-center selection into a subprocess command."""

    python_exe = resolve_cli_python()
    scripts_dir = os.path.join(project_root, "scripts")

    if alias == "rag-diag":
        extra = shlex.split(str(values.get("extra_args", "") or ""), posix=False)
        argv = (python_exe, "-m", "src.diagnostic.hybridrag_diagnostic", *extra)
        return PreparedCommand(argv=argv, display=" ".join(argv))

    if alias == "rag-models":
        argv = (python_exe, os.path.join(scripts_dir, "_list_models.py"))
        return PreparedCommand(argv=argv, display=" ".join(argv))

    if alias == "rag-test-api":
        argv = (python_exe, os.path.join(scripts_dir, "_test_api.py"))
        return PreparedCommand(argv=argv, display=" ".join(argv))

    if alias == "rag-profile":
        profile = str(values.get("profile", "status") or "status").strip()
        if profile == "status":
            argv = (python_exe, os.path.join(scripts_dir, "_profile_status.py"))
            return PreparedCommand(argv=argv, display=" ".join(argv))
        argv = (python_exe, os.path.join(scripts_dir, "_profile_switch.py"), profile)
        return PreparedCommand(argv=argv, display=" ".join(argv), reload_config_after=True)

    if alias == "rag-server":
        host = str(values.get("host", "127.0.0.1") or "127.0.0.1").strip()
        port = int(values.get("port", 8000) or 8000)
        argv = (python_exe, "-m", "src.api.server", "--host", host, "--port", str(port))
        return PreparedCommand(argv=argv, display=" ".join(argv), long_running=True)

    if alias == "rag-gui":
        argv = (python_exe, "-m", "src.gui.launch_gui", "--detach")
        return PreparedCommand(argv=argv, display=" ".join(argv), launch_detached=True)

    raise ValueError("Unsupported subprocess command: {}".format(alias))
