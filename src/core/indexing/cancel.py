# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the cancel part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# IndexCancelled -- dedicated cancellation signal for the indexing pipeline.
#
# Inherits from BaseException (not Exception) so that the per-file
# "except Exception" error handler in Indexer.index_folder cannot
# accidentally swallow it.  This makes cancel a clean control-flow
# exit, not an error.
# ============================================================================


class IndexCancelled(BaseException):
    """Raised when the user cancels an indexing run via the stop flag."""
    pass
