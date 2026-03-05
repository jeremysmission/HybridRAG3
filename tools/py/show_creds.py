# === NON-PROGRAMMER GUIDE ===
# Purpose: Automates the show creds operational workflow for developers or operators.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# show_creds.py -- Display all stored credentials with masking
# ============================================================================
# Shows all four credential values from keyring with appropriate masking:
#   - API Key: masked (first 4 + last 4 chars only)
#   - Endpoint: shown in full
#   - Deployment: shown in full
#   - API Version: shown in full
#
# INTERNET ACCESS: NONE -- only reads from local keyring
# ============================================================================

import keyring

items = {
    "azure_api_key": "API Key",
    "azure_endpoint": "Endpoint",
    "azure_deployment": "Deployment",
    "azure_api_version": "API Version",
}

for key_name, display_name in items.items():
    val = keyring.get_password("hybridrag", key_name)
    if val:
        if "key" in key_name.lower():
            display = val[:4] + "..." + val[-4:] + f"  (length: {len(val)})"
        else:
            display = val
        print(f"  {display_name}: {display}")
    else:
        print(f"  {display_name}: NOT SET")
