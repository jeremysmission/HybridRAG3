from __future__ import annotations

from typing import Any


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def uses_max_completion_tokens(*, provider: str = "", endpoint: str = "") -> bool:
    text = "{} {}".format(provider or "", endpoint or "").lower()
    return "azure" in text or "api.openai.com" in text


def build_api_generation_params(
    api_cfg,
    *,
    provider: str = "",
    endpoint: str = "",
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    max_tokens = _safe_int(getattr(api_cfg, "max_tokens", 0), 0)
    if max_tokens > 0:
        key = "max_completion_tokens" if uses_max_completion_tokens(
            provider=provider,
            endpoint=endpoint,
        ) else "max_tokens"
        params[key] = max_tokens

    params["temperature"] = _safe_float(getattr(api_cfg, "temperature", 0.05), 0.05)
    params["top_p"] = _safe_float(getattr(api_cfg, "top_p", 1.0), 1.0)
    params["presence_penalty"] = _safe_float(
        getattr(api_cfg, "presence_penalty", 0.0),
        0.0,
    )
    params["frequency_penalty"] = _safe_float(
        getattr(api_cfg, "frequency_penalty", 0.0),
        0.0,
    )

    seed = _safe_int(getattr(api_cfg, "seed", 0), 0)
    if seed > 0:
        params["seed"] = seed

    return params


def build_ollama_generation_options(config) -> dict[str, Any]:
    temperature = getattr(config.ollama, "temperature", None)
    if temperature is None:
        temperature = getattr(config.api, "temperature", 0.05)

    options = {
        "temperature": _safe_float(temperature, 0.05),
        "top_p": _safe_float(getattr(config.ollama, "top_p", 0.9), 0.9),
        "num_ctx": _safe_int(getattr(config.ollama, "context_window", 4096), 4096),
        "num_predict": _safe_int(getattr(config.ollama, "num_predict", 512), 512),
    }

    seed = _safe_int(getattr(config.ollama, "seed", 0), 0)
    if seed > 0:
        options["seed"] = seed

    num_thread = _safe_int(getattr(config.ollama, "num_thread", 0), 0)
    if num_thread > 0:
        options["num_thread"] = num_thread

    return options


def snapshot_backend_generation_settings(backend_cfg) -> dict[str, Any]:
    return {
        "context_window": _safe_int(getattr(backend_cfg, "context_window", 0), 0),
        "max_tokens": _safe_int(getattr(backend_cfg, "max_tokens", 0), 0),
        "num_predict": _safe_int(getattr(backend_cfg, "num_predict", 0), 0),
        "temperature": _safe_float(getattr(backend_cfg, "temperature", 0.0), 0.0),
        "top_p": _safe_float(getattr(backend_cfg, "top_p", 0.0), 0.0),
        "presence_penalty": _safe_float(
            getattr(backend_cfg, "presence_penalty", 0.0),
            0.0,
        ),
        "frequency_penalty": _safe_float(
            getattr(backend_cfg, "frequency_penalty", 0.0),
            0.0,
        ),
        "seed": _safe_int(getattr(backend_cfg, "seed", 0), 0),
        "timeout_seconds": _safe_int(getattr(backend_cfg, "timeout_seconds", 0), 0),
    }
