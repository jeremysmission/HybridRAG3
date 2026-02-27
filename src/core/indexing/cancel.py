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
