from pathlib import Path
import shutil

from tools import gui_demo_smoke


def test_gui_demo_smoke_local_temp_dir_stays_under_repo_workspace():
    temp_dir = Path(gui_demo_smoke._local_temp_dir("unit_"))
    try:
        assert temp_dir.exists()
        assert Path(".tmp_gui_demo_smoke").resolve() in temp_dir.parents
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_gui_demo_smoke_answer_backend_uses_boot_flags():
    class App:
        boot_result = type(
            "Boot",
            (),
            {"offline_available": False, "online_available": True, "warnings": []},
        )()

    assert gui_demo_smoke._answer_backend_available(App()) is True


def test_gui_demo_smoke_backend_limit_detail_reports_warning():
    class App:
        boot_result = type(
            "Boot",
            (),
            {
                "offline_available": False,
                "online_available": False,
                "warnings": ["Ollama generate probe failed (model 'phi4:14b-q4_K_M'): timed out"],
            },
        )()

    detail = gui_demo_smoke._backend_limit_detail(App())

    assert "offline generate backend unavailable" in detail
    assert "online answer backend unavailable" in detail
    assert "Ollama generate probe failed" in detail
