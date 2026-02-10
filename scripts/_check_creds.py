# ============================================================================
# HybridRAG v3 - Check Credential Status (scripts/_check_creds.py)
# ============================================================================
#
# WHAT THIS FILE DOES:
#   Checks whether an API key and endpoint URL are stored in Windows
#   Credential Manager. Prints the results so the PowerShell command
#   rag-mode-online can decide whether to proceed or show an error.
#
# WHO CALLS THIS:
#   api_mode_commands.ps1 -> rag-mode-online function
#   You never need to run this file directly.
#
# WHAT IT PRINTS:
#   KEY:True        (or KEY:False if no API key is stored)
#   ENDPOINT:True   (or ENDPOINT:False if no endpoint is stored)
#   KEY_SRC:keyring (or KEY_SRC:env_var or KEY_SRC:none)
#
# INTERNET ACCESS: NONE. Only reads from local Windows Credential Manager.
# ============================================================================

import sys
import os

# Add the project root folder to Python's search path so we can import
# our own modules (like src.security.credentials). The project root is
# stored in an environment variable by start_hybridrag.ps1.
sys.path.insert(0, os.environ.get('HYBRIDRAG_PROJECT_ROOT', '.'))

# Import our credential manager module
from src.security.credentials import credential_status

# Call the function that checks what credentials are stored.
# It returns a dictionary (a collection of named values) like:
#   {
#       'api_key_set': True,
#       'api_endpoint_set': False,
#       'api_key_source': 'keyring',
#       ...
#   }
s = credential_status()

# Print the results in a simple format that PowerShell can parse.
# PowerShell will look for "KEY:True" or "KEY:False" in this output
# to decide what to do next.
print('KEY:' + str(s['api_key_set']))
print('ENDPOINT:' + str(s['api_endpoint_set']))
print('KEY_SRC:' + str(s['api_key_source']))
