from __future__ import annotations

from pathlib import Path

from src.gui.testing.gui_cli_parity_harness import (
    CliParityCheck,
    DEFAULT_CLI_CHECKS,
    GuiCliParityHarness,
    ProbeOutcome,
    STATUS_FAILED,
    STATUS_MANUAL,
    STATUS_MISSING,
    STATUS_PASSED,
    STATUS_SKIPPED,
)


class _FakeStatusBar:
    def stop(self):
        return None


class _FakeApp:
    def __init__(self):
        self.status_bar = _FakeStatusBar()

    def destroy(self):
        return None


def test_default_cli_parity_catalog_tracks_expected_commands():
    commands = {check.cli_command: check for check in DEFAULT_CLI_CHECKS}
    assert "rag-query" in commands
    assert "rag-index" in commands
    assert "rag-status" in commands
    assert "rag-server" in commands
    assert commands["rag-server"].probe_name is None
    assert commands["rag-query"].requires_backends is True


def test_missing_check_is_reported_without_booting():
    boots = []

    def _boot():
        boots.append("booted")
        return _FakeApp()

    harness = GuiCliParityHarness(
        checks=[
            CliParityCheck(
                cli_command="rag-server",
                title="Missing server surface",
                category="missing",
                gui_surface="none",
            )
        ],
        project_root=Path.cwd(),
        boot_app=_boot,
    )

    report = harness.run()

    assert boots == []
    assert report["counts"][STATUS_MISSING] == 1
    assert report["ok"] is True
    assert report["strict_ok"] is False


def test_backend_required_check_skips_when_attach_mode_is_never():
    boots = []
    attached = []

    def _boot():
        boots.append("booted")
        return _FakeApp()

    def _attach(_app):
        attached.append("attached")

    class _Harness(GuiCliParityHarness):
        def _probe_query_probe(self):
            raise AssertionError("probe should not execute when backends are disabled")

    harness = _Harness(
        checks=[
            CliParityCheck(
                cli_command="rag-query",
                title="Query",
                category="core",
                gui_surface="QueryPanel",
                probe_name="_probe_query_probe",
                requires_backends=True,
            )
        ],
        project_root=Path.cwd(),
        boot_app=_boot,
        attach_backends=_attach,
        attach_mode="never",
    )

    report = harness.run()

    assert boots == ["booted"]
    assert attached == []
    assert report["counts"][STATUS_SKIPPED] == 1


def test_report_counts_failed_and_manual_states():
    class _Harness(GuiCliParityHarness):
        def _probe_pass(self):
            return ProbeOutcome(STATUS_PASSED, "ok")

        def _probe_manual(self):
            return ProbeOutcome(STATUS_MANUAL, "manual")

        def _probe_fail(self):
            return ProbeOutcome(STATUS_FAILED, "fail")

    harness = _Harness(
        checks=[
            CliParityCheck("rag-paths", "Paths", "admin", "surface", "_probe_pass"),
            CliParityCheck("rag-store-key", "Key", "cred", "surface", "_probe_manual"),
            CliParityCheck("rag-query", "Query", "core", "surface", "_probe_fail"),
        ],
        project_root=Path.cwd(),
        boot_app=_FakeApp,
    )

    report = harness.run()

    assert report["counts"][STATUS_PASSED] == 1
    assert report["counts"][STATUS_MANUAL] == 1
    assert report["counts"][STATUS_FAILED] == 1
    assert report["ok"] is False
    assert report["strict_ok"] is False
