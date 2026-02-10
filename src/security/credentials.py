# ============================================================================
# HybridRAG v3 — Secure Credential Manager (src/security/credentials.py)
# ============================================================================
#
# WHAT THIS FILE DOES:
#   Stores and retrieves your API key securely using Windows Credential
#   Manager — the same system Chrome and Edge use for passwords.
#   Your API key is encrypted with Windows DPAPI, tied to YOUR Windows
#   login. No one else on the machine can read it. Nothing on disk.
#
# WHY THIS MATTERS:
#   Common rookie mistakes with API keys:
#     ❌ Hardcoding in Python: api_key = "sk-abc123"
#     ❌ Storing in config.yaml (gets committed to git)
#     ❌ Storing in .env file (can be read by anyone with file access)
#     ✅ Windows Credential Manager (encrypted, tied to your login)
#
# HOW IT WORKS:
#   1. You run: rag-store-key  (enters your API key once)
#   2. keyring.set_password() calls Windows DPAPI to encrypt the key
#   3. The encrypted key is stored in Windows Credential Manager
#   4. When HybridRAG needs the key, it calls keyring.get_password()
#   5. Windows decrypts it using YOUR login credentials
#   6. Different Windows user = can't decrypt = key is safe
#
# VERIFICATION:
#   You can see the stored credential in Windows:
#   Start Menu → search "Credential Manager" → Windows Credentials
#   Look for "HybridRAG_v3" — that's your encrypted API key
#
# FALLBACK CHAIN (in order of priority):
#   1. keyring (Windows Credential Manager) — most secure
#   2. OPENAI_API_KEY environment variable — less secure but functional
#   3. None — online mode disabled, offline mode still works
#
# DEPENDENCIES:
#   - keyring: Already in requirements.txt. Uses Windows Credential
#     Manager on Windows, macOS Keychain on Mac, SecretService on Linux.
#
# INTERNET ACCESS: NONE. This file never touches the network.
# ============================================================================

import os
import sys
import getpass  # For secure password input (hides what you type)

# ── Try to import keyring ───────────────────────────────────────────────────
# keyring should already be installed (it's in requirements.txt), but if
# it's not, we handle it gracefully and fall back to environment variables.
# ────────────────────────────────────────────────────────────────────────────
try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

# ── Constants ───────────────────────────────────────────────────────────────
# SERVICE_NAME: The "account name" Windows Credential Manager uses to
#   organize credentials. Like a folder name for our app's secrets.
# KEY_NAME_API: The specific credential name for the API key.
# KEY_NAME_ENDPOINT: The specific credential name for the API endpoint URL.
# ────────────────────────────────────────────────────────────────────────────
SERVICE_NAME = "HybridRAG_v3"
KEY_NAME_API = "api_key"
KEY_NAME_ENDPOINT = "api_endpoint"


def store_api_key(api_key: str) -> bool:
    """
    Securely store an API key in Windows Credential Manager.

    Args:
        api_key: The API key string (e.g., "sk-abc123...")

    Returns:
        True if stored successfully, False if keyring unavailable

    What happens under the hood:
        1. keyring calls Windows DPAPI (Data Protection API)
        2. DPAPI encrypts the key using your Windows login credentials
        3. The encrypted blob is stored in Windows Credential Manager
        4. It appears as "HybridRAG_v3" → "api_key" in Credential Manager
    """
    if not KEYRING_AVAILABLE:
        print("WARNING: keyring not installed. Cannot store securely.")
        print("  Install with: pip install keyring")
        print("  Falling back to environment variable OPENAI_API_KEY")
        return False

    try:
        keyring.set_password(SERVICE_NAME, KEY_NAME_API, api_key)
        return True
    except Exception as e:
        print(f"WARNING: Could not store in Credential Manager: {e}")
        return False


def store_api_endpoint(endpoint: str) -> bool:
    """
    Securely store a custom API endpoint URL in Windows Credential Manager.

    Args:
        endpoint: The API endpoint URL (e.g., "https://your-company.com/v1/chat/completions")

    Returns:
        True if stored successfully, False if keyring unavailable

    Why store this securely?
        Your company's internal API endpoint URL might be considered
        sensitive information. Storing it in Credential Manager keeps it
        out of config files and git repos.
    """
    if not KEYRING_AVAILABLE:
        print("WARNING: keyring not installed. Cannot store endpoint securely.")
        return False

    try:
        keyring.set_password(SERVICE_NAME, KEY_NAME_ENDPOINT, endpoint)
        return True
    except Exception as e:
        print(f"WARNING: Could not store endpoint: {e}")
        return False


def get_api_key() -> str:
    """
    Retrieve the API key using the secure fallback chain.

    Priority order:
        1. Windows Credential Manager (via keyring) — most secure
        2. OPENAI_API_KEY environment variable — less secure but works
        3. Returns empty string — online mode will be disabled

    Returns:
        The API key string, or empty string if not found anywhere

    Note: This function NEVER prints the key. It only returns it to
    the calling code (LLMRouter) which uses it in the Authorization
    header. The key never appears in logs or console output.
    """
    # ── Try keyring first (most secure) ──
    if KEYRING_AVAILABLE:
        try:
            key = keyring.get_password(SERVICE_NAME, KEY_NAME_API)
            if key:
                return key
        except Exception:
            pass  # Fall through to env var

    # ── Try environment variable (less secure but functional) ──
    key = os.environ.get("OPENAI_API_KEY", "")
    return key


def get_api_endpoint() -> str:
    """
    Retrieve the custom API endpoint using the fallback chain.

    Priority order:
        1. Windows Credential Manager (via keyring)
        2. OPENAI_API_ENDPOINT environment variable
        3. Returns empty string — will use default from config.yaml

    Returns:
        The endpoint URL string, or empty string if not found
    """
    # ── Try keyring first ──
    if KEYRING_AVAILABLE:
        try:
            endpoint = keyring.get_password(SERVICE_NAME, KEY_NAME_ENDPOINT)
            if endpoint:
                return endpoint
        except Exception:
            pass

    # ── Try environment variable ──
    return os.environ.get("OPENAI_API_ENDPOINT", "")


def delete_api_key() -> bool:
    """
    Remove the stored API key from Windows Credential Manager.

    Use this if you need to rotate your key or remove it for security.

    Returns:
        True if deleted successfully, False otherwise
    """
    if not KEYRING_AVAILABLE:
        return False

    try:
        keyring.delete_password(SERVICE_NAME, KEY_NAME_API)
        return True
    except keyring.errors.PasswordDeleteError:
        # Key wasn't stored — that's fine
        return True
    except Exception as e:
        print(f"WARNING: Could not delete credential: {e}")
        return False


def delete_api_endpoint() -> bool:
    """Remove the stored API endpoint from Windows Credential Manager."""
    if not KEYRING_AVAILABLE:
        return False

    try:
        keyring.delete_password(SERVICE_NAME, KEY_NAME_ENDPOINT)
        return True
    except keyring.errors.PasswordDeleteError:
        return True
    except Exception:
        return False


def credential_status() -> dict:
    """
    Check what credentials are currently available.

    Returns a dictionary showing where each credential was found.
    Useful for diagnostics and the self-test system.

    Returns:
        {
            "api_key_source": "keyring" | "env_var" | "none",
            "api_key_set": True | False,
            "api_endpoint_source": "keyring" | "env_var" | "config" | "none",
            "api_endpoint_set": True | False,
            "keyring_available": True | False,
        }
    """
    status = {
        "keyring_available": KEYRING_AVAILABLE,
        "api_key_source": "none",
        "api_key_set": False,
        "api_endpoint_source": "none",
        "api_endpoint_set": False,
    }

    # Check API key
    if KEYRING_AVAILABLE:
        try:
            if keyring.get_password(SERVICE_NAME, KEY_NAME_API):
                status["api_key_source"] = "keyring"
                status["api_key_set"] = True
        except Exception:
            pass

    if not status["api_key_set"] and os.environ.get("OPENAI_API_KEY"):
        status["api_key_source"] = "env_var"
        status["api_key_set"] = True

    # Check API endpoint
    if KEYRING_AVAILABLE:
        try:
            if keyring.get_password(SERVICE_NAME, KEY_NAME_ENDPOINT):
                status["api_endpoint_source"] = "keyring"
                status["api_endpoint_set"] = True
        except Exception:
            pass

    if not status["api_endpoint_set"] and os.environ.get("OPENAI_API_ENDPOINT"):
        status["api_endpoint_source"] = "env_var"
        status["api_endpoint_set"] = True

    return status


# ============================================================================
# CLI ENTRY POINT — Run this file directly to manage credentials
# ============================================================================
# Usage:
#   python -m src.security.credentials store     # Store API key
#   python -m src.security.credentials status    # Check what's stored
#   python -m src.security.credentials delete    # Remove stored key
#   python -m src.security.credentials endpoint  # Store custom endpoint
# ============================================================================
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.security.credentials [store|status|delete|endpoint]")
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "store":
        print("=" * 50)
        print("HybridRAG v3 — Store API Key")
        print("=" * 50)
        print()
        print("Your key will be encrypted in Windows Credential Manager.")
        print("It will NOT appear in any file, log, or config.")
        print()
        # getpass.getpass() hides input — no one can shoulder-surf
        api_key = getpass.getpass("Paste your API key (input is hidden): ")
        if not api_key.strip():
            print("No key entered. Aborted.")
            sys.exit(1)

        if store_api_key(api_key.strip()):
            print("\n✅ API key stored securely in Windows Credential Manager.")
            print("   Verify: Start Menu → Credential Manager → Windows Credentials")
            print(f"   Look for: {SERVICE_NAME}")
        else:
            print("\n❌ Could not store in Credential Manager.")
            print("   Set OPENAI_API_KEY environment variable as fallback.")

    elif command == "endpoint":
        print("=" * 50)
        print("HybridRAG v3 — Store Custom API Endpoint")
        print("=" * 50)
        print()
        endpoint = input("Enter your API endpoint URL: ").strip()
        if not endpoint:
            print("No endpoint entered. Aborted.")
            sys.exit(1)

        if store_api_endpoint(endpoint):
            print(f"\n✅ Endpoint stored: {endpoint}")
        else:
            print("\n❌ Could not store endpoint.")
            print("   Set OPENAI_API_ENDPOINT environment variable as fallback.")

    elif command == "status":
        print("=" * 50)
        print("HybridRAG v3 — Credential Status")
        print("=" * 50)
        s = credential_status()
        print(f"\n  keyring available:  {'YES' if s['keyring_available'] else 'NO'}")
        print(f"  API key found:      {'YES' if s['api_key_set'] else 'NO'} (source: {s['api_key_source']})")
        print(f"  API endpoint found: {'YES' if s['api_endpoint_set'] else 'NO'} (source: {s['api_endpoint_source']})")

        if s["api_key_set"]:
            # Show first 8 chars only for verification (never the full key)
            key = get_api_key()
            masked = key[:8] + "..." + key[-4:] if len(key) > 12 else "***"
            print(f"  API key preview:    {masked}")

    elif command == "delete":
        print("Deleting stored credentials...")
        delete_api_key()
        delete_api_endpoint()
        print("✅ Credentials removed from Windows Credential Manager.")

    else:
        print(f"Unknown command: {command}")
        print("Usage: python -m src.security.credentials [store|status|delete|endpoint]")
        sys.exit(1)
