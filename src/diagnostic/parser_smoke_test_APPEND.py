# ===================================================================
# WHAT: Parser library import smoke test -- verifies every document
#       parser dependency is actually installed
# WHY:  The #1 portability problem: requirements.txt lists a package
#       (like python-docx) but it was not installed in the venv. This
#       test catches it before a real file triggers a confusing error.
# HOW:  Tries to __import__ each parser library (PDF, Word, Excel,
#       PowerPoint, etc.) and reports which are missing with the exact
#       pip install command to fix them
# USAGE: This is an APPEND file -- its function should be copied into
#        component_tests.py. It is not a standalone runnable script.
# ===================================================================


def test_parser_smoke() -> TestResult:
    """
    Smoke test: Can each critical parser import its library?

    This catches the #1 portability problem: requirements.txt lists a
    package but it wasn't installed (or was installed in wrong venv).

    We test the IMPORT, not actual file parsing, because we don't need
    a real file to verify the library is installed. This makes the test
    fast and dependency-free.
    """
    # Each entry: (name, import_statement, pip_package)
    # import_statement is what the parser actually calls internally
    # pip_package is what you'd run "pip install X" to fix it
    checks = [
        ("PDF (pdfplumber)",    "pdfplumber",            "pdfplumber"),
        ("PDF (pypdf)",         "pypdf",                 "pypdf"),
        ("DOCX (python-docx)",  "docx",                  "python-docx"),
        ("PPTX (python-pptx)",  "pptx",                  "python-pptx"),
        ("XLSX (openpyxl)",     "openpyxl",              "openpyxl"),
        ("HTTP (httpx)",        "httpx",                  "httpx"),
        ("ML (transformers)",   "transformers",           "transformers"),
        ("ML (sentence_transformers)", "sentence_transformers", "sentence-transformers"),
        ("Config (yaml)",       "yaml",                   "PyYAML"),
        ("Logging (structlog)", "structlog",              "structlog"),
        ("Images (PIL)",        "PIL",                    "pillow"),
    ]

    passed = []
    failed = []
    details = {}

    for name, module, pip_name in checks:
        try:
            __import__(module)
            passed.append(name)
            details[name] = "OK"
        except ImportError as e:
            failed.append(name)
            details[name] = f"MISSING -- fix: pip install {pip_name}"
        except Exception as e:
            failed.append(name)
            details[name] = f"ERROR: {type(e).__name__}: {e}"

    d = {
        "total": len(checks),
        "passed": len(passed),
        "failed": len(failed),
        "details": details,
    }

    if failed:
        # Build a single pip install command to fix everything
        fix_packages = []
        for name, module, pip_name in checks:
            if name in failed:
                fix_packages.append(pip_name)
        fix_cmd = "pip install " + " ".join(fix_packages)

        return TestResult(
            "parser_smoke", "Parsers", "FAIL",
            f"{len(failed)} missing: {', '.join(failed)}", d,
            fix_hint=f"Run: {fix_cmd}")

    return TestResult(
        "parser_smoke", "Parsers", "PASS",
        f"All {len(checks)} critical libraries importable", d)
