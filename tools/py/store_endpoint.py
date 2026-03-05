# === NON-PROGRAMMER GUIDE ===
# Purpose: Automates the store endpoint operational workflow for developers or operators.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# store_endpoint.py -- Store API endpoint + Azure deployment + API version
# ============================================================================
# Extended to prompt for all Azure connection values in one session:
#   1. Endpoint URL (required)
#   2. Deployment name (optional, for Azure)
#   3. API version (optional, for Azure)
#   4. Confirm and store
#
# INTERNET ACCESS: NONE -- only writes to local keyring
# ============================================================================

import sys
import os

sys.path.insert(0, os.environ.get("HYBRIDRAG_PROJECT_ROOT", "."))

from src.security.credentials import (
    store_endpoint, store_deployment, store_api_version,
    validate_endpoint,
)


def main():
    # --- Step 1: Endpoint URL (required) ---
    if len(sys.argv) > 1:
        endpoint = sys.argv[1]
    else:
        print("  Enter your API endpoint URL:")
        try:
            endpoint = input("  Endpoint: ")
        except EOFError:
            endpoint = ""

    if not endpoint or not endpoint.strip():
        print("  [FAIL] No endpoint entered. Nothing stored.")
        sys.exit(1)

    endpoint = endpoint.strip()

    # Validate before storing
    try:
        endpoint = validate_endpoint(endpoint)
    except Exception as e:
        print(f"  [FAIL] Invalid endpoint URL: {e}")
        sys.exit(1)

    # --- Step 2: Deployment name (optional) ---
    print()
    print("  Azure deployment name (press Enter to skip):")
    print("  Examples: gpt-4o, gpt-35-turbo, gpt-4.1")
    try:
        deployment = input("  Deployment: ")
    except EOFError:
        deployment = ""

    deployment = deployment.strip() if deployment else ""

    # --- Step 3: API version (optional) ---
    print()
    print("  Azure API version (press Enter to skip):")
    print("  Examples: 2024-02-02, 2024-08-01-preview")
    try:
        api_version = input("  API Version: ")
    except EOFError:
        api_version = ""

    api_version = api_version.strip() if api_version else ""

    # --- Step 4: Confirm and store ---
    print()
    print("  Summary:")
    print(f"    Endpoint:   {endpoint}")
    print(f"    Deployment: {deployment or '(not set)'}")
    print(f"    API Version: {api_version or '(not set)'}")
    print()

    errors = []

    try:
        store_endpoint(endpoint)
        print(f"  [OK] Endpoint stored: {endpoint}")
    except Exception as e:
        errors.append(("Endpoint", str(e)))
        print(f"  [FAIL] Could not store endpoint: {e}")

    if deployment:
        try:
            store_deployment(deployment)
            print(f"  [OK] Deployment stored: {deployment}")
        except Exception as e:
            errors.append(("Deployment", str(e)))
            print(f"  [FAIL] Could not store deployment: {e}")

    if api_version:
        try:
            store_api_version(api_version)
            print(f"  [OK] API version stored: {api_version}")
        except Exception as e:
            errors.append(("API Version", str(e)))
            print(f"  [FAIL] Could not store API version: {e}")

    if errors:
        print()
        print("  [WARN] Keyring storage failed for: {}".format(
            ", ".join(name for name, _ in errors)))
        print()
        print("  This usually means the keyring config is broken.")
        print("  Fix: Delete or repair this file, then retry:")
        cfg_path = os.path.join(
            os.environ.get("LOCALAPPDATA", ""),
            "Python Keyring", "keyringrc.cfg",
        )
        print(f"    {cfg_path}")
        print()
        print("  Or set backend to Windows Credential Manager:")
        print("    [backend]")
        print("    default-keyring = keyring.backends.Windows.WinVaultKeyring")
        sys.exit(1)


if __name__ == "__main__":
    main()
