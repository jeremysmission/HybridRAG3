# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies scheduled-index cadence tracking and launch decisions.
# What to read first: Start at the top-level tests; they use the public tracker/helper API.
# Inputs: Temp directories, fake state objects, and deterministic timestamps.
# Outputs: Assertions on schedule snapshots and due-run launch behavior.
# Safety notes: No real index job or thread loop runs in these tests.
# ============================

from types import SimpleNamespace

from src.api.index_schedule import IndexScheduleTracker, maybe_launch_scheduled_index


def test_index_schedule_tracker_from_env_uses_interval_and_source(monkeypatch):
    monkeypatch.setenv("HYBRIDRAG_INDEX_SCHEDULE_INTERVAL_SECONDS", "900")
    monkeypatch.setenv("HYBRIDRAG_INDEX_SCHEDULE_SOURCE_FOLDER", "/scheduled/source")

    tracker = IndexScheduleTracker.from_env("/default/source")

    snapshot = tracker.snapshot(indexing_active=False, now=0.0)
    assert snapshot["enabled"] is True
    assert snapshot["interval_seconds"] == 900
    assert snapshot["source_folder"] == "/scheduled/source"
    assert snapshot["last_status"] == "idle"


def test_index_schedule_tracker_from_env_accepts_minutes_compat(monkeypatch):
    monkeypatch.delenv("HYBRIDRAG_INDEX_SCHEDULE_INTERVAL_SECONDS", raising=False)
    monkeypatch.setenv("HYBRIDRAG_INDEX_SCHEDULE_INTERVAL_MINUTES", "15")

    tracker = IndexScheduleTracker.from_env("/default/source")

    snapshot = tracker.snapshot(indexing_active=False, now=0.0)
    assert snapshot["enabled"] is True
    assert snapshot["interval_seconds"] == 900


def test_index_schedule_tracker_respects_explicit_disable(monkeypatch):
    monkeypatch.setenv("HYBRIDRAG_INDEX_SCHEDULE_ENABLED", "0")
    monkeypatch.setenv("HYBRIDRAG_INDEX_SCHEDULE_INTERVAL_SECONDS", "900")

    tracker = IndexScheduleTracker.from_env("/default/source")

    snapshot = tracker.snapshot(indexing_active=False, now=0.0)
    assert snapshot["enabled"] is False
    assert snapshot["last_status"] == "disabled"


def test_maybe_launch_scheduled_index_starts_due_run_and_records_completion(tmp_path):
    tracker = IndexScheduleTracker(interval_seconds=60, source_folder=str(tmp_path))
    tracker.created_at = tracker.created_at.replace(year=1970, month=1, day=1, hour=0, minute=0, second=0)
    state = SimpleNamespace(
        index_schedule=tracker,
        indexing_active=False,
        config=SimpleNamespace(paths=SimpleNamespace(source_folder=str(tmp_path))),
    )
    captured = {}

    def _fake_start_job(source_folder, on_complete=None, trigger="manual"):
        captured["source_folder"] = source_folder
        captured["on_complete"] = on_complete
        captured["trigger"] = trigger
        return True

    launched = maybe_launch_scheduled_index(state, _fake_start_job, now=61.0)

    assert launched is True
    assert captured["source_folder"] == str(tmp_path)
    assert captured["trigger"] == "scheduled"
    running = tracker.snapshot(indexing_active=True, now=61.0)
    assert running["last_status"] == "running"
    assert running["last_trigger"] == "scheduled"
    assert running["total_runs"] == 1

    tracker.note_run_finished(success=True, now=62.0)
    completed = tracker.snapshot(indexing_active=False, now=62.0)
    assert completed["last_status"] == "completed"
    assert completed["total_success"] == 1
    assert completed["total_failed"] == 0
    assert completed["next_run_at"] is not None


def test_maybe_launch_scheduled_index_records_missing_source_failure(tmp_path):
    missing = tmp_path / "missing"
    tracker = IndexScheduleTracker(interval_seconds=300, source_folder=str(missing))
    tracker.created_at = tracker.created_at.replace(year=1970, month=1, day=1, hour=0, minute=0, second=0)
    state = SimpleNamespace(
        index_schedule=tracker,
        indexing_active=False,
        config=SimpleNamespace(paths=SimpleNamespace(source_folder=str(missing))),
    )

    launched = maybe_launch_scheduled_index(state, lambda *_args, **_kwargs: True, now=301.0)

    assert launched is False
    snapshot = tracker.snapshot(indexing_active=False, now=301.0)
    assert snapshot["last_status"] == "failed"
    assert "not found" in snapshot["last_error"].lower()
    assert snapshot["total_runs"] == 1
    assert snapshot["total_failed"] == 1


def test_snapshot_uses_windows_safe_utc_timestamps(tmp_path):
    tracker = IndexScheduleTracker(interval_seconds=60, source_folder=str(tmp_path))
    tracker.created_at = tracker.created_at.replace(year=1970, month=1, day=1, hour=0, minute=0, second=0)
    tracker.note_run_started(now=6.0)
    tracker.note_run_finished(success=True, now=12.0)

    snapshot = tracker.snapshot(indexing_active=False, now=12.0)

    assert snapshot["last_started_at"] == "1970-01-01T00:00:06Z"
    assert snapshot["last_finished_at"] == "1970-01-01T00:00:12Z"


def test_tracker_can_pause_and_resume_schedule(tmp_path):
    tracker = IndexScheduleTracker(interval_seconds=300, source_folder=str(tmp_path))

    tracker.pause(now=30.0)
    paused = tracker.snapshot(indexing_active=False, now=30.0)
    assert paused["enabled"] is False
    assert paused["last_status"] == "paused"
    assert paused["next_run_at"] is None

    tracker.resume(now=60.0)
    resumed = tracker.snapshot(indexing_active=False, now=60.0)
    assert resumed["enabled"] is True
    assert resumed["last_status"] == "idle"
    assert resumed["last_trigger"] == "admin_resume"
    assert resumed["next_run_at"] == "1970-01-01T00:06:00Z"
