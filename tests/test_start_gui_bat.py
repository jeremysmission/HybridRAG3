from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


if os.name != "nt":
    pytest.skip("Batch launcher tests require Windows", allow_module_level=True)


REPO_ROOT = Path(__file__).resolve().parent.parent
START_GUI_BAT = REPO_ROOT / "start_gui.bat"


def _run_batch(batch_path: Path, *args: str, cwd: Path, env: dict[str, str] | None = None):
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", str(batch_path), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=run_env,
    )
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode, output.replace("\r\n", "\n")


def _seed_fake_repo(root: Path, *, with_venv: bool) -> Path:
    shutil.copyfile(START_GUI_BAT, root / "start_gui.bat")
    gui_dir = root / "src" / "gui"
    gui_dir.mkdir(parents=True, exist_ok=True)
    (gui_dir / "launch_gui.py").write_text("print('placeholder launcher')\n", encoding="utf-8")
    if with_venv:
        scripts_dir = root / ".venv" / "Scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        (scripts_dir / "python.exe").write_text("", encoding="utf-8")
        (scripts_dir / "pythonw.exe").write_text("", encoding="utf-8")
        (scripts_dir / "activate.bat").write_text("@echo off\n", encoding="utf-8")
    return root / "start_gui.bat"


def test_start_gui_bat_dry_run_uses_script_location_as_project_root(tmp_path):
    env = {
        "HYBRIDRAG_GUI_DRY_RUN": "1",
        "HYBRIDRAG_GUI_NO_PAUSE": "1",
    }

    code, output = _run_batch(START_GUI_BAT, cwd=tmp_path, env=env)

    expected_root = str(REPO_ROOT.resolve())
    assert code == 0
    assert "GUI launcher dry run" in output
    assert "Project root: {}".format(expected_root) in output
    assert "Working directory: {}".format(expected_root) in output
    assert "Launch mode: terminal" in output


def test_start_gui_bat_dry_run_supports_detached_mode(tmp_path):
    env = {
        "HYBRIDRAG_GUI_DRY_RUN": "1",
        "HYBRIDRAG_GUI_NO_PAUSE": "1",
    }

    code, output = _run_batch(START_GUI_BAT, "--detach", cwd=tmp_path, env=env)

    assert code == 0
    assert "Launch mode: detached" in output
    assert "Launch exe:" in output
    assert "pythonw.exe" in output.lower()


def test_start_gui_bat_missing_venv_reports_plain_english_error(tmp_path):
    fake_root = tmp_path / "Repo With Spaces"
    fake_root.mkdir()
    batch_path = _seed_fake_repo(fake_root, with_venv=False)

    code, output = _run_batch(
        batch_path,
        cwd=tmp_path,
        env={"HYBRIDRAG_GUI_NO_PAUSE": "1"},
    )

    assert code == 2
    assert "virtual environment is missing" in output.lower()
    assert "Run INSTALL.bat first" in output
    assert str(fake_root) in output


def test_start_gui_bat_broken_venv_reports_rebuild_steps(tmp_path):
    fake_root = tmp_path / "Repo With Spaces"
    fake_root.mkdir()
    batch_path = _seed_fake_repo(fake_root, with_venv=True)

    code, output = _run_batch(
        batch_path,
        cwd=tmp_path,
        env={"HYBRIDRAG_GUI_NO_PAUSE": "1"},
    )

    assert code == 4
    assert "found .venv, but its python executable cannot start" in output.lower()
    assert "Remove-Item -Recurse -Force .venv" in output
    assert "py -3.12 -m venv .venv" in output


def test_start_gui_bat_dry_run_handles_space_paths_and_reports_launch_targets(tmp_path):
    fake_root = tmp_path / "Repo With Spaces"
    fake_root.mkdir()
    batch_path = _seed_fake_repo(fake_root, with_venv=True)

    code, output = _run_batch(
        batch_path,
        cwd=tmp_path,
        env={
            "HYBRIDRAG_GUI_DRY_RUN": "1",
            "HYBRIDRAG_GUI_NO_PAUSE": "1",
        },
    )

    assert code == 0
    assert "Project root: {}".format(fake_root) in output
    assert "GUI script: {}".format(fake_root / "src" / "gui" / "launch_gui.py") in output
    assert "Python exe: {}".format(fake_root / ".venv" / "Scripts" / "python.exe") in output
    assert "Launch mode: terminal" in output


def test_start_gui_bat_env_detach_switches_to_detached_mode(tmp_path):
    fake_root = tmp_path / "Repo With Spaces"
    fake_root.mkdir()
    batch_path = _seed_fake_repo(fake_root, with_venv=True)

    code, output = _run_batch(
        batch_path,
        cwd=tmp_path,
        env={
            "HYBRIDRAG_GUI_DRY_RUN": "1",
            "HYBRIDRAG_GUI_NO_PAUSE": "1",
            "HYBRIDRAG_GUI_DETACH": "1",
        },
    )

    assert code == 0
    assert "Launch mode: detached" in output
    assert "Launch exe: {}".format(fake_root / ".venv" / "Scripts" / "pythonw.exe") in output
