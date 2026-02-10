# ============================================================================
# HybridRAG v3 - Set Mode to Online (scripts/_set_online.py)
# ============================================================================
#
# WHAT THIS FILE DOES:
#   Opens the config file (config/default_config.yaml), changes the
#   "mode" setting from "offline" to "online", and saves it.
#
#   After this runs, the next time you use rag-query, HybridRAG will
#   send your question to the company GPT API instead of local Ollama.
#
# WHO CALLS THIS:
#   api_mode_commands.ps1 -> rag-mode-online function
#   You never need to run this file directly.
#
# WHAT IT CHANGES:
#   config/default_config.yaml -> mode: online
#
# WHAT IT DOES NOT CHANGE:
#   HuggingFace lockdown stays active (HF_HUB_OFFLINE=1)
#   Model caches stay local
#   All security layers stay active
#
# INTERNET ACCESS: NONE. Only modifies a local file.
# ============================================================================

# yaml is a library that reads and writes YAML files (the .yaml config format).
# YAML is a human-readable format for storing settings, like:
#   mode: offline
#   embedding:
#     batch_size: 16
import yaml

# Step 1: Open the config file and read its contents into a Python dictionary
with open('config/default_config.yaml', 'r') as f:
    cfg = yaml.safe_load(f)

# Step 2: Change the mode setting to "online"
# This is like editing the file by hand and changing "mode: offline"
# to "mode: online", but done programmatically so there are no typos.
cfg['mode'] = 'online'

# Step 3: Write the updated config back to the file
# default_flow_style=False keeps the YAML in the readable multi-line format
# instead of compressing it into one long line.
with open('config/default_config.yaml', 'w') as f:
    yaml.dump(cfg, f, default_flow_style=False)

# Step 4: Confirm the change
print('Mode set to: online')
