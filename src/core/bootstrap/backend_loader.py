# ============================================================================
# HybridRAG v3 -- Backend Loader (src/core/bootstrap/backend_loader.py)
# ============================================================================
# Purpose:
#   Load heavy backends for the GUI with low perceived latency:
#     - VectorStore connect
#     - Embedder (possibly preloaded)
#     - LLMRouter
#     - QueryEngine + Indexer assembly
#
# Design:
#   - Parallel init of store/embedder/router (3 threads)
#   - Optional warmups (non-blocking best-effort):
#       * Embedder warm encode already performed during preload
#       * Ollama warm model prompt
#       * Online API warm connection (DNS/TLS) if configured
#
# Outputs:
#   BackendBundle with services + init_errors (non-fatal)
#
# Constraints:
#   - No GUI imports here (pure core).
#   - Portable.
# ============================================================================

from __future__ import annotations

import os
import time
import logging
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Any, List, Callable, Dict

logger = logging.getLogger(__name__)


@dataclass
class BackendBundle:
    store: Optional[Any] = None
    embedder: Optional[Any] = None
    router: Optional[Any] = None
    query_engine: Optional[Any] = None
    indexer: Optional[Any] = None
    init_errors: List[str] = field(default_factory=list)
    timings_ms: Dict[str, float] = field(default_factory=dict)


class BackendLoader:
    def __init__(
        self,
        config: Any,
        boot_result: Any = None,
        preloaded_embedder: Any = None,
        stage_cb: Optional[Callable[[str], None]] = None,
    ):
        self.config = config
        self.boot_result = boot_result
        self.preloaded_embedder = preloaded_embedder
        self.stage_cb = stage_cb

    def load(self, timeout_seconds: int = 60) -> BackendBundle:
        bundle = BackendBundle()
        t_all = time.perf_counter()

        # Lazy imports: these modules can be heavy.
        from src.core.vector_store import VectorStore
        from src.core.llm_router import LLMRouter
        from src.core.grounded_query_engine import GroundedQueryEngine
        from src.core.runtime_limits import RuntimeLimiter
        from src.core.limiting_embedder import LimitingEmbedder
        from src.core.chunker import Chunker
        from src.core.indexer import Indexer

        model_name = getattr(getattr(self.config, "embedding", None), "model_name", "nomic-embed-text")

        limiter = RuntimeLimiter.from_config(self.config)


        def stage(msg: str) -> None:
            if self.stage_cb:
                try:
                    self.stage_cb(msg)
                except Exception:
                    pass

        def init_store():
            stage("VectorStore...")
            t0 = time.perf_counter()
            db_path = getattr(getattr(self.config, "paths", None), "database", "")
            if not db_path:
                raise RuntimeError("No database path configured")
            db_dir = os.path.dirname(db_path) or "."
            os.makedirs(db_dir, exist_ok=True)  # portability + first-run
            s = VectorStore(
                db_path=db_path,
                embedding_dim=getattr(getattr(self.config, "embedding", None), "dimension", 384),
            )
            s.connect()
            bundle.timings_ms["vector_store"] = (time.perf_counter() - t0) * 1000
            return s

        def init_embedder():
            stage("Embedder...")
            t0 = time.perf_counter()
            if self.preloaded_embedder is not None:
                bundle.timings_ms["embedder"] = (time.perf_counter() - t0) * 1000
                return LimitingEmbedder(self.preloaded_embedder, limiter)
            cache_dir = getattr(getattr(self.config, "paths", None), "embeddings_cache", "")
            if cache_dir:
                try:
                    os.makedirs(cache_dir, exist_ok=True)
                except Exception:
                    pass
            from src.core.embedder import Embedder
            e = Embedder(model_name=model_name)
            # Warm encode to avoid first-query latency spikes
            try:
                e.embed_query("warmup")
            except Exception:
                pass
            bundle.timings_ms["embedder"] = (time.perf_counter() - t0) * 1000
            return LimitingEmbedder(e, limiter)

        def init_router():
            stage("LLM Router...")
            t0 = time.perf_counter()
            creds = getattr(self.boot_result, "credentials", None)
            r = LLMRouter(self.config, credentials=creds)
            bundle.timings_ms["router"] = (time.perf_counter() - t0) * 1000
            return r

        # Per-component bounded timeouts (fast fail for GUI reliability).
        # Env overrides: HYBRIDRAG_INIT_TIMEOUT_STORE/EMBEDDER/ROUTER (seconds).
        def _to_int(env_name: str, default: int) -> int:
            try:
                return int(os.getenv(env_name, str(default)))
            except Exception:
                return default

        t_store = _to_int("HYBRIDRAG_INIT_TIMEOUT_STORE", min(10, timeout_seconds))
        t_embed = _to_int("HYBRIDRAG_INIT_TIMEOUT_EMBEDDER", min(15, timeout_seconds))
        t_router = _to_int("HYBRIDRAG_INIT_TIMEOUT_ROUTER", min(10, timeout_seconds))

        with ThreadPoolExecutor(max_workers=3) as pool:
            fut_store = pool.submit(init_store)
            fut_embedder = pool.submit(init_embedder)
            fut_router = pool.submit(init_router)

            bundle.store = self._await("VectorStore", fut_store, bundle.init_errors, t_store)
            bundle.embedder = self._await("Embedder", fut_embedder, bundle.init_errors, t_embed)
            bundle.router = self._await("LLMRouter", fut_router, bundle.init_errors, t_router)

        # Warmups (best effort, do not block readiness)
        stage("Warming up model...")
        self._warm_offline(bundle.router)
        self._warm_online(self.boot_result)

        # Assemble QueryEngine/Indexer
        stage("QueryEngine...")
        t_qe = time.perf_counter()
        if bundle.store and bundle.embedder:
            bundle.query_engine = GroundedQueryEngine(self.config, bundle.store, bundle.embedder, bundle.router)
            chunker = Chunker(self.config)
            bundle.indexer = Indexer(self.config, bundle.store, bundle.embedder, chunker)
        bundle.timings_ms["assemble"] = (time.perf_counter() - t_qe) * 1000

        bundle.timings_ms["total"] = (time.perf_counter() - t_all) * 1000
        stage("Ready")
        return bundle

    def _await(self, label: str, fut, errors: List[str], timeout_s: int):
        try:
            return fut.result(timeout=timeout_s)
        except Exception as e:
            logger.warning("[WARN] %s init failed: %s", label, e)
            errors.append(f"{label}: {e}")
            return None

    def _warm_offline(self, router: Any) -> None:
        # Warm Ollama weights into memory so first demo query is fast.
        try:
            if not router or not getattr(router, "ollama", None):
                return
            if not router.ollama.is_available():
                return
            cfg = self.config
            router.ollama._client.post(
                f"{router.ollama.base_url}/api/generate",
                json={
                    "model": cfg.ollama.model,
                    "prompt": "hi",
                    "stream": False,
                    "keep_alive": getattr(cfg.ollama, "keep_alive", -1),
                    "options": router.ollama._build_options(),
                },
                timeout=20,
            )
        except Exception:
            return

    def _warm_online(self, boot_result: Any) -> None:
        # Warm online API connection: DNS/TLS/connection pooling.
        # Do not fail if not configured.
        try:
            if not boot_result or not getattr(boot_result, "api_client", None):
                return
            client = boot_result.api_client
            # Avoid token generation/cost.
            if hasattr(client, "ping"):
                client.ping(timeout=5)
            elif hasattr(client, "list_models"):
                client.list_models(timeout=5)
        except Exception:
            return
