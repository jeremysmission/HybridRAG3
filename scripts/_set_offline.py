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
# USAGE: Called by api_mode_commands.ps1 -> rag-mode-offline.
#        Not run directly by users.
# ===================================================================
#
# PORTABILITY:
#   Uses HYBRIDRAG_PROJECT_ROOT env var to find config on any machine.
#   Falls back to current directory if the env var is not set.
#
# INTERNET ACCESS: NONE. Only modifies a local file.
# ===================================================================

import os
import yaml


def _config_path():
    """Build the full path to default_config.yaml using the project root.

    WHY THIS EXISTS:
      If PowerShell's working directory is not the repo root, a bare
      relative path like 'config/default_config.yaml' would fail.
      HYBRIDRAG_PROJECT_ROOT (set by start_hybridrag.ps1) ensures we
      always find the config regardless of the current directory.
    """
    root = os.environ.get('HYBRIDRAG_PROJECT_ROOT', '.')
    return os.path.join(root, 'config', 'default_config.yaml')


# Step 1: Read the current config
cfg_file = _config_path()
with open(cfg_file, 'r') as f:
    cfg = yaml.safe_load(f)

# Step 2: Change mode to offline
cfg['mode'] = 'offline'

# Step 3: Write back (separate from read -- never read+write same file
# in one expression)
with open(cfg_file, 'w') as f:
    yaml.dump(cfg, f, default_flow_style=False)

# Step 4: Confirm
print('Mode set to: offline')
