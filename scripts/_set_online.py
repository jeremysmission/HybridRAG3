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

# os gives us access to environment variables and path building.
# yaml reads and writes YAML files (the .yaml config format).
import os
import yaml


def _config_path():
    """Build the full path to default_config.yaml using the project root.

    WHY THIS EXISTS:
      If PowerShell's working directory is not the repo root (for example,
      if you cd somewhere else before running a script), a bare relative
      path like 'config/default_config.yaml' would fail with FileNotFoundError.
      By reading HYBRIDRAG_PROJECT_ROOT (set by start_hybridrag.ps1), we
      always find the config regardless of the current directory.
    """
    root = os.environ.get('HYBRIDRAG_PROJECT_ROOT', '.')
    return os.path.join(root, 'config', 'default_config.yaml')


def _write_yaml_atomic(path, data):
    """Write YAML via temp file + replace to avoid partial truncation."""
    tmp = path + ".tmp"
    with open(tmp, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    os.replace(tmp, path)


# Step 1: Open the config file and read its contents into a Python dictionary.
# _config_path() builds the full portable path instead of a bare relative one.
cfg_file = _config_path()
with open(cfg_file, 'r') as f:
    cfg = yaml.safe_load(f)

# Step 2: Change the mode setting to "online".
# This is like editing the file by hand and changing "mode: offline"
# to "mode: online", but done programmatically so there are no typos.
cfg['mode'] = 'online'

# Step 3: Write the updated config back to the file.
# IMPORTANT: We read FIRST (above), then write SECOND (here) -- never
# read and write the same file in a single expression.
# default_flow_style=False keeps the YAML in the readable multi-line format
# instead of compressing it into one long line.
_write_yaml_atomic(cfg_file, cfg)

# Step 4: Confirm the change
print('Mode set to: online')
