from __future__ import annotations
import os, sys, subprocess, time, json

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
LAUNCH = os.path.join(ROOT, "src", "gui", "launch_gui.py")

def main() -> int:
    env = os.environ.copy()
    # Force deterministic working dir and pythonpath
    env["PYTHONPATH"] = ROOT

    # IMPORTANT: do NOT set TCL_LIBRARY/TK_LIBRARY here yet -- first run "as-is"
    p = subprocess.Popen([PY, LAUNCH], cwd=ROOT, env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True)
    try:
        time.sleep(8.0)
        # if it exits early, capture output
        if p.poll() is not None:
            out = p.stdout.read() if p.stdout else ""
            print("EXITED_EARLY code=", p.returncode)
            print(out)
            return 2
        print("RUNNING_OK_8S")
        return 0
    finally:
        try:
            p.terminate()
            time.sleep(1.0)
        except Exception:
            pass
        try:
            p.kill()
        except Exception:
            pass

if __name__ == "__main__":
    raise SystemExit(main())
