# ============================================================================
# Hybrid3 Enterprise Troubleshooter (tools/run_hybrid3_troubleshoot.py)
# ============================================================================
# One-shot diagnostic: collects system info, runs GUI behavioral engine,
# checks API health, captures Ollama inventory, bundles everything into
# a timestamped folder with structured JSON. The BAT file zips it.
#
# Usage: .venv\Scripts\python.exe tools\run_hybrid3_troubleshoot.py
# ============================================================================
from __future__ import annotations
import io
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root on path
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)
os.environ.setdefault("HYBRIDRAG_PROJECT_ROOT", _root)

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def _run(cmd: str) -> str:
    try:
        return subprocess.check_output(
            cmd, shell=True, text=True, stderr=subprocess.STDOUT, timeout=30,
        ).strip()
    except Exception as e:
        return f"ERROR: {e}"


def _redact(text: str) -> str:
    """Strip API keys from diagnostic output."""
    import re
    return re.sub(r'(sk-[A-Za-z0-9_-]{10,})', '[REDACTED_KEY]', text)


def collect_system(base: Path) -> dict:
    """Collect system, git, GPU, Ollama, and config info."""
    try:
        import psutil
        mem_gb = round(psutil.virtual_memory().total / 1e9, 2)
        cpu = psutil.cpu_count()
    except ImportError:
        mem_gb = "psutil_missing"
        cpu = "psutil_missing"

    system = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python_version": sys.version,
        "python_executable": sys.executable,
        "cwd": os.getcwd(),
        "memory_total_gb": mem_gb,
        "cpu_count": cpu,
        "gpu_info": _redact(_run("nvidia-smi --query-gpu=name,memory.total,memory.free,driver_version --format=csv,noheader")),
        "ollama_models": _run("ollama list"),
        "git_branch": _run("git branch --show-current"),
        "git_commit": _run("git log -1 --oneline"),
        "git_status": _run("git status --porcelain"),
        "git_remote": _run("git remote -v"),
    }
    (base / "system_info.json").write_text(json.dumps(system, indent=2), encoding="utf-8")

    # Config snapshot
    cfg_path = Path("config/default_config.yaml")
    if cfg_path.exists():
        (base / "config_snapshot.yaml").write_text(
            _redact(cfg_path.read_text(encoding="utf-8")), encoding="utf-8",
        )

    return system


def run_selftests(base: Path) -> dict:
    """Run core selftests and capture output."""
    results = {}
    py = sys.executable

    for name, script in [
        ("selftest_ollama", "tools/selftest_ollama.py"),
        ("gui_smoke", "tools/gui_smoke.py"),
        ("selftest_data_pipeline", "tools/selftest_data_pipeline.py"),
        ("selftest_gui_registry", "tools/selftest_gui_registry.py"),
        ("selftest_model_state", "tools/selftest_model_state.py"),
        ("selftest_config_integrity", "tools/selftest_config_integrity.py"),
        ("thread_guard", "tools/thread_guard.py"),
        ("event_recorder", "tools/gui_event_recorder.py"),
        ("replay_engine", "tools/gui_replay.py"),
        ("screenshot_diff", "tools/gui_screenshot.py"),
    ]:
        if not Path(script).exists():
            results[name] = {"status": "SKIP", "output": "file not found"}
            continue
        try:
            out = subprocess.check_output(
                [py, script], text=True, stderr=subprocess.STDOUT, timeout=180,
            )
            results[name] = {"status": "PASS", "output": out.strip()}
        except subprocess.CalledProcessError as e:
            results[name] = {"status": "FAIL", "output": (e.output or "").strip(), "returncode": e.returncode}
        except subprocess.TimeoutExpired:
            results[name] = {"status": "TIMEOUT", "output": "exceeded 180s"}

    (base / "selftests.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results


def run_api_health(base: Path) -> dict:
    """Check FastAPI /health endpoint via TestClient."""
    try:
        from starlette.testclient import TestClient
        from src.api.server import app
        with TestClient(app) as client:
            r = client.get("/health")
            result = {"status": r.status_code, "body": r.json()}
    except Exception as e:
        result = {"status": "ERROR", "error": str(e)}
    (base / "api_health.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def run_gui_behavioral(base: Path) -> dict:
    """Boot GUI headless and run the full behavioral engine."""
    try:
        from src.gui.testing.gui_boot import boot_headless
        from src.gui.testing.gui_engine import HybridGuiEngine

        app = boot_headless()
        engine = HybridGuiEngine(app)
        report = engine.run_all()

        # Clean up the tk app
        try:
            app.destroy()
        except Exception:
            pass

    except Exception as e:
        import traceback
        report = {
            "total_actions": 0,
            "failures": 1,
            "boot_error": str(e),
            "boot_trace": traceback.format_exc(),
        }

    (base / "gui_behavioral.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def run_compileall() -> dict:
    """Syntax-check all source files."""
    try:
        subprocess.check_output(
            [sys.executable, "-m", "compileall", "src/", "tools/", "-q"],
            text=True, stderr=subprocess.STDOUT, timeout=60,
        )
        return {"status": "PASS"}
    except subprocess.CalledProcessError as e:
        return {"status": "FAIL", "output": (e.output or "").strip()}
    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT"}


def run_matrix_coverage(base: Path) -> dict:
    """Read tools/gui_matrix.json and produce a coverage report by status."""
    matrix_path = Path("tools/gui_matrix.json")
    if not matrix_path.exists():
        report = {"error": "gui_matrix.json not found", "total": 0, "pass": 0, "fail": 0, "untested": 0}
        (base / "matrix_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report

    data = json.loads(matrix_path.read_text(encoding="utf-8"))
    entries = data.get("entries", [])
    counts = {}
    for entry in entries:
        status = entry.get("status", "UNKNOWN").upper()
        counts[status] = counts.get(status, 0) + 1

    total = len(entries)
    pass_count = counts.get("PASS", 0)
    fail_count = counts.get("FAIL", 0)
    untested_count = counts.get("UNTESTED", 0)

    report = {
        "total": total,
        "pass": pass_count,
        "fail": fail_count,
        "untested": untested_count,
        "coverage_pct": round(pass_count / total * 100, 1) if total > 0 else 0,
        "by_status": counts,
    }
    (base / "matrix_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = Path("output/troubleshoot") / ts
    base.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Troubleshoot run: {base}")
    overall_start = time.perf_counter()

    # 1) System diagnostics
    print("[1/7] Collecting system diagnostics...")
    system = collect_system(base)

    # 2) Compileall
    print("[2/7] Syntax check (compileall)...")
    compile_result = run_compileall()

    # 3) Core selftests
    print("[3/7] Running core selftests...")
    selftests = run_selftests(base)

    # 4) API health
    print("[4/7] Checking API health...")
    api = run_api_health(base)

    # 5) Pytest
    print("[5/7] Running pytest suite...")
    try:
        pytest_result = subprocess.check_output(
            [sys.executable, "-m", "pytest", "tests/",
             "--ignore=tests/test_fastapi_server.py", "-q", "--tb=line"],
            text=True, stderr=subprocess.STDOUT, timeout=300,
        ).strip()
    except subprocess.CalledProcessError as e:
        pytest_result = (e.output or "").strip()
    except subprocess.TimeoutExpired:
        pytest_result = "TIMEOUT: exceeded 300s"
    (base / "pytest_output.txt").write_text(pytest_result, encoding="utf-8")

    # 6) Matrix coverage
    print("[6/7] Generating matrix coverage report...")
    matrix = run_matrix_coverage(base)

    # 7) GUI behavioral engine
    print("[7/7] Running GUI behavioral engine...")
    gui = run_gui_behavioral(base)

    elapsed = round(time.perf_counter() - overall_start, 1)

    # Build summary
    selftest_pass = all(v["status"] == "PASS" for v in selftests.values())
    # Count real failures (not headless skips)
    gui_results = gui.get("results", [])
    gui_failures = sum(
        1 for r in gui_results
        if not r.get("invoke", {}).get("success", True)
        and not r.get("invoke", {}).get("skipped", False)
    )
    api_ok = api.get("status") == 200

    summary = {
        "diag_dir": str(base),
        "timestamp": ts,
        "elapsed_s": elapsed,
        "python": sys.version.split()[0],
        "git_branch": system.get("git_branch", "unknown"),
        "git_commit": system.get("git_commit", "unknown"),
        "compileall": compile_result["status"],
        "selftests": {k: v["status"] for k, v in selftests.items()},
        "api_health": "OK" if api_ok else str(api.get("status")),
        "gui_actions": gui.get("total_actions", 0),
        "gui_failures": gui_failures,
        "gui_p95_s": gui.get("performance", {}).get("p95_s"),
        "matrix_total": matrix.get("total", 0),
        "matrix_pass": matrix.get("pass", 0),
        "matrix_coverage_pct": matrix.get("coverage_pct", 0),
        "overall": "PASS" if (selftest_pass and gui_failures == 0 and api_ok) else "FAIL",
    }

    (base / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # Print human-readable summary
    print()
    print("=" * 50)
    print("HYBRID3 TROUBLESHOOT SUMMARY")
    print("=" * 50)
    print(f"  Dir:        {base}")
    print(f"  Elapsed:    {elapsed}s")
    print(f"  Python:     {summary['python']}")
    print(f"  Branch:     {summary['git_branch']}")
    print(f"  Commit:     {summary['git_commit']}")
    print(f"  Compileall: {summary['compileall']}")
    for k, v in summary["selftests"].items():
        print(f"  {k}: {v}")
    print(f"  API Health: {summary['api_health']}")
    print(f"  GUI Actions: {summary['gui_actions']}")
    print(f"  GUI Failures: {summary['gui_failures']}")
    if summary["gui_p95_s"] is not None:
        print(f"  GUI p95:    {summary['gui_p95_s']}s")
    print(f"  Matrix:     {summary['matrix_pass']}/{summary['matrix_total']} ({summary['matrix_coverage_pct']}%)")
    print(f"  OVERALL:    {summary['overall']}")
    print("=" * 50)

    # Write the base path for the BAT to read
    Path("output").mkdir(exist_ok=True)
    Path("output/_last_troubleshoot_dir.txt").write_text(str(base), encoding="utf-8")

    return 0 if summary["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
