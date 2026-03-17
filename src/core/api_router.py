# ============================================================================
# api_router.py -- APIRouter class + helpers (Azure/OpenAI cloud, online mode)
# ============================================================================
# Extracted from llm_router.py. INTERNET ACCESS: YES
# ============================================================================

import os
import time
import logging
from typing import Optional, Dict, Any

from .llm_response import (
    LLMResponse, _build_httpx_client, _openai_sdk_available, _DEFAULT_API_VERSION,
)
from .config import Config
from .generation_params import build_api_generation_params
from .network_gate import get_gate, NetworkBlockedError
from ..monitoring.logger import get_app_logger

logger = logging.getLogger(__name__)


def _resolve_deployment(config, endpoint_url):
    """Resolve Azure deployment: YAML > env vars > URL > fallback."""
    import re
    if config.api.deployment:
        return config.api.deployment
    for var in [
        "AZURE_OPENAI_DEPLOYMENT", "AZURE_DEPLOYMENT",
        "OPENAI_DEPLOYMENT", "AZURE_OPENAI_DEPLOYMENT_NAME",
        "DEPLOYMENT_NAME", "AZURE_CHAT_DEPLOYMENT",
    ]:
        val = os.environ.get(var, "").strip()
        if val:
            return val
    if endpoint_url and "/deployments/" in endpoint_url:
        match = re.search(r"/deployments/([^/?]+)", endpoint_url)
        if match:
            return match.group(1)
    return "gpt-35-turbo"


def _resolve_api_version(config, endpoint_url):
    """Resolve Azure API version: YAML > env vars > URL > fallback."""
    import re
    if config.api.api_version:
        return config.api.api_version
    for var in [
        "AZURE_OPENAI_API_VERSION", "AZURE_API_VERSION",
        "OPENAI_API_VERSION", "API_VERSION",
    ]:
        val = os.environ.get(var, "").strip()
        if val:
            return val
    if endpoint_url and "api-version=" in endpoint_url:
        match = re.search(r"api-version=([^&]+)", endpoint_url)
        if match:
            return match.group(1)
    return _DEFAULT_API_VERSION


_CONTEXT_MARKERS = ("\nContext:\n", "\nContext (may be empty/partial):\n")


def _extract_system_user(prompt: str) -> tuple:
    """Split a combined prompt into (system_text, user_text)."""
    for marker in _CONTEXT_MARKERS:
        idx = prompt.find(marker)
        if idx >= 0:
            return prompt[:idx].strip(), prompt[idx + 1:].strip()
    return "", prompt


def _split_prompt_to_messages(prompt: str) -> list:
    """Split a combined prompt into system + user messages for chat API."""
    system_text, user_text = _extract_system_user(prompt)
    if system_text:
        return [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ]
    return [{"role": "user", "content": prompt}]


def _is_azure_endpoint(endpoint):
    """Check if an endpoint URL is Azure-style (commercial or government)."""
    if not endpoint:
        return False
    lower = endpoint.lower()
    return "azure" in lower or "aoai" in lower


_BANNED_PREFIXES = ["qwen", "deepseek", "llama", "baidu", "bge"]


def _filter_banned_deployments(models):
    """Remove banned model families from a deployment list."""
    return [m for m in models if not any(b in m.lower() for b in _BANNED_PREFIXES)]


def _api_extract_azure_base(url: str) -> str:
    """Extract just the base domain from an Azure endpoint URL."""
    idx = url.lower().find("/openai/")
    if idx > 0:
        return url[:idx]
    idx = url.lower().find("/chat/")
    if idx > 0:
        return url[:idx]
    idx = url.find("?")
    if idx > 0:
        return url[:idx]
    return url


def _api_init_http_fallback_client(router: "APIRouter") -> None:
    """Initialize internal HTTP client fallback when SDK is unavailable."""
    try:
        from src.core.api_client_factory import ApiClientFactory
        from src.security.credentials import ApiCredentials
        config_dict = (
            router.config.to_dict()
            if hasattr(router.config, "to_dict")
            else {
                "api": {
                    "provider": "azure" if router.is_azure else "openai",
                    "endpoint": router.base_endpoint,
                    "deployment": router.deployment,
                    "api_version": router.api_version,
                    "model": (
                        getattr(router.config.api, "model", "")
                        or (router.deployment if not router.is_azure else "")
                    ),
                }
            }
        )
        factory = ApiClientFactory(config_dict)
        creds = ApiCredentials(
            api_key=router.api_key, endpoint=router.base_endpoint,
            deployment=router.deployment, api_version=router.api_version,
            provider=("azure" if router.is_azure else "openai"),
        )
        router.http_api_client = factory.build(creds)
        router.logger.info("api_router_http_fallback_ready",
                           provider=("azure" if router.is_azure else "openai"))
    except Exception as e:
        router.http_api_client = None
        router._init_error = str(e)
        router.logger.error("api_router_http_fallback_init_failed", error=str(e))


def _api_reinit_sdk_client(router: "APIRouter") -> None:
    """Best-effort SDK client re-init using current resolved fields."""
    try:
        from openai import AzureOpenAI, OpenAI
        if router.is_azure:
            clean_endpoint = _api_extract_azure_base(router.base_endpoint)
            router.client = AzureOpenAI(
                azure_endpoint=clean_endpoint, api_key=router.api_key,
                api_version=router.api_version,
                http_client=_build_httpx_client(
                    timeout=getattr(router.config.api, "timeout_seconds", 60)),
            )
        else:
            kw = {"api_key": router.api_key}
            if router.base_endpoint and "openai.com" not in router.base_endpoint:
                kw["base_url"] = router.base_endpoint
            router.client = OpenAI(**kw)
        router._init_error = ""
    except Exception as e:
        router.client = None
        router._init_error = str(e)
        router.logger.warning("api_router_sdk_reinit_failed", error=str(e))


def _api_attempt_late_init(router: "APIRouter") -> None:
    """Last-chance API client initialization at query time."""
    if router.client is not None or router.http_api_client is not None:
        return
    try:
        from src.security.credentials import resolve_credentials
        creds = resolve_credentials(use_cache=False)
        if getattr(creds, "api_key", ""):
            router.api_key = creds.api_key
        if getattr(creds, "endpoint", ""):
            router.base_endpoint = creds.endpoint.rstrip("/")
        if getattr(creds, "deployment", ""):
            router.deployment = creds.deployment
        if getattr(creds, "api_version", ""):
            router.api_version = creds.api_version
        provider = (getattr(creds, "provider", "") or router.provider or "").lower()
        if provider in ("azure", "azure_gov"):
            router.is_azure = True
            router.provider = provider
        elif provider == "openai":
            router.is_azure = False
            router.provider = provider
        else:
            low = (router.base_endpoint or "").lower()
            router.is_azure = ("azure" in low or "aoai" in low)
        _api_reinit_sdk_client(router)
        _api_init_http_fallback_client(router)
    except Exception as e:
        router.logger.warning("api_router_late_init_failed", error=str(e))


def _api_get_status(router: "APIRouter") -> Dict[str, Any]:
    """Return current API router status for diagnostics."""
    detected_provider = router.provider if router.provider else (
        "azure_openai" if router.is_azure else "openai")
    status = {
        "provider": detected_provider, "endpoint": router.base_endpoint,
        "api_configured": (router.client is not None or router.http_api_client is not None),
        "sdk_available": _openai_sdk_available(),
        "sdk": "openai_official" if router.client is not None else "http_fallback",
    }
    if router.is_azure:
        status["deployment"] = router.deployment
        status["api_version"] = router.api_version
        status["clean_endpoint"] = _api_extract_azure_base(router.base_endpoint)
    return status


class APIRouter:
    """Route queries to Azure OpenAI or standard OpenAI API (online mode)."""

    def __init__(self, config: Config, api_key: str, endpoint: str = "",
                 deployment_override: str = "", api_version_override: str = "",
                 provider_override: str = ""):
        self.config = config
        self.api_key = api_key
        self.logger = get_app_logger("api_router")
        self.last_error = ""
        self.provider = provider_override or ""
        self.http_api_client = None
        self._init_error = ""
        self.base_endpoint = endpoint.rstrip("/") if endpoint else config.api.endpoint.rstrip("/")

        if self.provider in ("azure", "azure_gov"):
            self.is_azure = True
        elif self.provider == "openai":
            self.is_azure = False
        else:
            self.is_azure = ("azure" in self.base_endpoint.lower()
                             or "aoai" in self.base_endpoint.lower())

        self.deployment = (deployment_override
                           if deployment_override
                           else _resolve_deployment(config, self.base_endpoint))
        self.api_version = (api_version_override
                            if api_version_override
                            else _resolve_api_version(config, self.base_endpoint))

        try:
            get_gate().check_allowed(self.base_endpoint, "api_client_init", "api_router")
        except NetworkBlockedError as e:
            self.client = None
            self.logger.error("api_endpoint_blocked_by_gate",
                              endpoint=self.base_endpoint, error=str(e))
            return

        try:
            from openai import AzureOpenAI, OpenAI
        except ImportError:
            self.client = None
            self._init_error = "openai SDK missing"
            self.logger.error("openai_sdk_missing", hint="Run: pip install openai")
            return

        try:
            if self.is_azure:
                clean_ep = self._extract_azure_base(self.base_endpoint)
                self.client = AzureOpenAI(
                    azure_endpoint=clean_ep, api_key=self.api_key,
                    api_version=self.api_version,
                    http_client=_build_httpx_client(
                        timeout=getattr(self.config.api, "timeout_seconds", 60)),
                )
                self.logger.info("api_router_init", provider="azure_openai",
                                 endpoint=clean_ep, deployment=self.deployment,
                                 api_version=self.api_version, sdk="openai_official")
            else:
                kw = {"api_key": self.api_key}
                if self.base_endpoint and "openai.com" not in self.base_endpoint:
                    kw["base_url"] = self.base_endpoint
                self.client = OpenAI(**kw)
                self.logger.info("api_router_init", provider="openai", sdk="openai_official")
        except Exception as e:
            self.client = None
            self._init_error = str(e)
            self.logger.error("api_router_init_failed", error=str(e))
            self._init_http_fallback_client()

        if self.client is None and self.http_api_client is None:
            self._init_http_fallback_client()

    def _init_http_fallback_client(self):
        _api_init_http_fallback_client(self)

    def _reinit_sdk_client(self):
        _api_reinit_sdk_client(self)

    def _attempt_late_init(self):
        _api_attempt_late_init(self)

    def _extract_azure_base(self, url: str) -> str:
        return _api_extract_azure_base(url)

    def query(self, prompt: str) -> Optional[LLMResponse]:
        """Send a prompt to the API and get the AI-generated answer back."""
        self.last_error = ""
        if self.client is None and self.http_api_client is None:
            self._attempt_late_init()
        if self.client is None and self.http_api_client is None:
            detail = self._init_error.strip() if isinstance(self._init_error, str) else ""
            self.last_error = (f"API client not ready (SDK missing or init failed): {detail}"
                               if detail else "API client not ready (SDK missing or init failed)")
            self.logger.error("api_client_not_ready",
                              hint="openai SDK not installed and HTTP fallback unavailable")
            return None

        try:
            get_gate().check_allowed(self.base_endpoint, "api_query", "api_router")
        except NetworkBlockedError as e:
            gate_mode = getattr(get_gate(), "mode_name", "offline")
            if gate_mode == "offline":
                self.last_error = ("Network access is blocked because the app is in Offline Mode. "
                                   "Switch to Online Mode, then verify Admin > API Credentials.")
            else:
                self.last_error = ("Network access blocked by endpoint allowlist. "
                                   "Verify Admin > API Credentials and approved endpoint settings.")
            self.logger.error("api_query_blocked_by_gate", error=str(e))
            return None

        if getattr(self.config, "security", None) and self.config.security.pii_sanitization:
            from src.security.pii_scrubber import scrub_pii
            prompt, pii_count = scrub_pii(prompt)
            if pii_count > 0:
                self.logger.info("pii_scrubbed", count=pii_count)

        start_time = time.time()
        if self.is_azure:
            model_name = (self.deployment or "").strip()
        else:
            configured_model = (getattr(getattr(self.config, "api", None), "model", "") or "").strip()
            selected_model = (self.deployment or "").strip()
            model_name = configured_model or selected_model

        if not model_name:
            self.last_error = ("No online model selected. Verify Admin > Online Model Selection "
                               "or configure api.model/api.deployment.")
            self.logger.error("api_model_not_configured", is_azure=self.is_azure)
            return None

        try:
            self.logger.info("api_query_sending",
                             provider="azure" if self.is_azure else "openai", model=model_name)
            messages = _split_prompt_to_messages(prompt)
            generation_params = build_api_generation_params(
                self.config.api,
                provider=("azure" if self.is_azure else getattr(self.config.api, "provider", "")),
                endpoint=self.base_endpoint,
            )
            if self.client is not None:
                response = self.client.chat.completions.create(
                    model=model_name, messages=messages, **generation_params)
                answer_text = response.choices[0].message.content
                tokens_in = response.usage.prompt_tokens if response.usage else 0
                tokens_out = response.usage.completion_tokens if response.usage else 0
                actual_model = response.model or model_name
            else:
                sys_msg, usr_msg = _extract_system_user(prompt)
                fallback = self.http_api_client.chat(
                    user_message=usr_msg, system_prompt=sys_msg or None,
                    generation_params=generation_params)
                answer_text = fallback.get("answer", "")
                usage = fallback.get("usage", {}) or {}
                tokens_in = usage.get("prompt_tokens", 0)
                tokens_out = usage.get("completion_tokens", 0)
                actual_model = fallback.get("model", model_name) or model_name
            latency_ms = (time.time() - start_time) * 1000
            self.logger.info("api_query_success", model=actual_model,
                             tokens_in=tokens_in, tokens_out=tokens_out,
                             latency_ms=latency_ms, is_azure=self.is_azure)
            return LLMResponse(text=answer_text, tokens_in=tokens_in,
                               tokens_out=tokens_out, model=actual_model,
                               latency_ms=latency_ms)
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            error_name = type(e).__name__
            error_msg = str(e)
            self.last_error = f"{error_name}: {error_msg}"
            self._log_api_error(error_name, error_msg)
            return None

    def _log_api_error(self, error_name: str, error_msg: str):
        """Classify and log API errors with troubleshooting hints."""
        if "401" in error_msg or "Unauthorized" in error_msg:
            self.logger.error("api_auth_error", error=error_msg[:500],
                              hint="Check API key, run rag-store-key, verify Azure RBAC.")
        elif "404" in error_msg or "NotFound" in error_msg:
            self.logger.error("api_not_found", error=error_msg[:500],
                              hint=f"Deployment '{self.deployment}' not found. Check Azure portal.")
        elif "429" in error_msg or "RateLimit" in error_msg:
            self.logger.error("api_rate_limited", error=error_msg[:200],
                              hint="Wait 30-60 seconds and retry.")
        elif "SSL" in error_msg or "certificate" in error_msg.lower():
            self.logger.error("api_ssl_error", error=error_msg[:500],
                              hint="Install pip-system-certs; check enterprise LAN vs VPN.")
        elif "Connection" in error_name or "connect" in error_msg.lower():
            self.logger.error("api_connection_error", error=error_msg[:500],
                              hint="Check VPN/network connection and firewall rules.")
        elif "Timeout" in error_name or "timed out" in error_msg.lower():
            self.logger.error("api_timeout", error=error_msg[:200],
                              timeout_seconds=self.config.api.timeout_seconds)
        else:
            self.logger.error("api_error", error_type=error_name, error=error_msg[:500])

    def get_status(self) -> Dict[str, Any]:
        return _api_get_status(self)
