import pytest

from src.api.storage_protection import (
    build_storage_protection_snapshot,
    enforce_storage_protection,
)


def test_storage_protection_snapshot_is_disabled_without_roots(monkeypatch, tmp_path):
    monkeypatch.delenv("HYBRIDRAG_PROTECTED_STORAGE_ROOTS", raising=False)
    monkeypatch.delenv("HYBRIDRAG_PROTECTED_DATA_ROOTS", raising=False)
    monkeypatch.delenv("HYBRIDRAG_REQUIRE_PROTECTED_STORAGE", raising=False)
    database_path = tmp_path / "data" / "hybridrag.sqlite3"

    snapshot = build_storage_protection_snapshot(str(database_path))

    assert snapshot["mode"] == "disabled"
    assert snapshot["required"] is False
    assert snapshot["roots"] == []
    assert snapshot["tracked_paths"] == [
        str(database_path.resolve()),
        str((tmp_path / "data" / "hybridrag_query_history.sqlite3").resolve()),
    ]
    assert snapshot["protected_paths"] == []
    assert snapshot["unprotected_paths"] == snapshot["tracked_paths"]
    assert snapshot["all_paths_protected"] is False
    assert "advisory" in snapshot["summary"].lower()


def test_storage_protection_snapshot_marks_paths_under_configured_root(monkeypatch, tmp_path):
    protected_root = tmp_path / "protected"
    database_path = protected_root / "store" / "hybridrag.sqlite3"
    monkeypatch.setenv("HYBRIDRAG_PROTECTED_STORAGE_ROOTS", str(protected_root))
    monkeypatch.delenv("HYBRIDRAG_REQUIRE_PROTECTED_STORAGE", raising=False)

    snapshot = build_storage_protection_snapshot(str(database_path))

    assert snapshot["mode"] == "advisory"
    assert snapshot["required"] is False
    assert snapshot["roots"] == [str(protected_root.resolve())]
    assert snapshot["tracked_paths"] == [
        str(database_path.resolve()),
        str((protected_root / "store" / "hybridrag_query_history.sqlite3").resolve()),
    ]
    assert snapshot["protected_paths"] == snapshot["tracked_paths"]
    assert snapshot["unprotected_paths"] == []
    assert snapshot["all_paths_protected"] is True
    assert "all tracked data paths" in snapshot["summary"].lower()


def test_enforce_storage_protection_raises_when_required_paths_are_outside_roots(monkeypatch, tmp_path):
    outside_path = tmp_path / "outside" / "hybridrag.sqlite3"
    protected_root = tmp_path / "protected"
    monkeypatch.setenv("HYBRIDRAG_PROTECTED_STORAGE_ROOTS", str(protected_root))
    monkeypatch.setenv("HYBRIDRAG_REQUIRE_PROTECTED_STORAGE", "1")

    with pytest.raises(RuntimeError, match="outside the configured protected roots"):
        enforce_storage_protection(str(outside_path))
