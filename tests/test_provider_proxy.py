# ============================================================================
# test_provider_proxy.py -- Tests for dual-environment API layer
# ============================================================================
#
# COVERS:
#   1. Provider detection: azure, azure_gov, openai, auto-detect
#   2. Proxy auto-detection from env vars
#   3. CA bundle auto-detection from env vars
#   4. Localhost clients never proxied
#   5. Government endpoint URL patterns
#   6. Provider credential resolution
#
# RUN:
#   python -m pytest tests/test_provider_proxy.py -v
#
# INTERNET ACCESS: NONE -- all external calls are mocked
# ============================================================================

import os
import sys
from unittest.mock import MagicMock, patch
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from conftest import FakeConfig


class TestBuildHttpxClient:
    """Tests for the _build_httpx_client() factory function."""

    def _get_factory(self):
        """Import factory, patching out network gate to avoid import issues."""
        with patch("src.core.llm_router.get_gate", return_value=MagicMock()):
            from src.core.llm_router import _build_httpx_client
        return _build_httpx_client

    # ------------------------------------------------------------------
    # Test P-01: Default client has no proxy when env is clean
    # ------------------------------------------------------------------
    def test_p01_default_no_proxy(self):
        """Default client should not use a proxy when no env vars are set."""
        factory = self._get_factory()
        env_clean = {
            "HTTPS_PROXY": "", "https_proxy": "",
            "HTTP_PROXY": "", "http_proxy": "",
            "REQUESTS_CA_BUNDLE": "", "SSL_CERT_FILE": "",
            "CURL_CA_BUNDLE": "",
        }
        with patch.dict(os.environ, env_clean, clear=False):
            # Remove any existing proxy env vars
            for k in env_clean:
                os.environ.pop(k, None)
            client = factory(timeout=10)
        try:
            # Client should be created without error
            assert client is not None
        finally:
            client.close()

    # ------------------------------------------------------------------
    # Test P-02: non-localhost client uses trust_env=True so httpx
    # picks up HTTPS_PROXY AND honours NO_PROXY natively.
    # ------------------------------------------------------------------
    def test_p02_proxy_from_env(self):
        """Non-localhost client should use trust_env=True (httpx reads proxy env natively)."""
        factory = self._get_factory()
        import httpx
        with patch.dict(os.environ, {
            "HTTPS_PROXY": "http://proxy.corp.internal:8080"
        }, clear=False):
            with patch("httpx.Client") as mock_client_cls:
                mock_client_cls.return_value = MagicMock()
                client = factory(timeout=30)
                call_kwargs = mock_client_cls.call_args
                assert call_kwargs is not None
                kwargs = call_kwargs[1] if call_kwargs[1] else {}
                # trust_env=True lets httpx read proxy env AND NO_PROXY
                assert kwargs.get("trust_env") is True
                # proxy= must NOT be set explicitly (bypasses NO_PROXY)
                assert "proxy" not in kwargs

    # ------------------------------------------------------------------
    # Test P-03: localhost_only=True forces proxy=None
    # ------------------------------------------------------------------
    def test_p03_localhost_no_proxy(self):
        """localhost_only=True must force proxy=None even when HTTPS_PROXY is set."""
        factory = self._get_factory()
        with patch.dict(os.environ, {
            "HTTPS_PROXY": "http://proxy.corp.internal:8080"
        }, clear=False):
            with patch("httpx.Client") as mock_client_cls:
                mock_client_cls.return_value = MagicMock()
                client = factory(timeout=30, localhost_only=True)
                kwargs = mock_client_cls.call_args[1]
                assert kwargs.get("proxy") is None

    # ------------------------------------------------------------------
    # Test P-04: REQUESTS_CA_BUNDLE flows to verify param
    # ------------------------------------------------------------------
    def test_p04_ca_bundle_from_env(self, tmp_path):
        """REQUESTS_CA_BUNDLE should set verify= to the CA bundle path."""
        factory = self._get_factory()
        # Create a fake CA bundle file
        ca_file = tmp_path / "corp-ca-bundle.crt"
        ca_file.write_text("fake cert")
        with patch.dict(os.environ, {
            "REQUESTS_CA_BUNDLE": str(ca_file),
            "HTTPS_PROXY": "",
        }, clear=False):
            os.environ.pop("HTTPS_PROXY", None)
            with patch("httpx.Client") as mock_client_cls:
                mock_client_cls.return_value = MagicMock()
                client = factory(timeout=30)
                kwargs = mock_client_cls.call_args[1]
                assert kwargs.get("verify") == str(ca_file)

    # ------------------------------------------------------------------
    # Test P-05: SSL_CERT_FILE is second priority for CA bundle
    # ------------------------------------------------------------------
    def test_p05_ssl_cert_file_fallback(self, tmp_path):
        """SSL_CERT_FILE should be used if REQUESTS_CA_BUNDLE is not set."""
        factory = self._get_factory()
        ca_file = tmp_path / "ssl-cert.pem"
        ca_file.write_text("fake cert")
        with patch.dict(os.environ, {
            "SSL_CERT_FILE": str(ca_file),
        }, clear=False):
            os.environ.pop("REQUESTS_CA_BUNDLE", None)
            os.environ.pop("HTTPS_PROXY", None)
            with patch("httpx.Client") as mock_client_cls:
                mock_client_cls.return_value = MagicMock()
                client = factory(timeout=30)
                kwargs = mock_client_cls.call_args[1]
                assert kwargs.get("verify") == str(ca_file)


class TestProviderDetection:
    """Tests for APIRouter provider detection logic."""

    def _make_router(self, endpoint, provider="", config=None):
        """Create APIRouter with mocked dependencies."""
        if config is None:
            config = FakeConfig(mode="online")
        mock_gate = MagicMock()
        mock_gate.check_allowed.return_value = None
        with patch("src.core.llm_router.get_gate", return_value=mock_gate):
            with patch("src.core.llm_router.get_app_logger") as ml:
                ml.return_value = MagicMock()
                with patch("openai.OpenAI") as MockOpenAI:
                    with patch("openai.AzureOpenAI") as MockAzure:
                        from src.core.llm_router import APIRouter
                        router = APIRouter(
                            config, "test-key", endpoint,
                            provider_override=provider,
                        )
        return router

    # ------------------------------------------------------------------
    # Test D-01: Commercial Azure auto-detected from URL
    # ------------------------------------------------------------------
    def test_d01_azure_commercial_autodetect(self):
        """*.openai.azure.com is auto-detected as Azure."""
        router = self._make_router("https://company.openai.azure.com")
        assert router.is_azure is True

    # ------------------------------------------------------------------
    # Test D-02: Government Azure auto-detected from URL
    # ------------------------------------------------------------------
    def test_d02_azure_government_autodetect(self):
        """*.openai.azure.us is auto-detected as Azure (contains 'azure')."""
        router = self._make_router("https://company.openai.azure.us")
        assert router.is_azure is True

    # ------------------------------------------------------------------
    # Test D-03: Explicit provider="azure_gov" forces Azure mode
    # ------------------------------------------------------------------
    def test_d03_explicit_azure_gov_provider(self):
        """provider='azure_gov' forces is_azure=True regardless of URL."""
        router = self._make_router(
            "https://weird-endpoint.mil/api",
            provider="azure_gov",
        )
        assert router.is_azure is True
        assert router.provider == "azure_gov"

    # ------------------------------------------------------------------
    # Test D-04: Explicit provider="openai" forces non-Azure mode
    # ------------------------------------------------------------------
    def test_d04_explicit_openai_provider(self):
        """provider='openai' forces is_azure=False even if URL contains 'azure'."""
        router = self._make_router(
            "https://my-azure-proxy.internal/v1",
            provider="openai",
        )
        assert router.is_azure is False
        assert router.provider == "openai"

    # ------------------------------------------------------------------
    # Test D-05: OpenRouter auto-detected as non-Azure
    # ------------------------------------------------------------------
    def test_d05_openrouter_non_azure(self):
        """OpenRouter URL is correctly identified as non-Azure."""
        router = self._make_router("https://openrouter.ai/api/v1")
        assert router.is_azure is False

    # ------------------------------------------------------------------
    # Test D-06: provider appears in get_status output
    # ------------------------------------------------------------------
    def test_d06_provider_in_status(self):
        """get_status() returns the provider field."""
        router = self._make_router(
            "https://company.openai.azure.com",
            provider="azure",
        )
        status = router.get_status()
        assert status["provider"] == "azure"

    # ------------------------------------------------------------------
    # Test D-07: Government endpoint base extraction
    # ------------------------------------------------------------------
    def test_d07_gov_endpoint_base_extraction(self):
        """_extract_azure_base() handles .azure.us government endpoints."""
        router = self._make_router(
            "https://company.openai.azure.us/openai/deployments/gpt-4o/chat/completions",
            provider="azure_gov",
        )
        base = router._extract_azure_base(
            "https://company.openai.azure.us/openai/deployments/gpt-4o/chat/completions"
        )
        assert base == "https://company.openai.azure.us"


class TestProviderCredentialResolution:
    """Tests for provider field in credentials resolution."""

    def _clear_env(self):
        """Remove all credential env vars to isolate tests."""
        env_vars = [
            "HYBRIDRAG_API_KEY", "AZURE_OPENAI_API_KEY", "AZURE_OPEN_AI_KEY",
            "OPENAI_API_KEY", "HYBRIDRAG_API_ENDPOINT", "AZURE_OPENAI_ENDPOINT",
            "OPENAI_API_ENDPOINT", "AZURE_OPENAI_BASE_URL", "OPENAI_BASE_URL",
            "AZURE_OPENAI_DEPLOYMENT", "AZURE_DEPLOYMENT", "OPENAI_DEPLOYMENT",
            "AZURE_OPENAI_DEPLOYMENT_NAME", "DEPLOYMENT_NAME", "AZURE_CHAT_DEPLOYMENT",
            "AZURE_OPENAI_API_VERSION", "AZURE_API_VERSION", "OPENAI_API_VERSION",
            "API_VERSION", "HYBRIDRAG_API_PROVIDER", "AZURE_OPENAI_PROVIDER",
        ]
        for var in env_vars:
            os.environ.pop(var, None)

    # ------------------------------------------------------------------
    # Test C-01: provider from env var
    # ------------------------------------------------------------------
    def test_c01_provider_from_env(self):
        """HYBRIDRAG_API_PROVIDER env var resolves to creds.provider."""
        self._clear_env()
        os.environ["HYBRIDRAG_API_PROVIDER"] = "azure_gov"
        mock_keyring = MagicMock()
        mock_keyring.get_password = MagicMock(return_value=None)
        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            from src.security import credentials as creds_mod
            import importlib
            importlib.reload(creds_mod)
            result = creds_mod.resolve_credentials()
        assert result.provider == "azure_gov"
        assert "env:" in result.source_provider
        self._clear_env()

    # ------------------------------------------------------------------
    # Test C-02: provider from config dict
    # ------------------------------------------------------------------
    def test_c02_provider_from_config(self):
        """Config dict api.provider resolves when env/keyring are empty."""
        self._clear_env()
        mock_keyring = MagicMock()
        mock_keyring.get_password = MagicMock(return_value=None)
        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            from src.security import credentials as creds_mod
            import importlib
            importlib.reload(creds_mod)
            result = creds_mod.resolve_credentials(
                config_dict={"api": {"provider": "azure"}}
            )
        assert result.provider == "azure"
        assert result.source_provider == "config"
        self._clear_env()

    # ------------------------------------------------------------------
    # Test C-03: provider in credential_status output
    # ------------------------------------------------------------------
    def test_c03_provider_in_credential_status(self):
        """credential_status() includes provider_set and provider keys."""
        self._clear_env()
        os.environ["HYBRIDRAG_API_PROVIDER"] = "openai"
        mock_keyring = MagicMock()
        mock_keyring.get_password = MagicMock(return_value=None)
        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            from src.security import credentials as creds_mod
            import importlib
            importlib.reload(creds_mod)
            status = creds_mod.credential_status()
        assert status["provider_set"] is True
        assert status["provider"] == "openai"
        self._clear_env()

    # ------------------------------------------------------------------
    # Test C-04: provider in diagnostic dict
    # ------------------------------------------------------------------
    def test_c04_provider_in_diagnostic_dict(self):
        """to_diagnostic_dict() includes provider field."""
        self._clear_env()
        mock_keyring = MagicMock()
        mock_keyring.get_password = MagicMock(return_value=None)
        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            from src.security import credentials as creds_mod
            import importlib
            importlib.reload(creds_mod)
            result = creds_mod.resolve_credentials(
                config_dict={"api": {"provider": "azure_gov"}}
            )
        diag = result.to_diagnostic_dict()
        assert "provider" in diag
        assert diag["provider"] == "azure_gov"
        self._clear_env()

    # ------------------------------------------------------------------
    # Test C-05: provider from keyring
    # ------------------------------------------------------------------
    def test_c05_provider_env_overrides_keyring(self):
        """Env var provider takes priority over keyring (env-first design)."""
        self._clear_env()
        os.environ["HYBRIDRAG_API_PROVIDER"] = "openai"

        def fake_keyring_get(service, key_name):
            if key_name == "api_provider":
                return "azure_gov"
            return None

        mock_keyring = MagicMock()
        mock_keyring.get_password = fake_keyring_get
        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            from src.security import credentials as creds_mod
            import importlib
            importlib.reload(creds_mod)
            result = creds_mod.resolve_credentials(use_cache=False)
        assert result.provider == "openai"
        assert "env:" in result.source_provider
        self._clear_env()


class TestConfigProviderFields:
    """Tests for provider/auth_scheme fields in APIConfig dataclass."""

    # ------------------------------------------------------------------
    # Test CF-01: APIConfig has provider field with empty default
    # ------------------------------------------------------------------
    def test_cf01_apiconfig_provider_default(self):
        """APIConfig.provider defaults to empty string."""
        from src.core.config import APIConfig
        cfg = APIConfig()
        assert cfg.provider == ""

    # ------------------------------------------------------------------
    # Test CF-02: APIConfig has auth_scheme field with empty default
    # ------------------------------------------------------------------
    def test_cf02_apiconfig_auth_scheme_default(self):
        """APIConfig.auth_scheme defaults to empty string."""
        from src.core.config import APIConfig
        cfg = APIConfig()
        assert cfg.auth_scheme == ""

    # ------------------------------------------------------------------
    # Test CF-03: load_config reads provider from YAML
    # ------------------------------------------------------------------
    def test_cf03_load_config_reads_provider(self, tmp_path):
        """load_config() correctly reads api.provider from YAML."""
        yaml_content = (
            "mode: offline\n"
            "api:\n"
            "  provider: azure_gov\n"
            "  auth_scheme: api_key\n"
            "  endpoint: ''\n"
        )
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "default_config.yaml").write_text(yaml_content)
        with patch("src.core.network_gate.configure_gate"):
            from src.core.config import load_config
            config = load_config(str(tmp_path))
        assert config.api.provider == "azure_gov"
        assert config.api.auth_scheme == "api_key"
