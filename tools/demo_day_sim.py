#!/usr/bin/env python3
# === NON-PROGRAMMER GUIDE ===
# Purpose: One-command "demo day readiness check" that verifies everything
#          works before you present. Run this 30 minutes before any demo.
#
# Usage:
#   python tools/demo_day_sim.py              (quick preflight only)
#   python tools/demo_day_sim.py --full       (preflight + live queries)
#   python tools/demo_day_sim.py --online     (include online API test)
#
# What it checks:
#   1. Config loads correctly
#   2. Database exists and has chunks indexed
#   3. Ollama is running (offline model available)
#   4. Embedder is functional
#   5. Retriever finds documents for demo questions
#   6. (--full) Runs actual queries and checks answers
#   7. (--online) Tests online API connectivity
#
# Output: Plain-English GO / NO-GO verdict with specific fix instructions.
# ============================
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def _ts():
    return datetime.now().strftime("%H:%M:%S")


def _print_header():
    print()
    print("=" * 64)
    print("  HYBRIDRAG DEMO DAY READINESS CHECK")
    print("  {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    print("=" * 64)
    print()


def _print_result(label, ok, detail=""):
    tag = "[OK]" if ok else "[FAIL]"
    line = "  {} {}".format(tag, label)
    if detail:
        line += " -- {}".format(detail)
    print(line)


class DemoReadinessChecker:

    def __init__(self, full=False, online=False):
        self.full = full
        self.online = online
        self.results = []
        self.config = None
        self.bundle = None
        self.creds = None

    def record(self, label, ok, detail="", critical=True):
        self.results.append({
            "label": label,
            "ok": ok,
            "detail": detail,
            "critical": critical,
        })
        _print_result(label, ok, detail)
        return ok

    def check_config(self):
        print("[{}] Checking configuration...".format(_ts()))
        try:
            from src.core.bootstrap.boot_coordinator import BootCoordinator
            bc = BootCoordinator(str(PROJECT_ROOT))
            boot_report = bc.run()
            self.config = boot_report.config
            mode = getattr(self.config, "mode", "unknown")
            self.record("Config loaded", True, "mode={}".format(mode))
            return True
        except Exception as e:
            self.record("Config loaded", False, str(e))
            return False

    def check_database(self):
        print("[{}] Checking database...".format(_ts()))
        if not self.config:
            self.record("Database exists", False, "no config loaded")
            return False
        try:
            db_path = getattr(self.config.paths, "database", "")
            if not db_path or not Path(db_path).exists():
                self.record("Database exists", False,
                            "path={} not found".format(db_path))
                return False

            import sqlite3
            conn = sqlite3.connect(db_path)
            cursor = conn.execute("SELECT COUNT(*) FROM chunks")
            chunk_count = cursor.fetchone()[0]
            conn.close()

            ok = chunk_count > 0
            self.record("Database has chunks", ok,
                        "{:,} chunks indexed".format(chunk_count))

            if chunk_count < 1000:
                self.record("Index size adequate", False,
                            "only {:,} chunks -- expected ~39,000+".format(chunk_count),
                            critical=False)
            else:
                self.record("Index size adequate", True,
                            "{:,} chunks".format(chunk_count),
                            critical=False)
            return ok
        except Exception as e:
            self.record("Database exists", False, str(e))
            return False

    def check_ollama(self):
        print("[{}] Checking Ollama...".format(_ts()))
        try:
            import httpx
            resp = httpx.get("http://127.0.0.1:11434/api/tags", timeout=5.0)
            if resp.status_code != 200:
                self.record("Ollama running", False,
                            "status={}".format(resp.status_code))
                return False

            data = resp.json()
            models = [m.get("name", "") for m in data.get("models", [])]
            model_names = ", ".join(models[:5]) if models else "none"
            self.record("Ollama running", True,
                        "{} models: {}".format(len(models), model_names))

            # Check for phi4-mini or phi4:14b
            has_phi = any("phi4" in m.lower() for m in models)
            has_nomic = any("nomic" in m.lower() for m in models)
            self.record("Phi4 model available", has_phi,
                        "needed for offline queries",
                        critical=True)
            self.record("Nomic embedder available", has_nomic,
                        "needed for search",
                        critical=True)
            return True
        except Exception as e:
            self.record("Ollama running", False,
                        "Is Ollama started? Error: {}".format(e))
            return False

    def check_backend(self):
        print("[{}] Loading backend (retriever, embedder)...".format(_ts()))
        try:
            from src.core.bootstrap.backend_loader import BackendLoader
            from src.core.bootstrap.boot_coordinator import BootCoordinator
            bc = BootCoordinator(str(PROJECT_ROOT))
            boot_report = bc.run()
            self.config = boot_report.config

            loader = BackendLoader(
                config=self.config,
                boot_result=boot_report.boot_result,
            )
            self.bundle = loader.load(timeout_seconds=60)
            errors = len(self.bundle.init_errors)
            self.record("Backend loaded", errors == 0,
                        "{} init errors".format(errors))
            if self.bundle.init_errors:
                for err in self.bundle.init_errors:
                    print("    [WARN] {}".format(err))
            return errors == 0
        except Exception as e:
            self.record("Backend loaded", False, str(e))
            return False

    def check_retrieval(self):
        print("[{}] Testing retrieval on demo questions...".format(_ts()))
        if not (self.bundle and self.bundle.query_engine):
            self.record("Retrieval functional", False, "no query engine")
            return False

        test_queries = [
            ("What is the operating frequency range?", "frequency"),
            ("How do leaders and managers differ?", "leader"),
            ("calibration intervals quarterly review", "calibration"),
        ]

        all_ok = True
        retriever = self.bundle.query_engine.retriever
        for query, keyword in test_queries:
            try:
                results = retriever.search(query)
                found = len(results)
                has_keyword = any(
                    keyword.lower() in str(getattr(r, "text", "")).lower()
                    for r in results
                )
                ok = found > 0 and has_keyword
                self.record(
                    "Retrieval: '{}'".format(query[:40]),
                    ok,
                    "{} chunks, keyword '{}' {}".format(
                        found, keyword, "found" if has_keyword else "MISSING"),
                )
                if not ok:
                    all_ok = False
            except Exception as e:
                self.record("Retrieval: '{}'".format(query[:40]),
                            False, str(e))
                all_ok = False
        return all_ok

    def check_offline_query(self):
        if not self.full:
            return True
        print("[{}] Running live offline query...".format(_ts()))
        if not (self.bundle and self.bundle.query_engine):
            self.record("Offline query", False, "no query engine")
            return False

        saved_mode = getattr(self.config, "mode", None)
        try:
            self.config.mode = "offline"
            t0 = time.perf_counter()
            result = self.bundle.query_engine.query(
                "What is the operating frequency range?"
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000
            answer = (result.answer or "")[:100].replace("\n", " ")
            has_answer = len(answer.strip()) > 20
            no_error = not result.error
            ok = has_answer and no_error
            self.record("Offline query", ok,
                        "{:.0f}ms, chunks={}, answer='{}'...".format(
                            elapsed_ms, result.chunks_used, answer))
            return ok
        except Exception as e:
            self.record("Offline query", False, str(e))
            return False
        finally:
            if self.config and saved_mode is not None:
                self.config.mode = saved_mode

    def check_online_query(self):
        if not self.online:
            self.record("Online query", True,
                        "skipped (use --online to test)",
                        critical=False)
            return True

        print("[{}] Testing online API connectivity...".format(_ts()))
        try:
            from src.security.credentials import resolve_credentials
            self.creds = resolve_credentials(use_cache=True)
            has_key = getattr(self.creds, "has_key", False)
            has_endpoint = bool(getattr(self.creds, "endpoint", ""))
            self.record("API credentials", has_key and has_endpoint,
                        "key={} endpoint={}".format(has_key, has_endpoint))

            if not (has_key and has_endpoint):
                self.record("Online query", False,
                            "no credentials configured")
                return False
        except Exception as e:
            self.record("API credentials", False, str(e))
            return False

        if not (self.bundle and self.bundle.query_engine):
            self.record("Online query", False, "no query engine")
            return False

        saved_mode = getattr(self.config, "mode", None)
        try:
            from src.core.network_gate import configure_gate
            from src.core.llm_router import LLMRouter, invalidate_deployment_cache

            self.config.mode = "online"
            configure_gate(
                mode="online",
                api_endpoint=self.creds.endpoint or "",
                allowed_prefixes=[],
            )
            invalidate_deployment_cache()
            online_router = LLMRouter(self.config, credentials=self.creds)
            self.bundle.query_engine.llm_router = online_router

            t0 = time.perf_counter()
            result = self.bundle.query_engine.query(
                "How do leaders and managers differ?"
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000
            answer = (result.answer or "")[:100].replace("\n", " ")
            has_answer = len(answer.strip()) > 20
            no_error = not result.error
            ok = has_answer and no_error
            self.record("Online query", ok,
                        "{:.0f}ms, tokens_in={}, tokens_out={}, "
                        "cost=${:.4f}, answer='{}'...".format(
                            elapsed_ms, result.tokens_in,
                            result.tokens_out, result.cost_usd, answer))
            return ok
        except Exception as e:
            self.record("Online query", False, str(e))
            return False
        finally:
            try:
                from src.core.network_gate import configure_gate
                from src.core.llm_router import invalidate_deployment_cache
                if self.config and saved_mode is not None:
                    self.config.mode = saved_mode
                configure_gate(mode=saved_mode or "offline")
                invalidate_deployment_cache()
            except Exception:
                pass

    def check_rehearsal_pack(self):
        print("[{}] Validating rehearsal pack...".format(_ts()))
        try:
            from src.tools.demo_rehearsal_pack import load_demo_rehearsal_pack
            from src.tools.demo_rehearsal_audit import (
                audit_demo_rehearsal_pack,
                resolve_demo_rehearsal_db_path,
            )
            pack = load_demo_rehearsal_pack()
            db_path = resolve_demo_rehearsal_db_path(
                project_root=PROJECT_ROOT,
            )
            report = audit_demo_rehearsal_pack(pack, db_path=db_path)
            passed = report["summary"]["passed"]
            total = report["summary"]["checks"]
            ok = passed == total
            self.record("Rehearsal pack", ok,
                        "{}/{} evidence targets found".format(passed, total))
            return ok
        except Exception as e:
            self.record("Rehearsal pack", False, str(e))
            return False

    def check_query_decomposition(self):
        print("[{}] Verifying query decomposition...".format(_ts()))
        try:
            from src.core.query_engine import _decompose_query
            parts = _decompose_query(
                "What is the frequency range and what are the calibration intervals?"
            )
            ok = len(parts) >= 2
            self.record("Query decomposition", ok,
                        "split into {} parts".format(len(parts)),
                        critical=False)
            return ok
        except Exception as e:
            self.record("Query decomposition", False, str(e),
                        critical=False)
            return False

    def check_crag_config(self):
        print("[{}] Verifying CRAG configuration...".format(_ts()))
        try:
            from src.core.mode_config import MODE_RUNTIME_DEFAULTS
            online_ret = MODE_RUNTIME_DEFAULTS["online"]["retrieval"]
            has_crag = online_ret.get("corrective_retrieval", False)
            threshold = online_ret.get("corrective_threshold", 0)
            ok = has_crag and threshold > 0
            self.record("CRAG auto-enabled (online)", ok,
                        "corrective_retrieval={}, threshold={}".format(
                            has_crag, threshold),
                        critical=False)
            return ok
        except Exception as e:
            self.record("CRAG config", False, str(e), critical=False)
            return False

    def run(self):
        _print_header()

        # Phase 1: Preflight (fast, no queries)
        print("--- PHASE 1: PREFLIGHT ---")
        print()
        config_ok = self.check_config()
        if not config_ok:
            self._print_verdict()
            return

        self.check_database()
        self.check_ollama()
        self.check_rehearsal_pack()
        self.check_query_decomposition()
        self.check_crag_config()

        # Phase 2: Backend + Retrieval (slower)
        print()
        print("--- PHASE 2: BACKEND ---")
        print()
        backend_ok = self.check_backend()
        if backend_ok:
            self.check_retrieval()

        # Phase 3: Live queries (only with --full or --online)
        # Each method saves/restores config.mode in its own finally block.
        if self.full or self.online:
            print()
            print("--- PHASE 3: LIVE QUERIES ---")
            print()
            if self.full:
                self.check_offline_query()
            if self.online:
                self.check_online_query()

        self._print_verdict()

    def _print_verdict(self):
        print()
        print("=" * 64)

        critical_fails = [
            r for r in self.results if not r["ok"] and r["critical"]
        ]
        warnings = [
            r for r in self.results if not r["ok"] and not r["critical"]
        ]
        total = len(self.results)
        passed = sum(1 for r in self.results if r["ok"])

        if not critical_fails:
            print("  VERDICT: GO FOR DEMO  ({}/{} checks passed)".format(
                passed, total))
            if warnings:
                print()
                print("  Warnings (non-blocking):")
                for w in warnings:
                    print("    - {} -- {}".format(w["label"], w["detail"]))
        else:
            print("  VERDICT: NOT READY  ({}/{} checks passed)".format(
                passed, total))
            print()
            print("  Critical issues (must fix before demo):")
            for f in critical_fails:
                print("    - {} -- {}".format(f["label"], f["detail"]))
            print()
            print("  How to fix:")
            for f in critical_fails:
                fix = _suggest_fix(f["label"])
                if fix:
                    print("    {} -> {}".format(f["label"], fix))

        print()
        print("=" * 64)
        print()


def _suggest_fix(label):
    fixes = {
        "Config loaded": "Check config/config.yaml exists and is valid YAML",
        "Database exists": "Run: rag-index (point at your source folder first)",
        "Database has chunks": "Run: rag-index to build the search index",
        "Ollama running": "Start Ollama: open a terminal and run 'ollama serve'",
        "Phi4 model available": "Run: ollama pull phi4-mini",
        "Nomic embedder available": "Run: ollama pull nomic-embed-text",
        "Backend loaded": "Check Ollama is running and database path is correct",
        "API credentials": "Store credentials: rag-store-endpoint, then set API key in Windows Credential Manager",
        "Offline query": "Check Ollama model is loaded: ollama run phi4-mini",
        "Online query": "Check API key and endpoint are correct in credential store",
        "Rehearsal pack": "Run: python tools/demo_rehearsal_audit.py for details",
    }
    for key, fix in fixes.items():
        if key in label:
            return fix
    return ""


def main():
    parser = argparse.ArgumentParser(
        description="Demo day readiness check -- run 30 minutes before presenting.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run live offline queries (slower, more thorough).",
    )
    parser.add_argument(
        "--online",
        action="store_true",
        help="Also test online API connectivity and query.",
    )
    args = parser.parse_args()

    checker = DemoReadinessChecker(full=args.full, online=args.online)
    checker.run()

    critical_fails = [
        r for r in checker.results if not r["ok"] and r["critical"]
    ]
    return 1 if critical_fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
