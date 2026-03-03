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
#       Phase 2 - Boot + config + optional setup wizard (2-3s).
#       Phase 3 - Open GUI window, load remaining backends in a thread.
#       The preload runs in parallel with Phase 2.
# USAGE: python src/gui/launch_gui.py
#        or: .\tools\launch_gui.ps1 (PowerShell wrapper)
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
_preloaded_yaml_cfg = None  # raw YAML dict from default_config.yaml, cached for reuse


def _read_embedding_model_from_config():
    """Quick YAML read to get embedding.model_name before full boot.

    Returns the configured model name, or None to let Embedder use its
    class-level DEFAULT_MODEL.  This is intentionally lightweight --
    just a YAML parse, no config object construction.
    """
    global _preloaded_yaml_cfg
    try:
        import yaml
        cfg_path = os.path.join(_project_root, "config", "default_config.yaml")
        with open(cfg_path, "r") as f:
            cfg = yaml.safe_load(f) or {}
        # Overlay user_overrides.yaml on top of defaults
        ovr_path = os.path.join(_project_root, "config", "user_overrides.yaml")
        if os.path.isfile(ovr_path):
            with open(ovr_path, "r") as f:
                ovr = yaml.safe_load(f) or {}
            from src.core.config import _deep_merge
            cfg = _deep_merge(cfg, ovr)
        _preloaded_yaml_cfg = cfg
        return cfg.get("embedding", {}).get("model_name") or None
    except Exception:
        return None


def _preload_embedder():
    """Connect to Ollama embedding API as early as possible."""
    try:
        from src.core.embedder import Embedder
        model_name = _read_embedding_model_from_config()
        dim = 0
        if _preloaded_yaml_cfg:
            dim = _preloaded_yaml_cfg.get("embedding", {}).get("dimension", 0)
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

    # Try the preload first (bounded wait -- GUI must not hang if Ollama is down)
    if not _preload_done.is_set():
        logger.info("Waiting for eager preload to finish...")
    if not _preload_done.wait(timeout=5.0):
        logger.warning("[WARN] Eager preload did not finish within 5s; continuing without it")

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
            _set_stage(app, "Embedder...")
            embed_dim = getattr(
                getattr(config, "embedding", None), "dimension", 0
            )
            return _get_or_build_embedder(model_name, logger, dimension=embed_dim)

        def _init_router():
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
                logger.warning("[WARN] VectorStore init failed: %s", e)
                init_errors.append("Database: {}".format(e))
            try:
                embedder = fut_embedder.result(timeout=_INIT_TIMEOUT)
            except Exception as e:
                logger.warning("[WARN] Embedder init failed: %s", e)
                init_errors.append("Embedder: {}".format(e))
            try:
                router = fut_router.result(timeout=_INIT_TIMEOUT)
            except Exception as e:
                logger.warning("[WARN] LLMRouter init failed: %s", e)
                init_errors.append("LLM Router: {}".format(e))

        # -- Ollama warmup: pre-load model weights into memory --
        if router and getattr(router, "ollama", None) and router.ollama.is_available():
            _set_stage(app, "Warming up model...")
            try:
                router.ollama._client.post(
                    "{}/api/generate".format(router.ollama.base_url),
                    json={
                        "model": config.ollama.model,
                        "prompt": "hi",
                        "stream": False,
                        "keep_alive": getattr(config.ollama, "keep_alive", -1),
                        "options": router.ollama._build_options(),
                    },
                    timeout=30,
                )
                logger.info("[OK] Ollama model warmed up")
            except Exception as e:
                logger.debug("[WARN] Ollama warmup skipped: %s", e)

        # -- Sequential phase: assemble QueryEngine + Indexer --
        _set_stage(app, "QueryEngine...")
        if store and embedder:
            query_engine = GroundedQueryEngine(config, store, embedder, router)
            logger.info("[OK] Query engine ready")

            chunker = Chunker(config.chunking)
            indexer = Indexer(config, store, embedder, chunker)
            logger.info("[OK] Indexer ready")

    except Exception as e:
        logger.warning("[WARN] Backend loading partial: %s", e)

    # Attach backends to the GUI (schedule on main thread)
    def _attach():
        app.query_engine = query_engine
        app.indexer = indexer
        app.router = router
        if hasattr(app, "query_panel"):
            app.query_panel.query_engine = query_engine
            app.query_panel.set_ready(query_engine is not None)
        if hasattr(app, "index_panel"):
            app.index_panel.indexer = indexer
            app.index_panel.set_ready(indexer is not None)
        if hasattr(app, "status_bar"):
            app.status_bar.router = router
            if init_errors:
                app.status_bar.set_init_error(init_errors[0])
            app.status_bar.force_refresh()
        logger.info("[OK] Backends attached to GUI")

        # Show init errors to user so they know what failed
        if init_errors:
            from tkinter import messagebox
            messagebox.showwarning(
                "Backend Init Errors",
                "Some components failed to initialize:\n\n"
                + "\n".join("  - {}".format(e) for e in init_errors)
                + "\n\nThe system may have limited functionality."
                "\nCheck that Ollama is running and the database"
                " path exists.",
            )

        # -- IBIT: stepped verification display then final badge --
        _run_ibit_sequence(app, config, query_engine, indexer, router, logger)

        # Safety net: if IBIT hasn't cleared loading after 90s, force clear.
        # Prevents the GUI from being stuck in "Loading..." forever.
        def _loading_timeout():
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

    # -- Step 2.5: First-run setup wizard --
    _step("Step 2.5: checking needs_setup()...")
    from src.gui.panels.setup_wizard import needs_setup
    wizard_needed = needs_setup(_project_root)
    _step("Step 2.5: needs_setup = {}".format(wizard_needed))
    if wizard_needed:
        _step("Step 2.5: launching setup wizard...")
        import tkinter as _tk
        from src.gui.theme import apply_ttk_styles, current_theme
        _tmp_root = _tk.Tk()
        # DO NOT withdraw() -- a withdrawn parent makes transient
        # Toplevels invisible on corporate Windows builds.
        # Instead: make the host window tiny + transparent.
        _tmp_root.title("HybridRAG (Setup Host)")
        _tmp_root.geometry("1x1+0+0")
        try:
            _tmp_root.attributes("-alpha", 0.0)
        except Exception:
            pass
        _tmp_root.deiconify()
        _tmp_root.update_idletasks()
        apply_ttk_styles(current_theme())

        from src.gui.panels.setup_wizard import SetupWizard
        from src.gui.tk_utils import force_foreground
        wiz = SetupWizard(_tmp_root, _project_root)
        force_foreground(wiz, parent=_tmp_root)
        wiz.grab_set()
        _step("Step 2.5: wizard open -- WAITING FOR USER TO CLOSE IT")
        _tmp_root.wait_window(wiz)
        _tmp_root.destroy()

        if not wiz.completed:
            _step("Step 2.5: wizard cancelled -- exiting")
            sys.exit(0)

        # Reload config with wizard-written values
        _step("Step 2.5: reloading config after wizard...")
        try:
            config = load_config(_project_root)
            _step("Step 2.5: config reloaded (mode={})".format(config.mode))
        except Exception as e:
            _step("Step 2.5: config reload FAILED: {}".format(e))

    # -- Step 3: Open GUI immediately --
    _step("Step 3: creating HybridRAGApp...")
    from src.gui.app import HybridRAGApp

    app = HybridRAGApp(
        boot_result=boot_result,
        config=config,
    )
    _step("Step 3 done: GUI window created")

    # -- Step 4: Load backends in background thread --
    _step("Step 4: starting backend thread...")
    backend_thread = threading.Thread(
        target=_load_backends, args=(app, logger), daemon=True,
    )
    backend_thread.start()
    _step("Step 4 done: backend thread running")

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
