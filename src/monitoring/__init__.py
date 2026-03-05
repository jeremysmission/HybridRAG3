# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the init part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ===================================================================
# WHAT: Monitoring package -- structured logging + indexing run tracker
# WHY:  Week-long indexing runs and daily queries need auditable records
#       so you can prove what happened, when, and at what cost
# HOW:  Two modules:
#         logger.py      -- Structured (JSON) logging to daily log files
#         run_tracker.py -- Per-run SQLite tracking with ETA and progress
# USAGE: from src.monitoring.logger import get_app_logger
#        from src.monitoring.run_tracker import RunTracker
# ===================================================================
