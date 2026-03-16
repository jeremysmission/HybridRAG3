# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies behavior for the runtime limiter area and protects against regressions.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
import threading
from src.core.runtime_limits import RuntimeLimiter, RuntimePolicy

def test_runtime_limiter_limits_queries():
    limiter = RuntimeLimiter(RuntimePolicy(max_concurrent_queries=1, max_concurrent_embeddings=1))
    finished = []

    # Events for deterministic synchronization (no sleep needed)
    t1_acquired = threading.Event()   # fired when worker 1 holds the slot
    t1_release = threading.Event()    # tells worker 1 it can release the slot

    def worker1():
        with limiter.query_slot():
            t1_acquired.set()         # signal: slot is held
            t1_release.wait()         # hold slot until told to release
            finished.append(1)

    def worker2():
        t1_acquired.wait()            # wait until worker 1 holds the slot
        with limiter.query_slot():    # blocks until worker 1 releases
            finished.append(2)

    t1 = threading.Thread(target=worker1)
    t2 = threading.Thread(target=worker2)
    t1.start()
    t2.start()

    # Worker 1 holds the slot; worker 2 is blocked on acquire
    t1_acquired.wait(timeout=5)
    t1_release.set()                  # let worker 1 finish

    t1.join(timeout=5)
    t2.join(timeout=5)

    # With max_concurrent_queries=1, worker 2 cannot finish before worker 1 releases.
    assert finished == [1, 2]
