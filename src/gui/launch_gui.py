# ============================================================================
# HybridRAG v3 -- GUI Launcher (src/gui/launch_gui.py)
# ============================================================================
# WHAT: Entry point that boots the system and opens the GUI window.
# WHY:  Heavy imports (torch, sentence-transformers) take 10-16s.  If we
#       loaded them before showing the window, the user would stare at
#       nothing.  This module shows the window immediately and loads
#       backends in the background, so the user sees progress.
# HOW:  Three-phase launch:
#       Phase 1 - Eager preload: starts loading the embedding model at
#                 module import time (before boot/config/GUI).
#       Phase 2 - Boot + config + optional setup wizard (2-3s).
#       Phase 3 - Open GUI window, load remaining backends in a thread.
#       The preload runs in parallel with Phase 2, saving 2-3s of wall time.
# USAGE: python src/gui/launch_gui.py
#        or: from start_hybridrag.ps1 (PowerShell wrapper)
#
# PERFORMANCE: The Embedder is the cold-start bottleneck (~16s on 8GB
# laptop). Three tricks to minimize perceived wait:
#   1. Eager preload -- start building the Embedder at t=0, BEFORE
#      boot/config/GUI, so the 16s overlaps with the 2s of setup.
#   2. Embedder cache -- keep the Embedder across Reset clicks so the
#      7.6s model-load is paid only once per process lifetime.
#   3. Warm encode -- fire a dummy encode() after load so the first
#      real query pays zero lazy-init cost.
#
# INTERNET ACCESS: Depends on boot result and user mode selection.
# ============================================================================

import os
import sys
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from src.core.constants import DEFAULT_EMBED_DIM

# Ensure project root is on sys.path
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Set HYBRIDRAG_PROJECT_ROOT if not already set
if not os.environ.get("HYBRIDRAG_PROJECT_ROOT"):
    os.environ["HYBRIDRAG_PROJECT_ROOT"] = _project_root

# ============================================================================
# EAGER PRELOAD: start the heaviest work (import torch + sentence-transformers
# + load model weights) immediately, before boot/config/GUI.  The result is
# stashed in _preload_result and picked up by _load_backends() later.
# On this laptop the overlap saves ~2s; on faster hardware the ratio is even
# better because boot+config+GUI take longer relative to model-load time.
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
    """Build the Embedder (torch + model weights) as early as possible."""
    try:
        from src.core.embedder import Embedder
        model_name = _read_embedding_model_from_config()
        e = Embedder(model_name=model_name)
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


def _get_or_build_embedder(model_name, logger):
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
        e = Embedder(model_name=model_name)
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
    """Schedule a loading-stage update on the GUI main thread."""
    try:
        app.after(0, lambda: (
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
            )
            s.connect()
            logger.info("[OK] Vector store connected")
            return s

        def _init_embedder():
            _set_stage(app, "Embedder...")
            return _get_or_build_embedder(model_name, logger)

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
        app.after(0, _attach)
    except Exception as e:
        logger.debug("after() failed during backend attach: %s", e)


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
        try:
            results = run_ibit(config, query_engine, indexer, router)
            # Schedule stepped display on main thread
            app.after(0, lambda: _step_display(app, results, 0, STEP_DELAY_MS))
        except Exception as e:
            logger.warning("[WARN] IBIT failed: %s", e)
            # Safety net: clear loading state even on crash
            try:
                app.after(0, lambda: app.status_bar.set_ibit_result(0, 0, []))
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


def main():
    """Boot config, open GUI immediately, load backends in background."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger("gui_launcher")

    # NOTE: _preload_thread is already running (started at module load).
    # While we boot + load config + build the GUI (~2s), torch and the
    # embedding model are loading in parallel.

    # -- Step 1: Boot the system (lightweight -- config + creds + gate) --
    logger.info("Booting HybridRAG...")
    boot_result = None
    config = None

    try:
        from src.core.boot import boot_hybridrag
        boot_result = boot_hybridrag()
        if boot_result.success:
            logger.info("[OK] Boot succeeded")
        else:
            logger.warning("[WARN] Boot completed with errors")
            for err in boot_result.errors:
                logger.warning("  %s", err)
    except Exception as e:
        logger.error("[FAIL] Boot failed: %s", e)

    # -- Step 2: Load config --
    try:
        from src.core.config import load_config
        config = load_config(_project_root)
        logger.info("[OK] Config loaded (mode=%s)", config.mode)
    except Exception as e:
        logger.warning("[WARN] Config load failed, using defaults: %s", e)
        from src.core.config import Config
        config = Config()

    # -- Step 2.5: First-run setup wizard --
    from src.gui.panels.setup_wizard import needs_setup
    if needs_setup(_project_root):
        logger.info("First run detected -- launching setup wizard")
        import tkinter as _tk
        from src.gui.theme import apply_ttk_styles, current_theme
        _tmp_root = _tk.Tk()
        _tmp_root.withdraw()
        apply_ttk_styles(current_theme())

        from src.gui.panels.setup_wizard import SetupWizard
        wiz = SetupWizard(_tmp_root, _project_root)
        wiz.grab_set()
        _tmp_root.wait_window(wiz)
        _tmp_root.destroy()

        if not wiz.completed:
            logger.info("Setup wizard cancelled -- exiting")
            sys.exit(0)

        # Reload config with wizard-written values
        logger.info("Reloading config after setup wizard...")
        try:
            config = load_config(_project_root)
            logger.info("[OK] Config reloaded (mode=%s)", config.mode)
        except Exception as e:
            logger.warning("[WARN] Config reload failed: %s", e)

    # -- Step 3: Open GUI immediately --
    logger.info("Opening GUI window...")
    from src.gui.app import HybridRAGApp

    app = HybridRAGApp(
        boot_result=boot_result,
        config=config,
    )

    # -- Step 4: Load backends in background thread --
    backend_thread = threading.Thread(
        target=_load_backends, args=(app, logger), daemon=True,
    )
    backend_thread.start()

    # -- Step 5: Run the GUI event loop --
    app.mainloop()


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
