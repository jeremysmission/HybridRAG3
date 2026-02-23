# ===================================================================
# WHAT: Tools package -- utilities for data preparation and maintenance
# WHY:  Before HybridRAG can search documents, the documents need to
#       be transferred from network drives, verified for integrity,
#       and indexed. This package contains the tools that handle those
#       preparatory steps:
#         bulk_transfer_v2.py   -- Copy files from network drives
#         transfer_manifest.py  -- Track what was copied (audit trail)
#         transfer_staging.py   -- Prevent partial/corrupt files
#         scan_source_files.py  -- Detect corrupt files before indexing
#         run_index_once.py     -- Run the indexing pipeline
#         scheduled_scan.py     -- Weekly integrity scan via Task Scheduler
# HOW:  Each tool is a standalone script that can be run from the
#       command line or called programmatically. They share the same
#       config system (config/default_config.yaml) and logging patterns.
# ===================================================================
