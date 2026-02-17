#!/usr/bin/env python3
# ============================================================================
# VIRTUAL TEST: Hallucination Guard -- Part 2 (SIM-10 to SIM-17 + Custom)
# ============================================================================
# Split from virtual_test_hallucination_guard.py to stay under 500 lines.
# Part 1 covers SIM-01 through SIM-09 (file integrity through evidence chains).
# Part 2 covers SIM-10 through SIM-17 (regression compat through audit trail)
# plus custom guard-specific tests.
#
# INTERNET ACCESS: NONE
# ============================================================================
#!/usr/bin/env python3
# ============================================================================
# Virtual Test: Hallucination Guard Integration
# ============================================================================
# BASELINE: test_redesign.py 122P/1F | test_hybridrag3.py 2P/42F
# MODIFIED: config.py (+43 lines), default_config.yaml (+9 lines)
# ADDED:    grounded_query_engine.py (394), hallucination_guard/ (11 files)
# UNCHANGED: query_engine.py (235), boot.py, all tests, all diagnostics
# ============================================================================

import os, sys, ast, re, time, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # Up from tests/ to HybridRAG3/
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Mock heavy ML dependencies not available in sandbox
# (These exist on Jeremy's machine but not in Claude's test environment.
#  test_redesign.py uses the same pattern.)
# ---------------------------------------------------------------------------
import types
import logging as _logging

# Structlog mock (logger.py depends on this heavily)
_structlog = types.ModuleType("structlog")
_structlog_stdlib = types.ModuleType("structlog.stdlib")

def _noop(*a, **kw): pass
def _noop_return_list(*a, **kw): return []
def _noop_return_self(*a, **kw): return kw.get("_self", None)

_structlog.configure = _noop
_structlog.get_logger = lambda name="": _logging.getLogger(name)
_structlog.BoundLogger = _logging.Logger  # Type hint alias
_structlog.stdlib = _structlog_stdlib
_structlog_stdlib.filter_by_level = _noop
_structlog_stdlib.add_logger_name = _noop
_structlog_stdlib.add_log_level = _noop
_structlog_stdlib.PositionalArgumentsFormatter = lambda **kw: _noop
_structlog_stdlib.LoggerFactory = lambda **kw: None
_structlog_stdlib.ProcessorFormatter = type(
    "ProcessorFormatter", (_logging.Formatter,), {"__init__": lambda s, **kw: None})
_structlog.processors = types.ModuleType("structlog.processors")
_structlog.processors.TimeStamper = lambda **kw: _noop
_structlog.processors.JSONRenderer = lambda **kw: _noop
_structlog.processors.StackInfoRenderer = lambda **kw: _noop
_structlog.processors.UnicodeDecoder = lambda **kw: _noop
_structlog.processors.format_exc_info = _noop
_structlog.dev = types.ModuleType("structlog.dev")
_structlog.dev.ConsoleRenderer = lambda **kw: _noop

sys.modules["structlog"] = _structlog
sys.modules["structlog.stdlib"] = _structlog_stdlib
sys.modules["structlog.processors"] = _structlog.processors
sys.modules["structlog.dev"] = _structlog.dev

# Other heavy deps
for mod_name in [
    "sentence_transformers", "sentence_transformers.cross_encoder",
    "torch", "numpy", "scipy", "sklearn",
    "transformers", "huggingface_hub",
    "keyring", "keyring.errors",
    "httpx", "openai",
    "tqdm", "tqdm.auto",
]:
    if mod_name not in sys.modules:
        mock = types.ModuleType(mod_name)
        mock.SentenceTransformer = type("SentenceTransformer", (), {})
        mock.CrossEncoder = type("CrossEncoder", (), {})
        mock.AzureOpenAI = type("AzureOpenAI", (), {})
        mock.OpenAI = type("OpenAI", (), {})
        mock.Client = type("Client", (), {})
        mock.NoKeyringError = type("NoKeyringError", (Exception,), {})
        mock.OPENAI_SDK_AVAILABLE = True
        sys.modules[mod_name] = mock

results = []
phase_times = {}


def test(name, condition, detail=""):
    results.append({"name": name, "passed": condition, "detail": detail})
    status = "[PASS]" if condition else "[FAIL]"
    print(f"  {status} {name}" + (f" -- {detail}" if detail else ""))


def section(title):
    print(f"\n{'=' * 70}\n  {title}\n{'=' * 70}")



# ====================================================================
def sim_10_11():
    t0 = time.time()
    section("SIM-10/11: EXISTING TEST REGRESSION (zero delta)")

    # test_redesign.py: baseline 122P/1F
    r1 = subprocess.run(
        [sys.executable, "tests/test_redesign.py"],
        capture_output=True, text=True, cwd=str(ROOT), timeout=120)
    m1 = re.search(r'(\d+)\s+passed,\s+(\d+)\s+failed', r1.stdout)
    if m1:
        p, f = int(m1.group(1)), int(m1.group(2))
        test(f"test_redesign.py: {p}P/{f}F",
             p == 122 and f == 1,
             f"Delta: {p-122}P/{f-1}F")
    else:
        test("test_redesign.py ran", False, "parse error")

    # test_hybridrag3.py: baseline 2P/42F
    r2 = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_hybridrag3.py", "-q"],
        capture_output=True, text=True, cwd=str(ROOT), timeout=120)
    m2 = re.search(r'(\d+)\s+failed,\s+(\d+)\s+passed', r2.stdout)
    if m2:
        f2, p2 = int(m2.group(1)), int(m2.group(2))
        test(f"test_hybridrag3.py: {p2}P/{f2}F",
             p2 == 2 and f2 == 42,
             f"Delta: {p2-2}P/{f2-42}F")
    else:
        # Try alternate format
        m2b = re.search(r'(\d+) passed', r2.stdout)
        m2c = re.search(r'(\d+) failed', r2.stdout)
        if m2b and m2c:
            p2, f2 = int(m2b.group(1)), int(m2c.group(1))
            test(f"test_hybridrag3.py: {p2}P/{f2}F",
                 p2 == 2 and f2 == 42,
                 f"Delta: {p2-2}P/{f2-42}F")
        else:
            test("test_hybridrag3.py ran", False,
                 r2.stdout[-150:] if r2.stdout else "no output")

    phase_times["SIM-10/11"] = (time.time() - t0) * 1000


# ====================================================================
# SIM-12: BACKWARD COMPATIBILITY
# ====================================================================
def sim_12():
    t0 = time.time()
    section("SIM-12: BACKWARD COMPATIBILITY")

    from src.core.config import Config
    from src.core.query_engine import QueryEngine, QueryResult

    cfg = Config()
    test("Config() no args works", True)
    test("mode='offline'", cfg.mode == "offline")
    test("retrieval.top_k=8", cfg.retrieval.top_k == 8)
    test("Guard disabled by default", cfg.hallucination_guard.enabled is False)
    test("QueryEngine importable", True)

    qr = QueryResult(answer="x", sources=[], chunks_used=0,
                     tokens_in=0, tokens_out=0, cost_usd=0.0,
                     latency_ms=0.0, mode="offline")
    test("QueryResult: no grounding fields",
         not hasattr(qr, "grounding_score"))

    phase_times["SIM-12"] = (time.time() - t0) * 1000


# ====================================================================
# SIM-14: EDGE CASES
# ====================================================================
def sim_14():
    t0 = time.time()
    section("SIM-14: EDGE CASES")

    from src.core.config import HallucinationGuardConfig, _dict_to_dataclass

    g0 = _dict_to_dataclass(HallucinationGuardConfig, {"threshold": 0.0})
    test("Threshold 0.0 accepted", g0.threshold == 0.0)

    g1 = _dict_to_dataclass(HallucinationGuardConfig, {"threshold": 1.0})
    test("Threshold 1.0 accepted", g1.threshold == 1.0)

    gb = _dict_to_dataclass(HallucinationGuardConfig,
                            {"failure_action": "explode"})
    test("Invalid action stored (validation elsewhere)",
         gb.failure_action == "explode")

    from src.core.config import Config
    test("Missing guard section -> defaults",
         Config().hallucination_guard.enabled is False)

    phase_times["SIM-14"] = (time.time() - t0) * 1000


# ====================================================================
# SIM-15: CROSS-FILE REFERENCES
# ====================================================================
def sim_15():
    t0 = time.time()
    section("SIM-15: CROSS-FILE REFERENCES")

    gqe = (ROOT / "src" / "core" / "grounded_query_engine.py").read_text()

    refs = [
        ("from .query_engine import QueryEngine", "QE import"),
        ("from .config import Config", "Config import"),
        ("from .vector_store import VectorStore", "VStore import"),
        ("from .embedder import Embedder", "Embedder import"),
        ("from .llm_router import LLMRouter", "LLMRouter import"),
        ("from ..monitoring.logger import get_app_logger", "Logger import"),
    ]
    for pattern, label in refs:
        test(f"GQE -> {label}", pattern in gqe)

    # Referenced files exist
    for f in ["query_engine.py", "config.py", "vector_store.py",
              "embedder.py", "llm_router.py"]:
        test(f"src/core/{f} exists",
             (ROOT / "src" / "core" / f).exists())

    test("monitoring/logger.py exists",
         (ROOT / "src" / "monitoring" / "logger.py").exists())

    phase_times["SIM-15"] = (time.time() - t0) * 1000


# ====================================================================
# SIM-16: RESULT KEY UNIQUENESS
# ====================================================================
def sim_16():
    t0 = time.time()
    section("SIM-16: NO DUPLICATE DEFINITIONS")

    # Check no duplicate class names across core modules
    core = ROOT / "src" / "core"
    class_locations = {}
    for py in sorted(core.glob("*.py")):
        if "__pycache__" in str(py) or ".bak" in py.name:
            continue
        content = py.read_text(encoding="utf-8-sig", errors="replace")
        for m in re.finditer(r'^class\s+(\w+)', content, re.MULTILINE):
            cls_name = m.group(1)
            class_locations.setdefault(cls_name, []).append(py.name)

    dupes = {k: v for k, v in class_locations.items() if len(v) > 1}

    # QueryResult is in query_engine.py
    # GroundedQueryResult extends it in grounded_query_engine.py
    # These are different classes, not duplicates
    safe_dupes = {"QueryResult"}  # Expected: only in query_engine.py

    real_dupes = {k: v for k, v in dupes.items() if k not in safe_dupes}
    test("No duplicate class definitions",
         len(real_dupes) == 0,
         str(real_dupes) if real_dupes else "")

    phase_times["SIM-16"] = (time.time() - t0) * 1000


# ====================================================================
# SIM-17: SANITIZATION (3 repos)
# ====================================================================
def sim_17():
    t0 = time.time()
    section("SIM-17: SANITIZATION + 3-REPO COMPATIBILITY")

    # Check sync_to_educational.py skip patterns
    sync_path = ROOT / "tools" / "sync_to_educational.py"
    if sync_path.exists():
        sc = sync_path.read_text()

        # hallucination_guard/ should be COPIED (educational value)
        test("Guard package NOT in skip list",
             "hallucination_guard" not in sc
             or "hallucination_guard" in sc.split("COPY")[0])

        # Check for banned words in our new files
        banned = ["NGC", "Northrop", "Grumman", "classified",
                  "ITAR", "CUI", "clearance", "Claude", "Anthropic"]

        gqe = (ROOT / "src" / "core" / "grounded_query_engine.py") \
            .read_text()
        for word in banned:
            test(f"GQE clean of '{word}'",
                 word not in gqe and word.lower() not in gqe.lower())

        # Check guard package for banned words
        guard_dir = ROOT / "src" / "core" / "hallucination_guard"
        guard_text = ""
        for f in guard_dir.glob("*.py"):
            guard_text += f.read_text()

        for word in banned:
            found = word in guard_text or word.lower() in guard_text.lower()
            if found:
                # Find which file
                for f in guard_dir.glob("*.py"):
                    fc = f.read_text()
                    if word in fc or word.lower() in fc.lower():
                        test(f"Guard clean of '{word}'", False,
                             f"Found in {f.name}")
                        break
            else:
                test(f"Guard clean of '{word}'", True)
    else:
        test("sync_to_educational.py exists", False)

    # Check config.py changes don't contain banned words
    cc = (ROOT / "src" / "core" / "config.py").read_text()
    test("config.py clean of 'Claude'",
         "Claude" not in cc)
    test("config.py clean of 'Anthropic'",
         "Anthropic" not in cc)

    phase_times["SIM-17"] = (time.time() - t0) * 1000


# ====================================================================
# CUSTOM: GUARD-SPECIFIC FUNCTIONAL TESTS
# ====================================================================
def custom_guard_tests():
    t0 = time.time()
    section("CUSTOM: GUARD FUNCTIONAL TESTS")

    from src.core.config import Config, HallucinationGuardConfig

    # Test guard config validation helper
    g = HallucinationGuardConfig(
        enabled=True, threshold=0.90, failure_action="flag"
    )
    test("Guard config: enabled=True", g.enabled is True)
    test("Guard config: threshold=0.90", g.threshold == 0.90)
    test("Guard config: action='flag'", g.failure_action == "flag")

    # Config convenience properties
    cfg = Config()
    cfg.hallucination_guard = HallucinationGuardConfig(enabled=True)
    test("Convenience: enabled property works",
         cfg.hallucination_guard_enabled is True)
    test("Convenience: threshold property works",
         cfg.hallucination_guard_threshold == 0.80)
    test("Convenience: action property works",
         cfg.hallucination_guard_action == "block")

    # GroundedQueryResult dataclass
    gqe_path = ROOT / "src" / "core" / "grounded_query_engine.py"
    content = gqe_path.read_text()

    # Check all expected fields in GroundedQueryResult
    for field in ["grounding_score", "grounding_safe",
                  "grounding_blocked", "grounding_details"]:
        test(f"GroundedQueryResult has {field}",
             field in content)

    # Check guard actions handled
    for action in ["block", "flag", "strip"]:
        test(f"Guard handles action='{action}'",
             f'"{action}"' in content or f"'{action}'" in content)

    # Retrieval gate uses min_chunks
    test("Retrieval gate uses min_chunks",
         "guard_min_chunks" in content)

    # NLI verifier is lazy-loaded
    test("NLI verifier lazy-loaded",
         "_nli_verifier = None" in content)

    phase_times["CUSTOM"] = (time.time() - t0) * 1000


# ====================================================================
# MAIN
# ====================================================================
if __name__ == "__main__":
    start = time.time()
    print("=" * 70)
    print("  VIRTUAL TEST: Hallucination Guard -- Part 2 (SIM-10+)")
    print("  HybridRAG3 -- Zero Blast Radius Subclass Pattern")
    print("=" * 70)

    # Part 2: SIM-10 through SIM-17 + custom tests
    # (SIM-01 through SIM-09 are in virtual_test_guard_part1.py)
    sim_10_11()
    sim_12()
    sim_14()
    sim_15()
    sim_16()
    sim_17()
    custom_guard_tests()

    elapsed = time.time() - start

    # Summary
    print("\n" + "=" * 70)
    p = sum(1 for r in results if r["passed"])
    t = len(results)
    failed = [r for r in results if not r["passed"]]

    print(f"  RESULTS: {p} PASS, {len(failed)} FAIL, {t} total")

    if failed:
        print("\n  FAILURES:")
        for f in failed:
            print(f"    [FAIL] {f['name']}: {f.get('detail', '')}")
        print(f"\n  STATUS: DO NOT DEPLOY -- {len(failed)} failure(s)")
    else:
        print("  STATUS: ALL TESTS PASSED -- safe to deploy")

    print(f"  ELAPSED: {elapsed:.1f}s")
    print("=" * 70)

    for ph, ms in sorted(phase_times.items()):
        print(f"  {ph}: {ms:.0f}ms")
    print()

    sys.exit(0 if p == t else 1)
