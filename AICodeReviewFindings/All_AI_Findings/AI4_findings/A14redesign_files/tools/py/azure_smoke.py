# ============================================================================
# HybridRAG v3 - Quick Azure API Test (utility script)
# ============================================================================
# This is a *manual* connectivity check. It is NOT a pytest test.
#
# Credential source:
#   - Windows Credential Manager / keyring (service: "hybridrag")
#   - Keys:
#       endpoint -> "endpoint"
#       api_key  -> "api_key"
#
# NOTE:
#   Keyring backends vary by OS. On Linux CI, keyring may be unavailable.
#   This file must never break automated test collection.
# ============================================================================

__test__ = False  # do not let pytest collect this as a test module

from __future__ import annotations

def main() -> int:
    try:
        import keyring
    except Exception:
        print("keyring not available on this system.")
        return 2

    try:
        from openai import AzureOpenAI
    except Exception as e:
        print(f"openai SDK not available: {e}")
        return 2

    endpoint = keyring.get_password("hybridrag", "endpoint")
    api_key = keyring.get_password("hybridrag", "api_key")
    if not endpoint or not api_key:
        print("Missing keyring credentials: endpoint and/or api_key")
        return 2

    client = AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version="2024-02-02",
    )

    r = client.chat.completions.create(
        model="gpt-35-turbo",
        messages=[{"role": "user", "content": "say hello"}],
    )
    print(r.choices[0].message.content)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
