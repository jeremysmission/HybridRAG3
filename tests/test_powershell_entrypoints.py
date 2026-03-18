import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8", errors="replace")


def test_powershell_entrypoints_set_process_scope_execution_policy_bypass():
    entrypoints = [
        "start_hybridrag.ps1",
        "tools/launch_gui.ps1",
        "tools/setup_home.ps1",
        "tools/setup_work.ps1",
        "tools/build_usb_deploy_bundle.ps1",
        "tools/usb_install_offline.ps1",
    ]
    expected = "Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force -ErrorAction SilentlyContinue"
    for relative_path in entrypoints:
        content = _read(relative_path)
        marker_candidates = [
            content.find("$ErrorActionPreference"),
            content.find("function Test-MachineRestricted"),
            content.find("function Write-Info"),
            content.find("function Write-Step"),
        ]
        body_start = min(index for index in marker_candidates if index > 0)
        assert expected in content[:body_start], (
            f"{relative_path} must attempt a process-scope execution-policy bypass "
            "before the main script body"
        )


def test_launch_gui_ps1_resolves_project_root_and_venv_context():
    content = _read("tools/launch_gui.ps1")
    assert "Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)" in content
    assert "Set-Location $ProjectRoot" in content
    assert "$env:HYBRIDRAG_PROJECT_ROOT = $ProjectRoot" in content
    assert "$env:VIRTUAL_ENV = $VenvRoot" in content
    assert "Join-Path $ProjectRoot '.venv\\Scripts\\python.exe'" in content
    assert "function Test-PythonUsable([string]$PythonPath)" in content
    assert 'throw "No usable Python interpreter found.' in content


def test_build_usb_deploy_bundle_prefers_repo_venv_python_by_project_root():
    content = _read("tools/build_usb_deploy_bundle.ps1")
    assert 'function Find-Python([string]$ProjectRoot)' in content
    assert 'Join-Path $ProjectRoot ".venv\\Scripts\\python.exe"' in content
    assert '$py = Find-Python $projectRoot' in content


def test_start_rag_bat_launches_powershell_without_loading_user_profile():
    content = _read("start_rag.bat")
    assert "powershell -NoLogo -NoProfile -NoExit -Command" in content


@pytest.mark.skipif(os.name != "nt", reason="PowerShell execution test requires Windows")
def test_start_hybridrag_ps1_executes_in_clean_no_profile_shell(tmp_path):
    script_copy = tmp_path / "start_hybridrag.ps1"
    shutil.copyfile(REPO_ROOT / "start_hybridrag.ps1", script_copy)

    scripts_dir = tmp_path / ".venv" / "Scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "Activate.ps1").write_text(
        "$env:VIRTUAL_ENV = '{}'".format(tmp_path / ".venv"),
        encoding="utf-8",
    )
    shutil.copyfile(sys.executable, scripts_dir / "python.exe")

    result = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_copy),
        ],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )

    output = ((result.stdout or "") + (result.stderr or "")).replace("\r\n", "\n")

    assert result.returncode == 0, output
    assert (
        "HybridRAG shell ready." in output
        or "=== HybridRAG Startup ===" in output
    )
    assert (
        "Project root: {}".format(tmp_path) in output
        or "Project:    {}".format(tmp_path) in output
    )
