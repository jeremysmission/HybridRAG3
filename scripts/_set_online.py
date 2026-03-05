# === NON-PROGRAMMER GUIDE ===
# Purpose: Provides a command-line shortcut for the set online operation.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ===================================================================
# WHAT: Switch HybridRAG to online mode (cloud API)
# WHY:  When you want queries answered by a cloud AI model (GPT, etc.)
#       for faster, more powerful responses at a per-query cost
# HOW:  Opens config/default_config.yaml, sets mode: online, saves it.
#       Security layers (HF lockdown, model caches) remain unchanged.
# USAGE: Called by api_mode_commands.ps1 -> rag-mode-online.
#        Not run directly by users.
# ===================================================================
#
# WHAT IT CHANGES:
#   config/default_config.yaml -> mode: online
#
# WHAT IT DOES NOT CHANGE:
#   HuggingFace lockdown stays active (HF_HUB_OFFLINE=1)
#   Model caches stay local
#   All security layers stay active
#
# PORTABILITY:
#   Uses HYBRIDRAG_PROJECT_ROOT env var to find config on any machine.
#   Falls back to current directory if the env var is not set.
#
# INTERNET ACCESS: NONE. Only modifies a local file.
# ===================================================================

# Shared config I/O helper provides portable path resolution and atomic write.
import os
from _config_io import load_default_config, save_default_config_atomic


def _config_path():
    """Compatibility shim for legacy validation tests."""
    root = os.environ.get('HYBRIDRAG_PROJECT_ROOT', '.')
    return os.path.join(root, 'config', 'default_config.yaml')


# Step 1: Open the config file and read its contents into a Python dictionary.
cfg = load_default_config()

# Step 2: Change the mode setting to "online".
# This is like editing the file by hand and changing "mode: offline"
# to "mode: online", but done programmatically so there are no typos.
cfg['mode'] = 'online'

# Step 3: Write the updated config back to the file.
# IMPORTANT: We read FIRST (above), then write SECOND (here) -- never
# read and write the same file in a single expression.
# default_flow_style=False keeps the YAML in the readable multi-line format
# instead of compressing it into one long line.
save_default_config_atomic(cfg)

# Step 4: Confirm the change
print('Mode set to: online')
