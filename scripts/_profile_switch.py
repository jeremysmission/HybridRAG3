# === NON-PROGRAMMER GUIDE ===
# Purpose: Provides a command-line shortcut for the profile switch operation.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ===================================================================
# WHAT: Switch ALL hardware-dependent settings to match a predefined
#       performance profile (laptop / desktop / server)
# WHY:  Different machines have wildly different RAM and GPU capacity.
#       The same settings that work on a 64GB desktop would crash a
#       16GB laptop. Profiles bundle all hardware-sensitive settings
#       so one command adapts the entire system to the machine.
# HOW:  Deep-merges profile-specific settings (embedding model, batch
#       size, LLM model, context window, top_k) into the existing
#       config YAML, detects embedding model changes and warns about
#       required re-indexing
# USAGE: rag-profile laptop_safe|desktop_power|server_max
#        python scripts/_profile_switch.py <profile_name>
# ===================================================================
#
# PROFILE DETAILS:
#
#   laptop_safe (8-16GB RAM, no GPU):
#     - Embedder: nomic-embed-text (768d, Ollama)
#     - LLM: phi4-mini (3.8B, 8K context)
#     - batch_size=16, top_k=5, block=200K
#
#   desktop_power (64GB RAM, 12GB VRAM):
#     - Embedder: nomic-embed-text (768d, CUDA)
#     - LLM: phi4:14b-q4_K_M (14B, 4K context)
#     - batch_size=64, top_k=5, block=500K
#
#   server_max (64GB+ RAM, 24GB+ VRAM):
#     - Embedder: nomic-embed-text (768d, Ollama)
#     - LLM: phi4:14b-q4_K_M (14B, 4K context)
#     - batch_size=128, top_k=10, block=1M
#
# IMPORTANT:
#   If the embedding model changes, ALL documents must be RE-INDEXED.
#   Existing 384-dim vectors are incompatible with a 768-dim model.
#   This script detects model changes and prints a clear warning.
#
# INTERNET ACCESS: NONE. Only modifies a local file.
# ===================================================================

import os
import sys

sys.path.insert(0, os.environ.get("HYBRIDRAG_PROJECT_ROOT", "."))
sys.path.insert(0, os.path.join(
    os.environ.get("HYBRIDRAG_PROJECT_ROOT", "."), "scripts"
))
from _config_io import load_default_config, save_default_config_atomic


# -- Define the three profiles --
# Each profile is a dictionary of settings that get deep-merged into
# default_config.yaml. Keys match the YAML section names.
profiles = {
    'laptop_safe': {
        'embedding': {
            'model_name': 'nomic-embed-text',
            'dimension': 768,
            'batch_size': 16,
            'device': 'cpu',
        },
        'ollama': {
            'model': 'phi4-mini',
            'context_window': 4096,
        },
        'chunking': {
            'chunk_size': 1200,
            'overlap': 200,
        },
        'retrieval': {'top_k': 5, 'reranker_top_n': 20},
        'indexing': {
            'block_chars': 200000,
            'max_chars_per_file': 2000000,
        },
        'performance': {
            'max_concurrent_files': 1,
            'gc_between_files': True,
            'gc_between_blocks': True,
        },
    },
    'desktop_power': {
        'embedding': {
            'model_name': 'nomic-embed-text',
            'dimension': 768,
            'batch_size': 64,
            'device': 'cuda',
        },
        'ollama': {
            'model': 'phi4:14b-q4_K_M',
            'context_window': 4096,
        },
        'chunking': {
            'chunk_size': 1200,
            'overlap': 200,
        },
        'retrieval': {'top_k': 5, 'reranker_top_n': 20},
        'indexing': {
            'block_chars': 500000,
            'max_chars_per_file': 5000000,
        },
        'performance': {
            'max_concurrent_files': 2,
            'gc_between_files': False,
            'gc_between_blocks': False,
        },
    },
    'server_max': {
        'embedding': {
            'model_name': 'nomic-embed-text',
            'dimension': 768,
            'batch_size': 128,
            'device': 'cuda',
        },
        'ollama': {
            'model': 'phi4:14b-q4_K_M',
            'context_window': 4096,
        },
        'chunking': {
            'chunk_size': 1200,
            'overlap': 200,
        },
        'retrieval': {'top_k': 10, 'reranker_top_n': 30},
        'indexing': {
            'block_chars': 1000000,
            'max_chars_per_file': 10000000,
        },
        'performance': {
            'max_concurrent_files': 4,
            'gc_between_files': False,
            'gc_between_blocks': False,
        },
    },
}


# -- Read the command-line argument --
if len(sys.argv) < 2 or sys.argv[1] not in profiles:
    print('Usage: python _profile_switch.py [laptop_safe|desktop_power|server_max]')
    sys.exit(1)

profile = sys.argv[1]
settings = profiles[profile]

# -- Read the current config --
cfg = load_default_config()

# -- Detect embedding model change (requires re-index) --
old_model = cfg.get('embedding', {}).get('model_name', '')
new_model = settings.get('embedding', {}).get('model_name', '')
model_changed = old_model and new_model and old_model != new_model

# -- Apply the profile settings (deep merge) --
# Only changes the specific keys in each section, leaving all other
# settings untouched.
for section_name, values in settings.items():
    if section_name not in cfg:
        cfg[section_name] = {}
    for key, val in values.items():
        cfg[section_name][key] = val

# -- Save the updated config --
save_default_config_atomic(cfg)

# -- Print confirmation --
desc = {
    'laptop_safe': (
        'Laptop (8-16GB RAM, CPU)\n'
        '  Embedder: nomic-embed-text (768d, Ollama)\n'
        '  Default LLM: phi4-mini (3.8B, 8K ctx)'
    ),
    'desktop_power': (
        'Desktop (64GB RAM, 12GB VRAM)\n'
        '  Embedder: nomic-embed-text (768d, cuda)\n'
        '  Default LLM: phi4:14b-q4_K_M (14B, 4K ctx)'
    ),
    'server_max': (
        'Server (64GB+ RAM, 24GB+ VRAM)\n'
        '  Embedder: nomic-embed-text (768d, Ollama)\n'
        '  Default LLM: phi4:14b-q4_K_M (14B, 4K ctx)'
    ),
}
print('[OK]  Profile applied: ' + profile)
print('  ' + desc[profile])

# -- Show ranked model table per use case --
try:
    from _model_meta import get_profile_ranking_table, USE_CASES

    table = get_profile_ranking_table(profile)
    if table:
        print('')
        print('  Best model per use case on this hardware:')
        print('  %-22s %-22s %s' % ('Use Case', '#1 (default)', '#2 (fallback)'))
        print('  %-22s %-22s %s' % ('-' * 22, '-' * 22, '-' * 22))

        display_order = ['sw', 'eng', 'sys', 'draft', 'log', 'pm', 'fe', 'cyber', 'gen']
        for uc_key in display_order:
            if uc_key not in table:
                continue
            ranked = table[uc_key]
            label = USE_CASES[uc_key]['label']
            col1 = ranked[0]['model'] if len(ranked) > 0 else '---'
            col2 = ranked[1]['model'] if len(ranked) > 1 else '---'
            print('  %-22s %-22s %s' % (label, col1, col2))
except Exception:
    pass  # Model ranking is informational; never block profile switch

# -- Warn about re-index if embedding model changed --
if model_changed:
    print('')
    print('[WARN] Embedding model changed: %s -> %s' % (old_model, new_model))
    print('       Existing vectors are INCOMPATIBLE with the new model.')
    print('       You MUST re-index all documents before querying.')
    print('       Run: rag-index "D:\\RAG Source Data"')
