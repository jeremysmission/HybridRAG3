# ============================================================================
# llm_router.py -- LLM Backend Router Orchestrator
# ============================================================================
#
# WHAT: The "switchboard" that decides where AI queries go based on mode.
#
# This module was split into smaller files for maintainability (500-line
# budget per file). The LLMRouter orchestrator class lives here and
# imports the backend routers from their dedicated modules.
#
# MODULE LAYOUT:
#   llm_response.py         -- LLMResponse dataclass + shared utilities
#   ollama_router.py        -- OllamaRouter (localhost Ollama)
#   vllm_router.py          -- VLLMRouter (localhost vLLM)
#   api_router.py           -- APIRouter (Azure/OpenAI cloud)
#   deployment_discovery.py -- get_available_deployments, refresh, invalidate
#   llm_router.py           -- LLMRouter orchestrator (this file)
#
# USAGE:
#   router = LLMRouter(config)
#   answer = router.query("What is the operating frequency?")
# ============================================================================

import time
from typing import Optional, Dict, Any, Generator

# -- Re-export all public symbols so existing imports keep working -----------
from .llm_response import (
    LLMResponse,
    _build_httpx_client,
    _openai_sdk_available,
    _call_stream_with_optional_cancel,
    _safe_timeout_seconds,
    _http_error_message,
    _ollama_retry_model_name,
    _DEFAULT_API_VERSION,
)
from .ollama_router import OllamaRouter
from .vllm_router import VLLMRouter
from .api_router import (
    APIRouter,
    _resolve_deployment,
    _resolve_api_version,
    _extract_system_user,
    _split_prompt_to_messages,
    _is_azure_endpoint,
    _filter_banned_deployments,
)
from .deployment_discovery import (
    get_available_deployments,
    refresh_deployments,
    invalidate_deployment_cache,
)

# -- HybridRAG internals needed by the orchestrator -------------------------
from .config import Config
from .network_gate import get_gate, NetworkBlockedError
from ..monitoring.logger import get_app_logger


# ============================================================================
# LLMRouter -- The main switchboard
# ============================================================================
class LLMRouter:
    """
    Route queries to the appropriate LLM backend.

    Mode selection:
        "offline" --> Ollama (local, free, no internet)
        "online"  --> Azure OpenAI API (company cloud, costs money)
    """

    def __init__(self, config: Config, api_key: Optional[str] = None,
                 credentials=None):
        """
        Initialize the router and set up both backends.

        Args:
            config:  The HybridRAG configuration object
            api_key: Optional explicit API key (overrides all other sources)
            credentials: Pre-resolved credentials from boot (skips keyring lookup)
        """
        self.config = config
        self.logger = get_app_logger("llm_router")
        self.last_error = ""

        # -- Always create the Ollama router (offline mode) --
        self.ollama = OllamaRouter(config)

        # -- Create vLLM router if enabled --
        if config.vllm.enabled:
            self.vllm = VLLMRouter(config)
            self.logger.info("llm_router_vllm_enabled", model=config.vllm.model)
        else:
            self.vllm = None

        # Offline mode does not need API credentials or APIRouter bootstrap.
        mode = str(getattr(config, "mode", "offline")).lower()
        if mode != "online" and api_key is None and credentials is None:
            self.api = None
            self.logger.info("llm_router_init", api_mode="skipped_offline")
            return

        # -- Resolve credentials -------------------------------------------
        resolved_key = api_key
        resolved_endpoint = ""
        resolved_deployment = ""
        resolved_api_version = ""

        creds = credentials
        if creds is None:
            try:
                from ..security.credentials import resolve_credentials
                config_dict = None
                if hasattr(config, "to_dict"):
                    config_dict = config.to_dict()
                elif hasattr(config, "api"):
                    config_dict = {
                        "api": {
                            "endpoint": config.api.endpoint or "",
                            "deployment": config.api.deployment or "",
                            "api_version": config.api.api_version or "",
                        }
                    }
                creds = resolve_credentials(config_dict)
            except ImportError:
                self.logger.warning("llm_router_credentials_import_failed")

        resolved_provider = ""

        if creds is not None:
            if not resolved_key and creds.api_key:
                resolved_key = creds.api_key
            if creds.endpoint:
                resolved_endpoint = creds.endpoint
            if creds.deployment:
                resolved_deployment = creds.deployment
            if creds.api_version:
                resolved_api_version = creds.api_version
            if getattr(creds, "provider", None):
                resolved_provider = creds.provider

            self.logger.info(
                "llm_router_creds_resolved",
                key_source=getattr(creds, "source_key", "") or "caller",
                endpoint_source=getattr(creds, "source_endpoint", "") or "config",
                provider=resolved_provider or "auto",
            )

        if not resolved_provider:
            resolved_provider = getattr(config.api, "provider", "") or ""

        # -- Create the API router only when credentials are complete --
        if resolved_key and resolved_endpoint:
            self.api = APIRouter(
                config, resolved_key, resolved_endpoint,
                deployment_override=resolved_deployment,
                api_version_override=resolved_api_version,
                provider_override=resolved_provider,
            )
            self.logger.info("llm_router_init", api_mode="enabled")
        elif resolved_key:
            self.api = None
            self.logger.info("llm_router_init", api_mode="disabled_no_endpoint")
        else:
            self.api = None
            self.logger.info("llm_router_init", api_mode="disabled_no_key")

    def query(self, prompt: str) -> Optional[LLMResponse]:
        """Route a query to the appropriate backend based on config.mode."""
        mode = self.config.mode
        self.last_error = ""

        self.logger.info("query_mode", mode=mode)

        if mode == "online":
            if self.api is None:
                try:
                    from ..security.credentials import resolve_credentials
                    creds = resolve_credentials(use_cache=False)
                    if (
                        getattr(creds, "api_key", "")
                        and getattr(creds, "endpoint", "")
                    ):
                        self.api = APIRouter(
                            self.config,
                            creds.api_key,
                            getattr(creds, "endpoint", "") or "",
                            deployment_override=getattr(creds, "deployment", "") or "",
                            api_version_override=getattr(creds, "api_version", "") or "",
                            provider_override=getattr(creds, "provider", "") or "",
                        )
                    elif getattr(creds, "api_key", ""):
                        self.logger.warning(
                            "online_late_router_attach_skipped",
                            reason="missing_endpoint",
                        )
                except Exception as e:
                    self.logger.warning("online_late_router_attach_failed", error=str(e))
            if self.api is None:
                self.last_error = "API is not configured (missing key/endpoint)"
                self.logger.error(
                    "api_not_configured",
                    hint="Run rag-store-key and rag-store-endpoint first",
                )
                return None

            # Self-heal gate state for GUI mode/race inconsistencies
            try:
                from .network_gate import configure_gate
                endpoint = (
                    getattr(self.api, "base_endpoint", "")
                    or getattr(getattr(self.config, "api", None), "endpoint", "")
                    or ""
                )
                configure_gate(
                    mode="online",
                    api_endpoint=endpoint,
                    allowed_prefixes=getattr(
                        getattr(self.config, "api", None),
                        "allowed_endpoint_prefixes", [],
                    ) if self.config else [],
                )
            except Exception as e:
                self.logger.warning("online_gate_self_heal_failed", error=str(e))

            result = self.api.query(prompt)
            if result is None:
                self.last_error = (
                    getattr(self.api, "last_error", "")
                    or "Online API query failed"
                )
            return result

        else:
            # Offline mode priority: vLLM > Ollama
            if self.vllm and self.vllm.is_available():
                result = self.vllm.query(prompt)
                if result is not None:
                    return result
                self.last_error = (
                    getattr(self.vllm, "last_error", "")
                    or "vLLM query failed"
                )
                self.logger.warning("vllm_query_failed_falling_back_to_ollama")
            result = self.ollama.query(prompt)
            if result is None:
                self.last_error = (
                    getattr(self.ollama, "last_error", "")
                    or "Ollama query failed"
                )
            return result

    def query_stream(
        self,
        prompt: str,
        cancel_event=None,
    ) -> Generator[Dict[str, Any], None, None]:
        """Stream tokens from the appropriate backend."""
        mode = self.config.mode
        self.last_error = ""

        if mode == "offline":
            if self.vllm and self.vllm.is_available():
                for chunk in _call_stream_with_optional_cancel(
                    self.vllm.query_stream,
                    prompt,
                    cancel_event,
                ):
                    if "error" in chunk:
                        self.last_error = str(chunk.get("error", ""))
                    yield chunk
            else:
                for chunk in _call_stream_with_optional_cancel(
                    self.ollama.query_stream,
                    prompt,
                    cancel_event,
                ):
                    if "error" in chunk:
                        self.last_error = str(chunk.get("error", ""))
                    yield chunk
        else:
            if cancel_event is not None and cancel_event.is_set():
                return
            result = self.query(prompt)
            if cancel_event is not None and cancel_event.is_set():
                return
            if result:
                yield {"token": result.text}
                yield {
                    "done": True,
                    "tokens_in": result.tokens_in,
                    "tokens_out": result.tokens_out,
                    "model": result.model,
                    "latency_ms": result.latency_ms,
                }
            else:
                err = self.last_error or "Online API query failed"
                yield {"error": err, "backend": "api"}
                yield {
                    "done": True,
                    "tokens_in": 0, "tokens_out": 0,
                    "model": "unknown", "latency_ms": 0.0,
                }

    def close(self):
        """Release HTTP clients held by backend routers."""
        if hasattr(self, "ollama") and hasattr(self.ollama, "_client"):
            try:
                self.ollama._client.close()
            except Exception:
                pass
        if hasattr(self, "vllm") and self.vllm and hasattr(self.vllm, "_client"):
            try:
                self.vllm._client.close()
            except Exception:
                pass
        if hasattr(self, "api") and self.api and hasattr(self.api, "client"):
            try:
                if self.api.client:
                    self.api.client.close()
            except Exception:
                pass

    def get_status(self) -> Dict[str, Any]:
        """Get the current status of all LLM backends."""
        api_present = (
            self.api is not None
            and (
                getattr(self.api, "client", None) is not None
                or getattr(self.api, "http_api_client", None) is not None
            )
        )
        status = {
            "mode": self.config.mode,
            "ollama_model": self.config.ollama.model,
            "ollama_available": self.ollama.is_available(),
            "vllm_enabled": self.vllm is not None,
            "vllm_available": self.vllm.is_available() if self.vllm else False,
            "api_configured": (self.config.mode == "online" and api_present),
            "api_present": api_present,
            "sdk_available": _openai_sdk_available(),
        }

        if self.api:
            api_status = self.api.get_status()
            status.update({
                "api_provider": api_status["provider"],
                "api_endpoint": api_status["endpoint"],
                "api_sdk": api_status.get("sdk", "unknown"),
            })
            if api_status.get("deployment"):
                status["api_deployment"] = api_status["deployment"]
                status["api_version"] = api_status["api_version"]
                status["api_clean_endpoint"] = api_status.get("clean_endpoint", "")

        return status
