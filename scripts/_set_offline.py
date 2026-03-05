# === NON-PROGRAMMER GUIDE ===
# Purpose: Provides a command-line shortcut for the set offline operation.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ===================================================================
# WHAT: Switch HybridRAG to offline mode (local Ollama)
# WHY:  When you want queries answered by a local AI model running on
#       your own hardware -- no internet, no API costs, full privacy
# HOW:  Opens config/default_config.yaml, sets mode: offline, saves it
# USAGE: Usually called by api_mode_commands.ps1 -> rag-mode-offline.
#        Also runnable directly: python scripts/_set_offline.py
# ===================================================================
#
# PORTABILITY:
#   Uses HYBRIDRAG_PROJECT_ROOT env var to find config on any machine.
#   Falls back to current directory if the env var is not set.
#
# INTERNET ACCESS: NONE. Only modifies a local file.
# ===================================================================

from _config_io import load_default_config, save_default_config_atomic


# Step 1: Read the current config
cfg = load_default_config()

# Step 2: Change mode to offline
cfg['mode'] = 'offline'

# Step 3: Write back (separate from read -- never read+write same file
# in one expression)
save_default_config_atomic(cfg)

# Step 4: Confirm
print('Mode set to: offline')
