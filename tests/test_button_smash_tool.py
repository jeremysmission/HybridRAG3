from pathlib import Path
import shutil

from tools import test_button_smash


def test_local_temp_dir_stays_under_repo_workspace():
    temp_dir = Path(test_button_smash._local_temp_dir("unit_"))
    try:
        assert temp_dir.exists()
        assert Path(".tmp_button_smash").resolve() in temp_dir.parents
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_live_backend_available_uses_boot_result_flags():
    class App:
        boot_result = type(
            "Boot",
            (),
            {"offline_available": False, "online_available": True, "warnings": []},
        )()
        query_engine = None
        indexer = None

    assert test_button_smash._live_backend_available(App()) is True


def test_backend_limit_detail_reports_unavailable_backends():
    class App:
        boot_result = type(
            "Boot",
            (),
            {
                "offline_available": False,
                "online_available": False,
                "warnings": ["Ollama health check timed out (2s)."],
            },
        )()

    detail = test_button_smash._backend_limit_detail(App())

    assert "offline backend unavailable" in detail
    assert "online backend unavailable" in detail
    assert "Ollama health check timed out" in detail
