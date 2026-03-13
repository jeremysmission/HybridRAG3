import threading
import time

from src.api.query_queue import QueryQueueFullError, QueryQueueTracker


def test_query_queue_disabled_by_default():
    tracker = QueryQueueTracker()

    tracker.acquire()
    snapshot = tracker.snapshot()
    assert snapshot["enabled"] is False
    assert snapshot["active_queries"] == 1
    assert snapshot["available_slots"] is None
    assert snapshot["total_started"] == 1

    tracker.release()
    snapshot = tracker.snapshot()
    assert snapshot["active_queries"] == 0
    assert snapshot["total_completed"] == 1


def test_query_queue_rejects_when_full():
    tracker = QueryQueueTracker(max_concurrent=1, max_queue=0)

    tracker.acquire()
    try:
        try:
            tracker.acquire()
            assert False, "Expected QueryQueueFullError"
        except QueryQueueFullError:
            pass
        snapshot = tracker.snapshot()
        assert snapshot["total_rejected"] == 1
        assert snapshot["last_rejected_at"] is not None
    finally:
        tracker.release()


def test_query_queue_tracks_waiting_and_releases_next():
    tracker = QueryQueueTracker(max_concurrent=1, max_queue=1)
    tracker.acquire()

    entered = threading.Event()
    acquired = threading.Event()

    def _waiter():
        entered.set()
        tracker.acquire()
        acquired.set()
        tracker.release()

    thread = threading.Thread(target=_waiter, daemon=True)
    thread.start()
    assert entered.wait(timeout=2.0)

    deadline = time.time() + 2.0
    while time.time() < deadline:
        snapshot = tracker.snapshot()
        if snapshot["waiting_queries"] == 1:
            break
        time.sleep(0.01)
    else:
        assert False, "waiting_queries never reached 1"

    tracker.release()
    assert acquired.wait(timeout=2.0)
    thread.join(timeout=2.0)

    snapshot = tracker.snapshot()
    assert snapshot["active_queries"] == 0
    assert snapshot["waiting_queries"] == 0
    assert snapshot["max_waiting_seen"] == 1
    assert snapshot["total_started"] == 2
    assert snapshot["total_completed"] == 2
