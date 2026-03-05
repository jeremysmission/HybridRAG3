# === NON-PROGRAMMER GUIDE ===
# Purpose: Provides a command-line shortcut for the profile status operation.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ===================================================================
# WHAT: Show the current hardware performance profile settings
# WHY:  Users need to verify which profile is active (laptop_safe,
#       desktop_power, or server_max) because batch size, chunk size,
#       and search depth all affect RAM usage and indexing speed
# HOW:  Reads config/default_config.yaml and infers the profile from
#       the embedding batch_size setting (16=laptop, 64=desktop, 128=server)
# USAGE: Called by api_mode_commands.ps1 -> rag-profile status.
#        Not run directly by users.
# ===================================================================
#
# WHY PROFILES MATTER:
#   Higher batch sizes mean the embedder processes more chunks at once
#   during indexing, which is faster but uses more RAM. On a laptop
#   with 16GB, a batch of 128 could cause the system to slow down or
#   crash from running out of memory. On a 64GB machine, batch 128
#   is comfortable and indexes 8x faster than batch 16.
#
# PORTABILITY:
#   Uses HYBRIDRAG_PROJECT_ROOT env var to find config on any machine.
#   Falls back to current directory if the env var is not set.
#
# INTERNET ACCESS: NONE. Only reads a local file.
# ===================================================================

from _config_io import load_default_config


# Read the config file using the shared portable resolver
cfg = load_default_config()

# Extract the key settings that define a profile.
# .get() with a default of '?' means "if the setting doesn't exist,
# show a question mark instead of crashing"
eb = cfg.get('embedding', {}).get('batch_size', '?')    # Embedding batch size
ck = cfg.get('chunking', {}).get('chunk_size', '?')     # Chunk size in chars
tk = cfg.get('retrieval', {}).get('top_k', '?')         # How many results to return

# Print the current values
print('  Embedding batch_size: ' + str(eb))
print('  Chunk chunk_size:     ' + str(ck))
print('  Search top_k:         ' + str(tk))

# Infer which profile is active based on the batch size.
# If someone manually edited the config to a non-standard batch size,
# we just call it "custom".
if eb == 16:
    print('  Profile:              laptop_safe')
elif eb == 64:
    print('  Profile:              desktop_power')
elif eb == 128:
    print('  Profile:              server_max')
else:
    print('  Profile:              custom')
