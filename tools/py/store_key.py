# ============================================================================
# HybridRAG -- Store Azure API Key (tools/py/store_key.py)
# ============================================================================
#
# WHAT THIS DOES:
#   Saves your Azure OpenAI API key into Windows Credential Manager so
#   HybridRAG can use it later without you having to type it every time.
#   Think of it like saving a Wi-Fi password -- you enter it once, and
#   Windows remembers it securely.
#
# HOW TO USE:
#   python tools/py/store_key.py YOUR_API_KEY_HERE
#
# WHERE THE KEY GOES:
#   Windows Credential Manager -> Generic Credentials -> "hybridrag"
#   You can view it in Control Panel -> Credential Manager if needed.
#
# SAFETY:
#   - The key is stored encrypted by Windows, not in a plain text file
#   - It never appears in git, logs, or config files
#   - Only your Windows user account can read it back
# ============================================================================
import argparse
import os
import sys
import keyring


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Store HybridRAG Azure API key in Windows Credential Manager."
    )
    parser.add_argument(
        "api_key",
        nargs="?",
        help="API key value (optional if HYBRIDRAG_API_KEY is set).",
    )
    return parser.parse_args()


args = parse_args()

# Prefer env var (hides key from process list), then explicit CLI arg.
key = os.environ.get("HYBRIDRAG_API_KEY") or args.api_key
if not key:
    print("  [ERROR] No API key provided (set HYBRIDRAG_API_KEY or pass as argument).")
    sys.exit(1)
try:
    keyring.set_password("hybridrag", "azure_api_key", key)
except Exception as e:
    print("  [FAIL] Keyring storage failed: {}".format(e))
    print()
    print("  This usually means the keyring config is broken.")
    print("  Fix: Delete or repair this file, then retry:")
    cfg_path = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "Python Keyring", "keyringrc.cfg",
    )
    print("    {}".format(cfg_path))
    print()
    print("  Or set backend to Windows Credential Manager:")
    print("    [backend]")
    print("    default-keyring = keyring.backends.Windows.WinVaultKeyring")
    sys.exit(1)

try:
    stored = keyring.get_password("hybridrag", "azure_api_key")
except Exception:
    stored = None

if stored == key:
    print("  [OK] API key stored successfully.")
    print("  Preview: " + stored[:4] + "..." + stored[-4:])
else:
    print("  [FAIL] Key storage failed. Stored value does not match.")
    sys.exit(1)
