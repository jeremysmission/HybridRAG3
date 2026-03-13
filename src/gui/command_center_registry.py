"""Registry for the GUI command center CLI-parity surface."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CommandFieldSpec:
    """Describe one input field for a command."""

    key: str
    label: str
    kind: str = "text"
    required: bool = False
    default: object = ""
    placeholder: str = ""
    help_text: str = ""
    choices: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class CommandSpec:
    """Describe one CLI-equivalent action exposed in the GUI."""

    command_id: str
    alias: str
    title: str
    category: str
    summary: str
    cli_equivalent: str
    action_kind: str
    handler: str
    run_label: str = "Run"
    detail: str = ""
    target_view: str = ""
    long_running: bool = False
    reload_config_after: bool = False
    fields: tuple[CommandFieldSpec, ...] = field(default_factory=tuple)


COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec(
        command_id="query",
        alias="rag-query",
        title="Ask A Question",
        category="Core Workflows",
        summary="Use the native Query panel instead of a raw terminal prompt.",
        cli_equivalent='rag-query "question"',
        action_kind="native",
        handler="open_query",
        run_label="Open Query",
        detail="Prefill the question and optionally submit it immediately.",
        target_view="query",
        fields=(
            CommandFieldSpec(
                "question",
                "Question",
                kind="multiline",
                required=False,
                placeholder="Type the question you would normally pass to rag-query.",
            ),
            CommandFieldSpec(
                "run_now",
                "Submit immediately",
                kind="bool",
                default=False,
                help_text="If checked, the Query panel will try to run the question after opening.",
            ),
        ),
    ),
    CommandSpec(
        command_id="index",
        alias="rag-index",
        title="Run Indexing",
        category="Core Workflows",
        summary="Open the native Index panel and optionally start indexing right away.",
        cli_equivalent="rag-index",
        action_kind="native",
        handler="open_index",
        run_label="Open Index",
        detail="The GUI shows progress, telemetry, and safe stop controls while indexing runs.",
        target_view="index",
        fields=(CommandFieldSpec("start_now", "Start indexing immediately", kind="bool", default=True),),
    ),
    CommandSpec(
        command_id="set_model",
        alias="rag-set-model",
        title="Pick A Model",
        category="Core Workflows",
        summary="Route to the native model-selection surfaces already built into the GUI.",
        cli_equivalent="rag-set-model",
        action_kind="native",
        handler="open_model_surface",
        run_label="Open Model Controls",
        detail="Query has the fast role-aware picker; Admin has the online discovery grid and saved defaults.",
        fields=(
            CommandFieldSpec(
                "surface",
                "Open in",
                kind="choice",
                default="query",
                choices=(("query", "Query Panel"), ("admin", "Admin Panel")),
            ),
        ),
    ),
    CommandSpec(
        command_id="mode_offline",
        alias="rag-mode-offline",
        title="Switch To Offline",
        category="Mode And Access",
        summary="Use the same guarded mode-switch logic as the title bar.",
        cli_equivalent="rag-mode-offline",
        action_kind="native",
        handler="switch_mode_offline",
        run_label="Switch Offline",
    ),
    CommandSpec(
        command_id="mode_online",
        alias="rag-mode-online",
        title="Switch To Online",
        category="Mode And Access",
        summary="Use the same guarded mode-switch logic as the title bar.",
        cli_equivalent="rag-mode-online",
        action_kind="native",
        handler="switch_mode_online",
        run_label="Switch Online",
    ),
    CommandSpec(
        command_id="store_key",
        alias="rag-store-key",
        title="Store API Key",
        category="Mode And Access",
        summary="Save the API key directly to Windows Credential Manager from the GUI.",
        cli_equivalent="rag-store-key",
        action_kind="native",
        handler="store_api_key",
        fields=(
            CommandFieldSpec(
                "api_key",
                "API key",
                kind="password",
                required=True,
                placeholder="Paste the key you would normally enter at the CLI prompt.",
            ),
        ),
    ),
    CommandSpec(
        command_id="store_shared_token",
        alias="rag-store-shared-token",
        title="Store Shared Token",
        category="Mode And Access",
        summary="Save the shared deployment token directly to Windows Credential Manager.",
        cli_equivalent="python tools/shared_launch_preflight.py --prompt-shared-token",
        action_kind="native",
        handler="store_shared_token",
        fields=(
            CommandFieldSpec(
                "shared_token",
                "Shared token",
                kind="password",
                required=True,
                placeholder="Paste the shared deployment token.",
            ),
            CommandFieldSpec(
                "previous",
                "Store as previous token",
                kind="bool",
                default=False,
                help_text="Use this for a cutover window where both current and previous tokens must work.",
            ),
        ),
    ),
    CommandSpec(
        command_id="store_endpoint",
        alias="rag-store-endpoint",
        title="Store Endpoint",
        category="Mode And Access",
        summary="Save endpoint, deployment, and API version without leaving the GUI.",
        cli_equivalent="rag-store-endpoint",
        action_kind="native",
        handler="store_endpoint",
        fields=(
            CommandFieldSpec("endpoint", "Endpoint", required=True, placeholder="https://your-provider.example.com"),
            CommandFieldSpec("deployment", "Deployment", placeholder="Optional unless your provider requires it."),
            CommandFieldSpec(
                "api_version",
                "API version",
                default="2024-02-01",
                placeholder="Optional for OpenAI-compatible providers.",
            ),
        ),
    ),
    CommandSpec(
        command_id="cred_status",
        alias="rag-cred-status",
        title="Show Credential Status",
        category="Mode And Access",
        summary="Inspect the current API credential posture without opening PowerShell.",
        cli_equivalent="rag-cred-status",
        action_kind="native",
        handler="credential_status",
    ),
    CommandSpec(
        command_id="cred_delete",
        alias="rag-cred-delete",
        title="Clear Stored Credentials",
        category="Mode And Access",
        summary="Remove all stored API credentials from Windows Credential Manager.",
        cli_equivalent="rag-cred-delete",
        action_kind="native",
        handler="clear_credentials",
        run_label="Delete Credentials",
        detail="This uses the same secure credential store as the CLI commands.",
    ),
    CommandSpec(
        command_id="models",
        alias="rag-models",
        title="List Available Models",
        category="Mode And Access",
        summary="Run the shared model inventory script and stream its output in-place.",
        cli_equivalent="rag-models",
        action_kind="process",
        handler="rag-models",
    ),
    CommandSpec(
        command_id="test_api",
        alias="rag-test-api",
        title="Test API Connectivity",
        category="Mode And Access",
        summary="Run the same API connectivity check that the CLI exposes.",
        cli_equivalent="rag-test-api",
        action_kind="process",
        handler="rag-test-api",
    ),
    CommandSpec(
        command_id="profile",
        alias="rag-profile",
        title="Switch Performance Profile",
        category="Mode And Access",
        summary="Read or change the active hardware profile from the GUI.",
        cli_equivalent="rag-profile [status|laptop_safe|desktop_power|server_max]",
        action_kind="process",
        handler="rag-profile",
        reload_config_after=True,
        fields=(
            CommandFieldSpec(
                "profile",
                "Profile",
                kind="choice",
                default="status",
                choices=(
                    ("status", "Show current profile"),
                    ("laptop_safe", "laptop_safe"),
                    ("desktop_power", "desktop_power"),
                    ("server_max", "server_max"),
                ),
            ),
        ),
    ),
    CommandSpec(
        command_id="paths",
        alias="rag-paths",
        title="Show Paths",
        category="Diagnostics",
        summary="Display the same environment and storage path view the CLI provides.",
        cli_equivalent="rag-paths",
        action_kind="native",
        handler="show_paths",
    ),
    CommandSpec(
        command_id="status",
        alias="rag-status",
        title="Quick Health Check",
        category="Diagnostics",
        summary="Show a local health snapshot for Python, mode, gate, and database state.",
        cli_equivalent="rag-status",
        action_kind="native",
        handler="show_status",
    ),
    CommandSpec(
        command_id="shared_launch",
        alias="rag-shared-launch",
        title="Shared Launch Readiness",
        category="Diagnostics",
        summary="Inspect or apply the shared launch posture without leaving the GUI.",
        cli_equivalent="python tools/shared_launch_preflight.py",
        action_kind="native",
        handler="show_shared_launch",
        run_label="Run Preflight",
        detail="The same readiness logic checks mode, deployment guard, and shared auth posture before the next live soak.",
        fields=(
            CommandFieldSpec(
                "apply_online",
                "Persist online mode",
                kind="bool",
                default=False,
            ),
            CommandFieldSpec(
                "apply_production",
                "Persist production guard",
                kind="bool",
                default=False,
            ),
        ),
    ),
    CommandSpec(
        command_id="diag",
        alias="rag-diag",
        title="Run Diagnostics",
        category="Diagnostics",
        summary="Launch the full diagnostic CLI and stream its output in the panel.",
        cli_equivalent="rag-diag [flags]",
        action_kind="process",
        handler="rag-diag",
        fields=(CommandFieldSpec("extra_args", "Extra flags", placeholder='Example: --verbose or --test-query "freq range"'),),
    ),
    CommandSpec(
        command_id="server",
        alias="rag-server",
        title="Start REST API Server",
        category="Diagnostics",
        summary="Run the local FastAPI server and stream logs until you stop it.",
        cli_equivalent="rag-server -Host 127.0.0.1 -Port 8000",
        action_kind="process",
        handler="rag-server",
        long_running=True,
        run_label="Start Server",
        fields=(
            CommandFieldSpec("host", "Host", default="127.0.0.1"),
            CommandFieldSpec("port", "Port", kind="int", default=8000),
        ),
    ),
    CommandSpec(
        command_id="launch_gui",
        alias="rag-gui",
        title="Launch Another GUI Window",
        category="Diagnostics",
        summary="Spawn another detached HybridRAG GUI process if you need a second session.",
        cli_equivalent="rag-gui",
        action_kind="process",
        handler="rag-gui",
    ),
)


def get_command_specs() -> list[CommandSpec]:
    """Return command-center specs in stable display order."""

    return list(COMMAND_SPECS)
