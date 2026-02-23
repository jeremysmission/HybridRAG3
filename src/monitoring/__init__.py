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
