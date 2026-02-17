#!/usr/bin/env python3
"""
Run hallucination guard self-tests or BIT diagnostics.

Usage:
    python -m hallucination_guard          # Full self-test (needs NLI model)
    python -m hallucination_guard --bit    # Quick BIT checks only (< 50ms)
"""
import sys

if "--bit" in sys.argv:
    from .startup_bit import run_bit
    passed, total, details = run_bit(verbose=True)
    sys.exit(0 if passed == total else 1)
else:
    from .self_test import run_self_test
    passed = run_self_test()
    sys.exit(0 if passed else 1)
