"""HybridRAG v3 core package.

Design goals:
- Keep `src.core` as the stable public surface area for the rest of the app.
- Avoid heavy imports at package import time (models, torch, etc.).
- Still allow ergonomic access like `import src.core as core; core.indexer`.

Implementation:
- Lazy-load submodules via PEP 562 (`__getattr__`).
"""

from __future__ import annotations

import importlib
from typing import Dict

# Public submodules that callers/tests expect to access as attributes on `src.core`.
# Keep this list explicit so we don't accidentally expose internals.
_PUBLIC_SUBMODULES: Dict[str, str] = {
    "exceptions": "src.core.exceptions",
    "http_client": "src.core.http_client",
    "api_client_factory": "src.core.api_client_factory",
    "boot": "src.core.boot",
    "network_gate": "src.core.network_gate",
    "indexer": "src.core.indexer",
    "llm_router": "src.core.llm_router",
    "query_engine": "src.core.query_engine",
    "grounded_query_engine": "src.core.grounded_query_engine",
    "retriever": "src.core.retriever",
    "vector_store": "src.core.vector_store",
    "chunker": "src.core.chunker",
    "embedder": "src.core.embedder",
    "health_checks": "src.core.health_checks",
    "fault_analysis": "src.core.fault_analysis",
    "sqlite_utils": "src.core.sqlite_utils",
    "feature_registry": "src.core.feature_registry",
    "guard_config": "src.core.guard_config",
    "config": "src.core.config",
}

__all__ = sorted(_PUBLIC_SUBMODULES.keys())

def __getattr__(name: str):
    """Lazy module attribute access.

    Example:
        import src.core as core
        core.indexer  # loads src.core.indexer on first access
    """
    if name in _PUBLIC_SUBMODULES:
        module = importlib.import_module(_PUBLIC_SUBMODULES[name])
        globals()[name] = module
        return module
    raise AttributeError(f"module 'src.core' has no attribute {name!r}")

def __dir__():
    return sorted(list(globals().keys()) + list(_PUBLIC_SUBMODULES.keys()))
