# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the launch gui part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG v3 -- GUI Launcher (src/gui/launch_gui.py)
# ============================================================================
# WHAT: Entry point that boots the system and opens the GUI window.
# WHY:  Backend initialization (Ollama connection, VectorStore, LLMRouter)
#       takes a few seconds.  This module shows the window immediately
#       and loads backends in the background, so the user sees progress.
# HOW:  Three-phase launch:
#       Phase 1 - Eager preload: starts connecting to Ollama embedding
#                 API at module import time (before boot/config/GUI).
#       Phase 2 - Boot + config.
#       Phase 3 - Open GUI window, load remaining backends in a thread.
#       The preload runs in parallel with Phase 2.
# USAGE: python src/gui/launch_gui.py
#        or: .\tools\launch_gui.ps1 (PowerShell wrapper)
#
# STARTUP POLICY: The main HybridRAG window must always boot first. The
# first-run setup wizard is available as a helper, but it is never allowed
# to block or terminate core GUI startup.
#
# PERFORMANCE: Three tricks to minimize perceived wait:
#   1. Eager preload -- start connecting to Ollama embedder at t=0,
#      BEFORE boot/config/GUI, so the HTTP handshake overlaps with setup.
#   2. Embedder cache -- keep the Embedder across Reset clicks so the
#      Ollama connection is paid only once per process lifetime.
#   3. Warm encode -- fire a dummy embed_query() after connect so the
#      first real query pays zero lazy-init cost.
#
# INTERNET ACCESS: Depends on boot result and user mode selection.
# ============================================================================

import os
import sys
import logging
import threading
from glob import glob
from concurrent.futures import ThreadPoolExecutor

# Ensure project root is on sys.path BEFORE any src.* imports
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Set HYBRIDRAG_PROJECT_ROOT if not already set
if not os.environ.get("HYBRIDRAG_PROJECT_ROOT"):
    os.environ["HYBRIDRAG_PROJECT_ROOT"] = _project_root

from src.core.constants import DEFAULT_EMBED_DIM

# ============================================================================
# EAGER PRELOAD: start connecting to Ollama embedding API immediately,
# before boot/config/GUI.  The result is stashed in _preload_result and
# picked up by _load_backends() later.  The overlap saves ~1-2s of wall
# time by running the HTTP handshake in parallel with boot+config.
# ============================================================================

_preload_result = {}   # {"embedder": Embedder | None, "error": str | None}
_preload_done = threading.Event()
_preloaded_cfg = None  # canonical Config object cached for preload reuse


def _read_embedding_preload_settings():
    """Read preload embedding settings via canonical config loader.

    Returns (model_name, dimension). Falls back to (None, 0) so Embedder
    defaults still apply if config load is unavailable during early startup.
    """
    global _preloaded_cfg
    try:
        from src.core.config import load_config
        cfg = load_config(_project_root)
        _preloaded_cfg = cfg
        emb = getattr(cfg, "embedding", None)
        model_name = getattr(emb, "model_name", None) if emb else None
        dim = int(getattr(emb, "dimension", 0) or 0) if emb else 0
        return model_name, dim
    except Exception:
        return None, 0


def _preload_embedder():
    """Connect to Ollama embedding API as early as possible."""
    try:
        from src.core.embedder import Embedder
        model_name, dim = _read_embedding_preload_settings()
        e = Embedder(model_name=model_name, dimension=dim)
        # Warm encode: force any lazy init (tokenizer buffers, etc.)
        e.embed_query("warmup")
        _preload_result["embedder"] = e
        _preload_result["error"] = None
    except Exception as exc:
        _preload_result["embedder"] = None
        _preload_result["error"] = str(exc)
    finally:
        _preload_done.set()


_preload_thread = None


def _ensure_preload_started():
    """Start embedder preload lazily (avoids import-time side effects)."""
    global _preload_thread
    if _preload_thread is not None:
        return
    _preload_thread = threading.Thread(target=_preload_embedder, daemon=True)
    _preload_thread.start()

# ============================================================================
# Module-level embedder cache -- survives Reset clicks so the expensive
# model-load is paid once per process.  _load_backends() stores the
# Embedder here after first use; reset_backends() in app.py re-reads it.
# ============================================================================

_cached_embedder = None
_cached_embedder_lock = threading.Lock()


def _get_or_build_embedder(model_name, logger, dimension=0):
    """Return a cached Embedder if model_name matches, else build a new one."""
    global _cached_embedder

    _ensure_preload_started()

    # Try the preload first (bounded wait -- GUI must not hang if Ollama is down)
    if not _preload_done.is_set():
        logger.info("Waiting for eager preload to finish...")
    if not _preload_done.wait(timeout=5.0):
        logger.warning("[LAUNCH:PRELOAD] Eager preload did not finish within 5s; continuing without it")

    with _cached_embedder_lock:
        # Use cached if model matches
        if (_cached_embedder is not None
                and getattr(_cached_embedder, "model_name", None) is not None
                and _cached_embedder.model_name == model_name):
            logger.info("[OK] Embedder reused from cache")
            return _cached_embedder

        # Use preload result if model matches and cache is empty
        preloaded = _preload_result.get("embedder")
        if (preloaded is not None
                and getattr(preloaded, "model_name", None) is not None
                and preloaded.model_name == model_name):
            _cached_embedder = preloaded
            logger.info("[OK] Embedder loaded (from eager preload)")
            return _cached_embedder

        # Fallback: build fresh (different model_name or preload failed)
        from src.core.embedder import Embedder
        e = Embedder(model_name=model_name, dimension=dimension)
        e.embed_query("warmup")
        _cached_embedder = e
        logger.info("[OK] Embedder loaded (fresh build)")
        return _cached_embedder


def clear_embedder_cache():
    """Clear the cached embedder so the next build uses the new model.

    Called by settings_view.py when the user switches to a profile
    with a different embedding model.  Without this, reset_backends()
    would reuse the old (wrong-dimension) embedder from cache.
    """
    global _cached_embedder
    with _cached_embedder_lock:
        _cached_embedder = None


def _set_stage(app, stage_text):
    """Schedule a loading-stage update on the GUI main thread.

    Uses safe_after() because this is called from background threads.
    Direct app.after() from a non-main thread raises RuntimeError
    on some Tk builds (especially corporate Windows).
    """
    try:
        from src.gui.helpers.safe_after import safe_after
        safe_after(app, 0, lambda: (
            app.status_bar.set_loading_stage(stage_text)
            if hasattr(app, "status_bar") else None
        ))
    except Exception:
        pass


def _probe_ollama_runtime(router, config, logger):
    """Run lightweight embed/generate probes and auto-fallback on overload."""
    errors = []
    try:
        if not router or not getattr(router, "ollama", None):
            return errors
        if not router.ollama.is_available():
            return errors

        base_url = router.ollama.base_url
        client = router.ollama._client
        embed_model = getattr(
            getattr(config, "embedding", None), "model_name", "nomic-embed-text"
        ) or "nomic-embed-text"
        gen_model = str(
            getattr(getattr(config, "ollama", None), "model", "") or ""
        ).strip()
        probe_timeout = float(
            min(max(getattr(getattr(config, "ollama", None), "timeout_seconds", 30), 8), 20)
        )

        # Probe embeddings endpoint (fast health signal for retrieval path).
        try:
            r = client.post(
                "{}/api/embed".format(base_url),
                json={"model": embed_model, "input": ["startup probe"]},
                timeout=probe_timeout,
            )
            r.raise_for_status()
        except Exception as e:
            errors.append(
                "Ollama embed probe failed (model '{}'): {}"
                .format(embed_model, str(e))
            )

        # Probe generate endpoint for the configured chat model.
        def _probe_generate(model_name):
            """Plain-English: This function handles probe generate."""
            r = client.post(
                "{}/api/generate".format(base_url),
                json={
                    "model": model_name,
                    "prompt": "Reply with: OK",
                    "stream": False,
                    "keep_alive": getattr(config.ollama, "keep_alive", -1),
                    "options": {
                        "temperature": 0.0,
                        "num_predict": 8,
                        "num_ctx": min(
                            int(getattr(config.ollama, "context_window", 4096) or 4096),
                            4096,
                        ),
                    },
                },
                timeout=probe_timeout,
            )
            r.raise_for_status()

        gen_error = None
        if gen_model:
            try:
                _probe_generate(gen_model)
            except Exception as e:
                gen_error = e

        # Auto-fallback for known heavy default when runtime is overloaded.
        if gen_error is not None:
            from src.core.model_identity import canonicalize_model_name
            cfg_canon = canonicalize_model_name(gen_model)
            if cfg_canon.startswith("phi4:14b"):
                available = router.ollama._available_models() or []
                available_canon = {
                    canonicalize_model_name(m): m for m in available
                }
                fallback = (
                    available_canon.get("phi4-mini")
                    or available_canon.get("phi4-mini:latest")
                )
                if fallback:
                    try:
                        config.ollama.model = fallback
                        _probe_generate(fallback)
                        logger.warning(
                            "[WARN] Ollama startup fallback applied: %s -> %s",
                            gen_model, fallback,
                        )
                        errors.append(
                            "Ollama model probe failed for '{}' ({}). "
                            "Auto-fallback switched to '{}'."
                            .format(gen_model, str(gen_error), fallback)
                        )
                        gen_error = None
                    except Exception:
                        # Keep original error report if fallback also fails.
                        pass

        if gen_error is not None:
            errors.append(
                "Ollama generate probe failed (model '{}'): {}"
                .format(gen_model, str(gen_error))
            )
    except Exception as e:
        logger.debug("ollama_runtime_probe_failed: %s", e)
    return errors


def _partition_backend_startup_issues(issues):
    """Split modal-worthy init failures from non-blocking startup warnings."""
    warning_prefixes = (
        "Ollama embed probe failed",
        "Ollama generate probe failed",
        "Ollama model probe failed",
    )
    blocking = []
    warnings = []
    for issue in issues or []:
        text = str(issue or "")
        if text.startswith(warning_prefixes):
            warnings.append(text)
        else:
            blocking.append(text)
    return blocking, warnings


def _present_backend_startup_issues(app, logger, init_issues):
    """Surface startup issues without blocking boot on non-fatal probes."""
    blocking_errors, startup_warnings = _partition_backend_startup_issues(init_issues)

    if hasattr(app, "status_bar"):
        app.status_bar.router = getattr(app, "router", None)
        first_issue = (blocking_errors or startup_warnings or [None])[0]
        if first_issue:
            app.status_bar.set_init_error(first_issue)
        app.status_bar.force_refresh()

    if startup_warnings:
        logger.warning(
            "[LAUNCH:WARN] Non-blocking backend startup warnings: %s",
            " | ".join(startup_warnings),
        )

    if blocking_errors:
        from tkinter import messagebox

        messagebox.showwarning(
            "Backend Init Errors",
            "Some components failed to initialize:\n\n"
            + "\n".join("  - {}".format(e) for e in blocking_errors)
            + "\n\nThe system may have limited functionality."
            "\nCheck that Ollama is running and the database"
            " path exists.",
        )


def _load_backends(app, logger):
    """Load heavy backends in a background thread, then attach to the GUI."""
    config = app.config
    query_engine = None
    indexer = None
    router = None
    store = None
    embedder = None
    init_errors = []

    try:
        logger.info("Loading backends (this may take a moment)...")
        from src.core.vector_store import VectorStore
        from src.core.llm_router import LLMRouter
        from src.core.grounded_query_engine import GroundedQueryEngine
        from src.core.chunker import Chunker
        from src.core.indexer import Indexer

        model_name = getattr(
            getattr(config, "embedding", None), "model_name",
            "nomic-embed-text"
        )

        # -- Parallel phase: VectorStore, Embedder, LLMRouter --
        def _init_store():
            """Plain-English: This function handles init store."""
            _set_stage(app, "VectorStore...")
            db_path = getattr(getattr(config, "paths", None), "database", "")
            if not db_path:
                logger.warning("[WARN] No database path configured")
                return None
            db_dir = os.path.dirname(db_path) or "."
            os.makedirs(db_dir, exist_ok=True)
            s = VectorStore(
                db_path=db_path,
                embedding_dim=getattr(
                    getattr(config, "embedding", None), "dimension", DEFAULT_EMBED_DIM
                ),
                embedding_model=getattr(
                    getattr(config, "embedding", None), "model_name", ""
                ),
            )
            s.connect()
            logger.info("[OK] Vector store connected")
            return s

        def _init_embedder():
            """Plain-English: This function handles init embedder."""
            _set_stage(app, "Embedder...")
            embed_dim = getattr(
                getattr(config, "embedding", None), "dimension", 0
            )
            return _get_or_build_embedder(model_name, logger, dimension=embed_dim)

        def _init_router():
            """Plain-English: This function handles init router."""
            _set_stage(app, "LLM Router...")
            boot_creds = getattr(
                getattr(app, "boot_result", None), "credentials", None,
            )
            r = LLMRouter(config, credentials=boot_creds)
            logger.info("[OK] LLM router ready")
            return r

        _INIT_TIMEOUT = 60  # seconds -- fail fast, don't hang GUI

        with ThreadPoolExecutor(max_workers=3) as pool:
            fut_store = pool.submit(_init_store)
            fut_embedder = pool.submit(_init_embedder)
            fut_router = pool.submit(_init_router)

            try:
                store = fut_store.result(timeout=_INIT_TIMEOUT)
            except Exception as e:
                logger.warning("[LAUNCH:INIT] VectorStore init failed: %s", e)
                init_errors.append("Database: {}".format(e))
            try:
                embedder = fut_embedder.result(timeout=_INIT_TIMEOUT)
            except Exception as e:
                logger.warning("[LAUNCH:INIT] Embedder init failed: %s", e)
                init_errors.append("Embedder: {}".format(e))
            try:
                router = fut_router.result(timeout=_INIT_TIMEOUT)
            except Exception as e:
                logger.warning("[LAUNCH:INIT] LLMRouter init failed: %s", e)
                init_errors.append("LLM Router: {}".format(e))

        # -- Ollama runtime probes (embed + generate) + overload fallback --
        _set_stage(app, "Probing Ollama runtime...")
        init_errors.extend(_probe_ollama_runtime(router, config, logger))

        # -- Sequential phase: assemble QueryEngine + Indexer --
        _set_stage(app, "QueryEngine...")
        if store and embedder:
            query_engine = GroundedQueryEngine(config, store, embedder, router)
            logger.info("[OK] Query engine ready")

            chunker = Chunker(config.chunking)
            indexer = Indexer(config, store, embedder, chunker)
            logger.info("[OK] Indexer ready")

    except Exception as e:
        logger.warning("[LAUNCH:INIT] Backend loading partial: %s", e)

    # Attach backends to the GUI (schedule on main thread)
    def _attach():
        """Plain-English: This function handles attach."""
        app.query_engine = query_engine
        app.indexer = indexer
        app.router = router
        if hasattr(app, "query_panel"):
            app.query_panel.query_engine = query_engine
            app.query_panel.set_ready(query_engine is not None)
        if hasattr(app, "index_panel"):
            app.index_panel.indexer = indexer
            app.index_panel.set_ready(indexer is not None)
        logger.info("[OK] Backends attached to GUI")
        _present_backend_startup_issues(app, logger, init_errors)

        # -- IBIT: stepped verification display then final badge --
        _run_ibit_sequence(app, config, query_engine, indexer, router, logger)

        # Safety net: if IBIT hasn't cleared loading after 90s, force clear.
        # Prevents the GUI from being stuck in "Loading..." forever.
        def _loading_timeout():
            """Plain-English: This function handles loading timeout."""
            if hasattr(app, "status_bar") and app.status_bar._loading:
                logger.warning("[WARN] Loading timeout -- forcing ready state")
                app.status_bar.set_ibit_result(0, 0, [])

        app.after(90_000, _loading_timeout)

    try:
        from src.gui.helpers.safe_after import safe_after
        safe_after(app, 0, _attach)
    except Exception as e:
        logger.debug("safe_after() failed during backend attach: %s", e)


def _run_ibit_sequence(app, config, query_engine, indexer, router, logger):
    """Run IBIT checks with stepped status-bar display.

    Shows each check name briefly (labor illusion / time distortion),
    then settles on the final pass/fail badge.  The stepped display
    uses 150ms holds per check -- fast enough to feel snappy, slow
    enough for each name to register visually (research: 100-200ms
    is the perceptual sweet spot for sequential items).
    """
    from src.core.ibit import run_ibit

    STEP_DELAY_MS = 150  # Per-check display hold (ms)

    def _do_ibit():
        """Plain-English: This function handles do ibit."""
        from src.gui.helpers.safe_after import safe_after
        try:
            results = run_ibit(config, query_engine, indexer, router)
            # Schedule stepped display on main thread (safe_after
            # because _do_ibit runs in a daemon thread)
            safe_after(app, 0, lambda: _step_display(app, results, 0, STEP_DELAY_MS))
        except Exception as e:
            logger.warning("[WARN] IBIT failed: %s", e)
            # Safety net: clear loading state even on crash
            try:
                safe_after(app, 0, lambda: app.status_bar.set_ibit_result(0, 0, []))
            except Exception:
                pass

    # Run checks in background to avoid blocking GUI
    import threading
    threading.Thread(target=_do_ibit, daemon=True).start()


def _step_display(app, results, idx, delay_ms):
    """Show one IBIT check name at a time, then the final result.

    Each step holds for delay_ms before advancing.  This creates
    the labor illusion: rapid-fire check names make the system
    feel thorough and the transition from loading to ready feel
    deliberate rather than abrupt.
    """
    if not hasattr(app, "status_bar"):
        return
    if idx < len(results):
        app.status_bar.set_ibit_stage(results[idx].name)
        app.after(delay_ms, lambda: _step_display(app, results, idx + 1, delay_ms))
    else:
        # All steps shown -- display final badge
        passed = sum(1 for r in results if r.ok)
        app.status_bar.set_ibit_result(passed, len(results), results)

        # Start CBIT (continuous health monitoring, every 60s)
        app.status_bar.start_cbit(query_engine=app.query_engine)


def _step(msg):
    """Print a startup step to console immediately (no logging dependency).

    Guaranteed visible in the terminal even if logging is not configured yet.
    Use this to diagnose startup hangs -- the last printed step is the one
    that is stuck.
    """
    import time
    ts = time.strftime("%H:%M:%S")
    print("[STARTUP {}] {}".format(ts, msg), flush=True)


def _sync_path_widgets_from_config(app, config):
    """Push path values from a freshly loaded config into visible path widgets."""
    paths = getattr(config, "paths", None)
    source = getattr(paths, "source_folder", "") if paths is not None else ""
    database = getattr(paths, "database", "") if paths is not None else ""
    index_dir = os.path.dirname(database) if database else "(not set)"

    index_panel = getattr(app, "index_panel", None)
    if index_panel is not None:
        try:
            index_panel.config = config
            index_panel.folder_var.set(source or "")
            index_panel.index_var.set(index_dir)
        except Exception:
            pass

    admin_panel = getattr(app, "_admin_panel", None)
    paths_panel = getattr(admin_panel, "_paths_panel", None) if admin_panel is not None else None
    if paths_panel is not None:
        try:
            paths_panel.source_var.set(source or "")
            paths_panel.index_var.set(os.path.dirname(database) if database else "")
            if hasattr(paths_panel, "_refresh_info"):
                paths_panel._refresh_info()
        except Exception:
            pass


def _apply_wizard_config_reload(app, logger):
    """Reload config after setup wizard completion and propagate it into the app."""
    try:
        from src.core.config import load_config

        new_config = load_config(_project_root)
        app.reload_config(new_config)
        _sync_path_widgets_from_config(app, new_config)
        _step("Step 3.5: config reloaded after setup wizard")
    except Exception as exc:
        logger.warning("[LAUNCH:WIZARD] Config reload after setup failed: %s", exc)
        _step("Step 3.5: config reload after wizard FAILED: {}".format(exc))


def _start_backend_thread(app, logger):
    """Start background backend loading once the startup path is ready."""
    if getattr(app, "_backend_reload_thread", None) is not None:
        if app._backend_reload_thread.is_alive():
            logger.info("[LAUNCH] Backend thread already running")
            return

    _step("Step 4: starting backend thread...")
    backend_thread = threading.Thread(
        target=_load_backends, args=(app, logger), daemon=True,
    )
    backend_thread.start()
    app._backend_reload_thread = backend_thread
    _step("Step 4 done: backend thread running")


def _launch_setup_wizard_after_boot(app, logger):
    """Launch the setup wizard manually after the main window exists.

    The GUI must remain alive even if the wizard is cancelled or crashes.
    Startup never calls this helper automatically.
    """
    try:
        from src.gui.panels.setup_wizard import SetupWizard, needs_setup

        if not needs_setup(_project_root):
            _step("Step 3.5: setup wizard no longer needed; continuing startup")
            _start_backend_thread(app, logger)
            return

        _step("Step 3.5: launching setup wizard after GUI boot...")
        from src.gui.tk_utils import force_foreground

        wiz = SetupWizard(app, _project_root)
        force_foreground(wiz, parent=app)
        wiz.grab_set()
        app.wait_window(wiz)

        if getattr(wiz, "completed", False):
            _step("Step 3.5: setup wizard completed")
            _apply_wizard_config_reload(app, logger)
        else:
            logger.info("[LAUNCH:WIZARD] Setup wizard dismissed; app remains open")
            _step("Step 3.5: setup wizard dismissed; continuing with main app")
    except Exception as exc:
        logger.warning("[LAUNCH:WIZARD] Setup wizard failed post-launch: %s", exc)
        _step("Step 3.5 FAILED: setup wizard crashed after boot: {}".format(exc))
        try:
            from tkinter import messagebox

            messagebox.showwarning(
                "Setup Wizard Failed",
                "HybridRAG booted, but the setup wizard failed to open cleanly.\n\n"
                "The main app will stay open. Configure Source and Index paths "
                "from Settings > Admin if needed.\n\n"
                "Error: {}".format(str(exc)[:200]),
                parent=app,
            )
        except Exception:
            pass
    finally:
        _start_backend_thread(app, logger)


def _sanitize_tk_env():
    """Auto-heal common Tk startup failures caused by bad environment vars.

    Corporate images and shell profiles sometimes leave stale TCL/TK/PYTHONHOME
    values that point at removed Python installs. When that happens, tkinter
    crashes with "can't find a usable tk.tcl/init.tcl". We defensively clear
    invalid paths and set known-good defaults from sys.base_prefix if present.
    """
    # Clear invalid explicit overrides first.
    for var, must_have in (
        ("TCL_LIBRARY", "init.tcl"),
        ("TK_LIBRARY", "tk.tcl"),
    ):
        val = os.environ.get(var)
        if not val:
            continue
        marker = os.path.join(val, must_have)
        if not (os.path.isdir(val) and os.path.isfile(marker)):
            _step("Tk env fix: clearing invalid {}={}".format(var, val))
            os.environ.pop(var, None)

    pyhome = os.environ.get("PYTHONHOME")
    if pyhome and not os.path.isdir(pyhome):
        _step("Tk env fix: clearing invalid PYTHONHOME={}".format(pyhome))
        os.environ.pop("PYTHONHOME", None)

    # If no explicit override is set, use the interpreter's bundled Tcl/Tk.
    tcl_root = os.path.join(sys.base_prefix, "tcl")
    if os.path.isdir(tcl_root):
        if not os.environ.get("TCL_LIBRARY"):
            tcl_dirs = sorted(glob(os.path.join(tcl_root, "tcl*")))
            for d in tcl_dirs:
                if os.path.isfile(os.path.join(d, "init.tcl")):
                    os.environ["TCL_LIBRARY"] = d
                    _step("Tk env fix: set TCL_LIBRARY={}".format(d))
                    break
        if not os.environ.get("TK_LIBRARY"):
            tk_dirs = sorted(glob(os.path.join(tcl_root, "tk*")))
            for d in tk_dirs:
                if os.path.isfile(os.path.join(d, "tk.tcl")):
                    os.environ["TK_LIBRARY"] = d
                    _step("Tk env fix: set TK_LIBRARY={}".format(d))
                    break


def main():
    """Boot config, open GUI immediately, load backends in background."""
    _step("main() entered")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger("gui_launcher")
    _sanitize_tk_env()

    # NOTE: _preload_thread is already running (started at module load).
    # While we boot + load config + build the GUI (~2s), the Ollama
    # embedder connection is being established in parallel.

    # -- Step 1: Boot the system (lightweight -- config + creds + gate) --
    _step("Step 1: boot_hybridrag()...")
    boot_result = None
    config = None

    try:
        from src.core.boot import boot_hybridrag
        _step("Step 1a: boot module imported")
        boot_result = boot_hybridrag()
        _step("Step 1b: boot complete (success={})".format(
            boot_result.success if boot_result else "None"))
        if boot_result and not boot_result.success:
            for err in boot_result.errors:
                _step("  boot error: {}".format(err))
    except Exception as e:
        _step("Step 1 FAILED: {}".format(e))

    # -- Step 2: Load config --
    _step("Step 2: load_config()...")
    try:
        from src.core.config import load_config
        config = load_config(_project_root)
        _step("Step 2 done (mode={})".format(config.mode))
    except Exception as e:
        _step("Step 2 FAILED: {}".format(e))
        from src.core.config import Config
        config = Config()

    # -- Step 2.5: First-run setup status (informational only) --
    _step("Step 2.5: checking needs_setup()...")
    from src.gui.panels.setup_wizard import needs_setup
    wizard_needed = needs_setup(_project_root)
    _step("Step 2.5: needs_setup = {}".format(wizard_needed))

    # -- Step 3: Open GUI immediately --
    _step("Step 3: creating HybridRAGApp...")
    from src.gui.app import HybridRAGApp

    app = HybridRAGApp(
        boot_result=boot_result,
        config=config,
    )
    _step("Step 3 done: GUI window created")

    # -- Step 3.5/4: Always boot the GUI; never auto-launch the wizard --
    if wizard_needed:
        logger.warning(
            "[LAUNCH:WIZARD] Setup appears incomplete, but automatic wizard "
            "launch is disabled during startup so the main GUI can boot."
        )
        _step("Step 3.5: setup needed but startup wizard is skipped")
    _start_backend_thread(app, logger)

    # -- Step 5: Run the GUI event loop --
    _step("Step 5: entering mainloop() -- GUI should be visible now")
    app.mainloop()
    _step("Step 5 done: mainloop exited")


def _detach_and_exit():
    """Re-launch this script as a detached process and exit immediately.

    On Windows, DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP severs the
    child from the parent console so the GUI survives terminal close.
    Uses pythonw.exe (no console window) when available.
    """
    import subprocess
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    exe = pythonw if os.path.isfile(pythonw) else sys.executable

    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

    subprocess.Popen(
        [exe, "-m", "src.gui.launch_gui"],
        creationflags=flags,
        cwd=_project_root,
        close_fds=True,
    )
    sys.exit(0)


if __name__ == "__main__":
    if "--detach" in sys.argv:
        _detach_and_exit()
    main()
