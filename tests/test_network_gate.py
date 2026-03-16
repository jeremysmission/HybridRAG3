# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies behavior for the network gate (zero-trust access control) module.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# test_network_gate.py -- Tests for NetworkGate (centralized network access)
# ============================================================================
#
# COVERS:
#   1. Default mode is OFFLINE (fail-closed)
#   2. OFFLINE allows localhost, blocks external
#   3. ONLINE allows configured endpoints, blocks others
#   4. ADMIN allows everything
#   5. Audit log records allowed and denied attempts
#   6. Singleton pattern
#   7. Mode transitions
#   8. Environment variable kill-switch override
#   9. Prefix-based allowlisting
#  10. Non-HTTP scheme rejection
#
# RUN:
#   python -m pytest tests/test_network_gate.py -v
#
# INTERNET ACCESS: NONE -- no real connections are made
# ============================================================================

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.network_gate import (
    NetworkGate,
    NetworkMode,
    NetworkBlockedError,
    get_gate,
    configure_gate,
    reset_gate,
)


@pytest.fixture(autouse=True)
def _reset_singleton(monkeypatch):
    """Reset the module-level singleton and env vars before and after every test."""
    for var in ("HYBRIDRAG_OFFLINE", "HYBRIDRAG_NETWORK_KILL_SWITCH"):
        monkeypatch.delenv(var, raising=False)
    reset_gate()
    yield
    reset_gate()


@pytest.fixture()
def gate():
    """Fresh NetworkGate instance (not the singleton)."""
    return NetworkGate()


# ============================================================================
# 1. DEFAULT MODE
# ============================================================================

class TestDefaultMode:
    def test_defaults_to_offline(self, gate):
        assert gate.mode == NetworkMode.OFFLINE
        assert gate.mode_name == "offline"

    def test_unconfigured_gate_blocks_external(self, gate):
        with pytest.raises(NetworkBlockedError):
            gate.check_allowed("https://example.com", "test")


# ============================================================================
# 2. OFFLINE MODE
# ============================================================================

class TestOfflineMode:
    def test_allows_localhost(self, gate):
        gate.check_allowed("http://localhost:11434/api/generate", "ollama")

    def test_allows_127(self, gate):
        gate.check_allowed("http://127.0.0.1:11434/api/generate", "ollama")

    def test_allows_ipv6_loopback(self, gate):
        gate.check_allowed("http://[::1]:11434/api/generate", "ollama")

    def test_blocks_external(self, gate):
        with pytest.raises(NetworkBlockedError) as exc_info:
            gate.check_allowed("https://api.openai.com/v1/chat", "query")
        assert exc_info.value.mode == "offline"
        assert "api.openai.com" in exc_info.value.reason

    def test_blocks_non_http_scheme(self, gate):
        with pytest.raises(NetworkBlockedError) as exc_info:
            gate.check_allowed("ftp://files.example.com/data", "download")
        assert "ftp" in exc_info.value.reason


# ============================================================================
# 3. ONLINE MODE
# ============================================================================

class TestOnlineMode:
    def test_allows_configured_endpoint(self, gate):
        gate.configure("online", api_endpoint="https://myco.openai.azure.com/v1")
        gate.check_allowed("https://myco.openai.azure.com/v1/chat", "api_query")

    def test_allows_localhost_in_online(self, gate):
        gate.configure("online", api_endpoint="https://myco.openai.azure.com/v1")
        gate.check_allowed("http://localhost:11434/api/generate", "ollama")

    def test_blocks_non_allowlisted_host(self, gate):
        gate.configure("online", api_endpoint="https://myco.openai.azure.com/v1")
        with pytest.raises(NetworkBlockedError) as exc_info:
            gate.check_allowed("https://evil.example.com/steal", "unknown")
        assert exc_info.value.mode == "online"

    def test_blocks_wrong_scheme(self, gate):
        gate.configure("online", api_endpoint="https://myco.openai.azure.com/v1")
        with pytest.raises(NetworkBlockedError):
            gate.check_allowed("http://myco.openai.azure.com/v1/chat", "query")

    def test_blocks_wrong_port(self, gate):
        gate.configure("online", api_endpoint="https://myco.openai.azure.com:443/v1")
        with pytest.raises(NetworkBlockedError):
            gate.check_allowed("https://myco.openai.azure.com:8443/v1/chat", "query")


# ============================================================================
# 4. ONLINE MODE -- PREFIX ALLOWLISTING
# ============================================================================

class TestPrefixAllowlist:
    def test_allows_matching_prefix(self, gate):
        gate.configure(
            "online",
            allowed_prefixes=["https://proxy.corp.com/api/"],
        )
        gate.check_allowed("https://proxy.corp.com/api/v1/chat", "query")

    def test_blocks_non_matching_path(self, gate):
        gate.configure(
            "online",
            allowed_prefixes=["https://proxy.corp.com/api/"],
        )
        with pytest.raises(NetworkBlockedError):
            gate.check_allowed("https://proxy.corp.com/admin/secrets", "bad")

    def test_path_boundary_no_partial_match(self, gate):
        """Prefix /api must NOT match /api2 (path boundary enforcement)."""
        gate.configure(
            "online",
            allowed_prefixes=["https://proxy.corp.com/api"],
        )
        with pytest.raises(NetworkBlockedError):
            gate.check_allowed("https://proxy.corp.com/api2/exploit", "bad")


# ============================================================================
# 5. ADMIN MODE
# ============================================================================

class TestAdminMode:
    def test_allows_any_url(self, gate):
        gate.configure("admin")
        gate.check_allowed("https://pypi.org/simple/", "pip_install")
        gate.check_allowed("https://random.example.com", "maintenance")

    def test_allows_ftp_in_admin(self, gate):
        gate.configure("admin")
        gate.check_allowed("ftp://files.example.com/data", "download")


# ============================================================================
# 6. AUDIT LOG
# ============================================================================

class TestAuditLog:
    def test_records_allowed_attempt(self, gate):
        gate.check_allowed("http://localhost:11434", "ollama", "boot")
        log = gate.get_audit_log()
        assert len(log) == 1
        assert log[0].allowed is True
        assert log[0].purpose == "ollama"
        assert log[0].caller == "boot"

    def test_records_denied_attempt(self, gate):
        with pytest.raises(NetworkBlockedError):
            gate.check_allowed("https://evil.com", "probe", "attacker")
        log = gate.get_audit_log()
        assert len(log) == 1
        assert log[0].allowed is False
        assert log[0].host == "evil.com"

    def test_audit_summary_counts(self, gate):
        gate.check_allowed("http://localhost:11434", "ok")
        with pytest.raises(NetworkBlockedError):
            gate.check_allowed("https://bad.com", "probe")
        summary = gate.get_audit_summary()
        assert summary["total_checks"] == 2
        assert summary["allowed"] == 1
        assert summary["denied"] == 1

    def test_clear_audit_log(self, gate):
        gate.check_allowed("http://localhost:11434", "test")
        cleared = gate.clear_audit_log()
        assert cleared == 1
        assert len(gate.get_audit_log()) == 0


# ============================================================================
# 7. SINGLETON PATTERN
# ============================================================================

class TestSingleton:
    def test_get_gate_returns_same_instance(self):
        g1 = get_gate()
        g2 = get_gate()
        assert g1 is g2

    def test_configure_gate_returns_singleton(self):
        g = configure_gate("offline")
        assert g is get_gate()

    def test_reset_gate_creates_new_instance(self):
        g1 = get_gate()
        reset_gate()
        g2 = get_gate()
        assert g1 is not g2


# ============================================================================
# 8. MODE TRANSITIONS
# ============================================================================

class TestModeTransitions:
    def test_offline_to_online(self, gate):
        assert gate.mode == NetworkMode.OFFLINE
        gate.configure("online", api_endpoint="https://api.example.com")
        assert gate.mode == NetworkMode.ONLINE

    def test_online_to_admin(self, gate):
        gate.configure("online", api_endpoint="https://api.example.com")
        gate.configure("admin")
        assert gate.mode == NetworkMode.ADMIN

    def test_admin_back_to_offline(self, gate):
        gate.configure("admin")
        gate.configure("offline")
        assert gate.mode == NetworkMode.OFFLINE

    def test_unrecognized_mode_defaults_offline(self, gate):
        gate.configure("bogus_mode")
        assert gate.mode == NetworkMode.OFFLINE


# ============================================================================
# 9. ENVIRONMENT VARIABLE KILL-SWITCH
# ============================================================================

class TestEnvKillSwitch:
    def test_hybridrag_offline_forces_offline(self, gate):
        with patch.dict(os.environ, {"HYBRIDRAG_OFFLINE": "1"}):
            gate.configure("online", api_endpoint="https://api.example.com")
        assert gate.mode == NetworkMode.OFFLINE

    def test_kill_switch_env_forces_offline(self, gate):
        with patch.dict(os.environ, {"HYBRIDRAG_NETWORK_KILL_SWITCH": "true"}):
            gate.configure("admin")
        assert gate.mode == NetworkMode.OFFLINE


# ============================================================================
# 10. is_allowed HELPER
# ============================================================================

class TestIsAllowed:
    def test_returns_true_for_localhost(self, gate):
        assert gate.is_allowed("http://localhost:11434") is True

    def test_returns_false_for_blocked(self, gate):
        assert gate.is_allowed("https://evil.com") is False
