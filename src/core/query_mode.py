from __future__ import annotations

from types import SimpleNamespace


def _ensure_query_config(config):
    """Return a writable query config section, creating it when missing."""
    query_cfg = getattr(config, "query", None)
    if query_cfg is None:
        query_cfg = SimpleNamespace()
        setattr(config, "query", query_cfg)
    return query_cfg


def clamp_grounding_bias(value) -> int:
    """Return grounding bias constrained to the supported 0..10 range."""
    try:
        return max(0, min(10, int(value)))
    except Exception:
        return 7


def resolve_query_mode_settings(config) -> dict:
    """Resolve active query-mode controls into runtime guard settings."""
    query_cfg = getattr(config, "query", None)
    bias = clamp_grounding_bias(getattr(query_cfg, "grounding_bias", 7))
    allow_open_knowledge = bool(
        getattr(query_cfg, "allow_open_knowledge", True)
    )
    guard_enabled = bias > 0
    threshold = 0.35 + (max(1, bias) / 10.0) * 0.55
    min_chunks = 1 if bias <= 4 else 2 if bias <= 7 else 3
    min_score = 0.00 if bias <= 2 else 0.03 if bias <= 4 else 0.06 if bias <= 7 else 0.10
    action = "flag" if bias <= 5 else "block"
    return {
        "grounding_bias": bias,
        "allow_open_knowledge": allow_open_knowledge,
        "guard_enabled": bool(guard_enabled),
        "guard_threshold": float(round(threshold, 2)),
        "guard_min_chunks": int(min_chunks),
        "guard_min_score": float(min_score),
        "guard_action": action,
    }


def apply_query_mode_to_config(config) -> dict:
    """Normalize and persist query-mode controls on the config object."""
    settings = resolve_query_mode_settings(config)
    query_cfg = _ensure_query_config(config)
    query_cfg.grounding_bias = settings["grounding_bias"]
    query_cfg.allow_open_knowledge = settings["allow_open_knowledge"]
    return settings


def apply_query_mode_to_engine(engine, sync_guard_policy: bool = False) -> dict:
    """Push query-mode settings into a live query engine.

    General runtime sync only mirrors open-knowledge fallback so config
    hydration does not stomp explicit guard overrides. Guard-policy sync
    is opt-in for UI actions that intentionally change the grounding mode.
    """
    settings = apply_query_mode_to_config(engine.config)
    setattr(engine, "allow_open_knowledge", settings["allow_open_knowledge"])
    if sync_guard_policy:
        if hasattr(engine, "guard_enabled"):
            engine.guard_enabled = settings["guard_enabled"]
        if hasattr(engine, "guard_threshold"):
            engine.guard_threshold = settings["guard_threshold"]
        if hasattr(engine, "guard_min_chunks"):
            engine.guard_min_chunks = settings["guard_min_chunks"]
        if hasattr(engine, "guard_min_score"):
            engine.guard_min_score = settings["guard_min_score"]
        if hasattr(engine, "guard_action"):
            engine.guard_action = settings["guard_action"]
    return settings
