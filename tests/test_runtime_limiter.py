# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies behavior for the runtime limiter area and protects against regressions.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
import threading
import time
from src.core.runtime_limits import RuntimeLimiter, RuntimePolicy

def test_runtime_limiter_limits_queries():
    limiter = RuntimeLimiter(RuntimePolicy(max_concurrent_queries=1, max_concurrent_embeddings=1))
    started = []
    finished = []

    def worker(i):
        with limiter.query_slot():
            started.append(i)
            time.sleep(0.2)
            finished.append(i)

    t1 = threading.Thread(target=worker, args=(1,))
    t2 = threading.Thread(target=worker, args=(2,))
    t1.start(); time.sleep(0.05); t2.start()
    t1.join(); t2.join()

    # With max_concurrent_queries=1, the second cannot finish before first releases.
    assert finished[0] == 1
    assert finished[1] == 2
