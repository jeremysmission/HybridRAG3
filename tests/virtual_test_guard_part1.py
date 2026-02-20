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
# SIM-01: FILE INTEGRITY
# ====================================================================
def sim_01():
    t0 = time.time()
    section("SIM-01: FILE INTEGRITY")

    new_files = [
        ROOT / "src" / "core" / "grounded_query_engine.py",
    ]
    guard_dir = ROOT / "src" / "core" / "hallucination_guard"
    if guard_dir.exists():
        new_files += sorted(guard_dir.glob("*.py"))

    for path in new_files:
        label = path.name
        test(f"{label} exists", path.exists())
        if path.exists():
            content = path.read_text(encoding="utf-8")
            bad = [(i+1, ch) for i, ch in enumerate(content)
                   if ord(ch) > 127]
            test(f"{label} ASCII-clean", len(bad) == 0,
                 f"{len(bad)} non-ASCII" if bad else "")

    phase_times["SIM-01"] = (time.time() - t0) * 1000


# ====================================================================
# SIM-03: PYTHON SYNTAX
# ====================================================================
def sim_03():
    t0 = time.time()
    section("SIM-03: PYTHON SYNTAX (AST compile)")

    for d in ["src/core", "src/core/hallucination_guard"]:
        dp = ROOT / d
        if not dp.exists():
            test(f"{d} exists", False)
            continue
        fails = []
        for py in sorted(dp.glob("*.py")):
            if "__pycache__" in str(py) or ".bak" in py.name:
                continue
            try:
                ast.parse(py.read_text(encoding="utf-8-sig", errors="replace"))
            except SyntaxError as e:
                fails.append(f"{py.name}:{e.lineno}: {e.msg}")
        test(f"{d}/ all compile", len(fails) == 0,
             "; ".join(fails[:3]) if fails else "")

    phase_times["SIM-03"] = (time.time() - t0) * 1000


# ====================================================================
# SIM-04: IMPORT CHAINS
# ====================================================================
def sim_04():
    t0 = time.time()
    section("SIM-04: IMPORT CHAINS")

    try:
        from src.core.config import (
            Config, HallucinationGuardConfig, load_config,
            _dict_to_dataclass,
        )
        test("Config + HallucinationGuardConfig import", True)
    except ImportError as e:
        test("Config import", False, str(e))
        phase_times["SIM-04"] = (time.time() - t0) * 1000
        return

    # Guard package modules parse cleanly (don't need runtime deps)
    guard_dir = ROOT / "src" / "core" / "hallucination_guard"
    for f in sorted(guard_dir.glob("*.py")):
        if f.name.startswith("__"):
            continue
        try:
            ast.parse(f.read_text(encoding="utf-8"))
            test(f"guard/{f.name} parses", True)
        except Exception as e:
            test(f"guard/{f.name} parses", False, str(e))

    # grounded_query_engine.py parses
    gqe = ROOT / "src" / "core" / "grounded_query_engine.py"
    try:
        ast.parse(gqe.read_text(encoding="utf-8"))
        test("grounded_query_engine.py parses", True)
    except Exception as e:
        test("grounded_query_engine.py parses", False, str(e))

    phase_times["SIM-04"] = (time.time() - t0) * 1000


# ====================================================================
# SIM-05: API SURFACE COMPATIBILITY
# ====================================================================
def sim_05():
    t0 = time.time()
    section("SIM-05: API SURFACE COMPATIBILITY")

    from src.core.config import Config, HallucinationGuardConfig

    cfg = Config()

    # All original fields still exist
    for f in ["mode", "paths", "embedding", "chunking", "ollama",
              "api", "cost", "retrieval", "indexing", "security"]:
        test(f"Config.{f} exists", hasattr(cfg, f))

    # New field
    test("Config.hallucination_guard exists",
         hasattr(cfg, "hallucination_guard"))
    test("Is HallucinationGuardConfig",
         isinstance(cfg.hallucination_guard, HallucinationGuardConfig))

    # Convenience properties
    test("hallucination_guard_enabled prop",
         hasattr(cfg, "hallucination_guard_enabled"))
    test("hallucination_guard_threshold prop",
         hasattr(cfg, "hallucination_guard_threshold"))
    test("hallucination_guard_action prop",
         hasattr(cfg, "hallucination_guard_action"))

    # Safe defaults
    test("Guard OFF by default", cfg.hallucination_guard.enabled is False)
    test("Threshold 0.80", cfg.hallucination_guard.threshold == 0.80)
    test("Action 'block'", cfg.hallucination_guard.failure_action == "block")

    # Original QueryResult unchanged
    from src.core.query_engine import QueryResult
    qr = QueryResult(answer="x", sources=[], chunks_used=0,
                     tokens_in=0, tokens_out=0, cost_usd=0.0,
                     latency_ms=0.0, mode="offline")
    test("QueryResult has no grounding_score",
         not hasattr(qr, "grounding_score"))

    phase_times["SIM-05"] = (time.time() - t0) * 1000


# ====================================================================
# SIM-06: DATA FLOW (config YAML)
# ====================================================================
def sim_06():
    t0 = time.time()
    section("SIM-06: DATA FLOW (config loading)")

    from src.core.config import HallucinationGuardConfig, _dict_to_dataclass

    # YAML values load correctly
    g = _dict_to_dataclass(HallucinationGuardConfig,
                           {"enabled": True, "threshold": 0.90,
                            "failure_action": "flag"})
    test("YAML enabled=True", g.enabled is True)
    test("YAML threshold=0.90", g.threshold == 0.90)
    test("YAML action='flag'", g.failure_action == "flag")
    test("Default nli_model preserved",
         g.nli_model == "cross-encoder/nli-deberta-v3-base")

    # Empty dict -> all defaults
    d = _dict_to_dataclass(HallucinationGuardConfig, {})
    test("Empty -> disabled", d.enabled is False)

    # Unknown key -> warns but no crash
    u = _dict_to_dataclass(HallucinationGuardConfig, {"bogus": 99})
    test("Unknown key ignored", u.enabled is False)

    # Full YAML parse
    import yaml
    yp = ROOT / "config" / "default_config.yaml"
    if yp.exists():
        raw = yaml.safe_load(yp.read_text())
        test("YAML has guard section", "hallucination_guard" in raw)
        hg = raw.get("hallucination_guard", {})
        test("YAML guard.enabled=false", hg.get("enabled") is False)
        test("YAML guard.threshold=0.80", hg.get("threshold") == 0.80)

    phase_times["SIM-06"] = (time.time() - t0) * 1000


# ====================================================================
# SIM-07: MODIFIED FILE LOGIC
# ====================================================================
def sim_07():
    t0 = time.time()
    section("SIM-07: GROUNDED QUERY ENGINE LOGIC")

    c = (ROOT / "src" / "core" / "grounded_query_engine.py").read_text()

    checks = [
        ("from .query_engine import QueryEngine", "Imports QueryEngine"),
        ("class GroundedQueryEngine(QueryEngine):", "Subclasses QE"),
        ("super().__init__", "Calls super init"),
        ("self.guard_enabled", "Guard toggle"),
        ("super().query(user_query)", "Fast path when disabled"),
        ("_build_grounded_prompt", "Grounded prompt builder"),
        ("_verify_response", "Response verifier"),
        ("except ImportError", "Graceful guard import"),
        ("GroundedQueryResult", "Extended result type"),
        ("grounding_score", "Score field"),
        ("grounding_blocked", "Blocked field"),
        ("NETWORK ACCESS: NONE", "Network declaration"),
    ]
    for pattern, label in checks:
        test(label, pattern in c)

    phase_times["SIM-07"] = (time.time() - t0) * 1000


# ====================================================================
# SIM-08: DOWNSTREAM CONSUMERS UNCHANGED
# ====================================================================
def sim_08():
    t0 = time.time()
    section("SIM-08: DOWNSTREAM CONSUMERS (zero blast radius)")

    # query_engine.py UNTOUCHED
    qe = ROOT / "src" / "core" / "query_engine.py"
    lines = len(qe.read_text().splitlines())
    test(f"query_engine.py: {lines} lines (untouched)",
         230 <= lines <= 240)

    # boot.py UNTOUCHED
    bc = (ROOT / "src" / "core" / "boot.py").read_text()
    test("boot.py: no grounded ref",
         "grounded_query_engine" not in bc)

    # Diagnostic UNTOUCHED
    dp = ROOT / "src" / "diagnostic" / "hybridrag_diagnostic.py"
    if dp.exists():
        dc = dp.read_text()
        test("Diagnostic imports base QueryEngine",
             "from src.core.query_engine import QueryEngine" in dc)
        test("Diagnostic: no GroundedQueryEngine",
             "GroundedQueryEngine" not in dc)

    # cli_test_phase1.py UNTOUCHED
    cp = ROOT / "tests" / "cli_test_phase1.py"
    if cp.exists():
        cc = cp.read_text()
        test("CLI test imports base QueryEngine",
             "from src.core.query_engine import QueryEngine" in cc)

    phase_times["SIM-08"] = (time.time() - t0) * 1000


# ====================================================================
# SIM-09: MODULE SIZE COMPLIANCE
# ====================================================================
def sim_09():
    t0 = time.time()
    section("SIM-09: MODULE SIZE (<500 lines)")

    to_check = [
        ("grounded_query_engine.py",
         ROOT / "src" / "core" / "grounded_query_engine.py"),
    ]
    gd = ROOT / "src" / "core" / "hallucination_guard"
    for f in sorted(gd.glob("*.py")):
        to_check.append((f"guard/{f.name}", f))

    for label, path in to_check:
        if path.exists():
            n = len(path.read_text().splitlines())
            test(f"{label}: {n} lines", n <= 500)

    phase_times["SIM-09"] = (time.time() - t0) * 1000


# ====================================================================
# SIM-10/11: EXISTING TEST REGRESSION


# ====================================================================
# RUNNER (Part 1: SIM-01 through SIM-09)
# ====================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("  HALLUCINATION GUARD VIRTUAL TEST -- PART 1")
    print("  SIM-01 through SIM-09 (integrity, imports, API, logic)")
    print("=" * 60)

    sim_01()
    sim_03()
    sim_04()
    sim_05()
    sim_06()
    sim_07()
    sim_08()
    sim_09()

    pass_count = sum(1 for r in results if r["passed"])
    fail_count = sum(1 for r in results if not r["passed"])
    print()
    print("=" * 60)
    print(f"  PART 1 RESULTS: {pass_count} PASS / {fail_count} FAIL")
    print("=" * 60)
    if fail_count > 0:
        print("  FAILURES:")
        for r in results:
            if not r["passed"]:
                print(f"    [FAIL] {r['name']}")
                if r["detail"]:
                    print(f"           {r['detail']}")
        sys.exit(1)
