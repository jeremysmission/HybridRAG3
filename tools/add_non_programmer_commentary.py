from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

TARGET_GLOBS = ["*.py", "*.ps1", "*.bat", "*.psd1"]
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".mypy_cache", ".pytest_cache"}
MARKER = "NON-PROGRAMMER GUIDE"


def _should_skip(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def _keywords(name: str) -> str:
    words = re.split(r"[_\-.]+", name.lower())
    words = [w for w in words if w and w not in {"test", "run", "tool", "script", "utils", "helper"}]
    return " ".join(words[:6]) if words else "workflow"


def _purpose(path: Path) -> str:
    rel = path.relative_to(ROOT)
    folder = rel.parts[0].lower() if rel.parts else "project"
    key = _keywords(path.stem)
    if folder == "src":
        return f"Implements the {key} part of the application runtime."
    if folder == "tests":
        return f"Verifies behavior for the {key} area and protects against regressions."
    if folder == "tools":
        return f"Automates the {key} operational workflow for developers or operators."
    if folder == "scripts":
        return f"Provides a command-line shortcut for the {key} operation."
    return f"Supports the {key} workflow in this repository."


def _py_header(path: Path) -> str:
    return "\n".join(
        [
            "# === NON-PROGRAMMER GUIDE ===",
            f"# Purpose: {_purpose(path)}",
            "# What to read first: Start at the top-level function/class definitions and follow calls downward.",
            "# Inputs: Configuration values, command arguments, or data files used by this module.",
            "# Outputs: Returned values, written files, logs, or UI updates produced by this module.",
            "# Safety notes: Update small sections at a time and run relevant tests after edits.",
            "# ============================",
            "",
        ]
    )


def _ps1_header(path: Path) -> str:
    return "\n".join(
        [
            "<#",
            "=== NON-PROGRAMMER GUIDE ===",
            f"Purpose: {_purpose(path)}",
            "How to follow: Read variables first, then each command block in order.",
            "Inputs: Environment variables, script parameters, and local files.",
            "Outputs: Console messages, changed files, or system configuration updates.",
            "Safety notes: Run in a test environment before using on production systems.",
            "=============================",
            "#>",
            "",
        ]
    )


def _bat_header(path: Path) -> str:
    lines = [
        "@REM === NON-PROGRAMMER GUIDE ===",
        f"@REM Purpose: {_purpose(path)}",
        "@REM How to follow: Read each command line in order from top to bottom.",
        "@REM Inputs: Command arguments, environment variables, and local files.",
        "@REM Outputs: Terminal messages and any files changed by called tools.",
        "@REM Safety notes: Confirm paths before running on important data.",
        "@REM ============================",
        "",
    ]
    return "\n".join(lines)


def _psd1_header(path: Path) -> str:
    return "\n".join(
        [
            "# === NON-PROGRAMMER GUIDE ===",
            f"# Purpose: {_purpose(path)}",
            "# How to follow: Each key/value pair controls script analysis or formatting behavior.",
            "# Inputs: Values defined in this settings file.",
            "# Outputs: Affects how tools validate PowerShell scripts.",
            "# ============================",
            "",
        ]
    )


def _insert_python(text: str, header: str) -> str:
    if MARKER in text:
        return text
    bom = ""
    if text.startswith("\ufeff"):
        bom = "\ufeff"
        text = text[1:]
    lines = text.splitlines(keepends=True)
    idx = 0
    if lines and lines[0].startswith("#!"):
        idx = 1
    if len(lines) > idx and re.match(r"#.*coding[:=]", lines[idx]):
        idx += 1
    prefix = "".join(lines[:idx])
    suffix = "".join(lines[idx:])
    return bom + prefix + header + suffix


def _insert_general(text: str, header: str) -> str:
    if MARKER in text:
        return text
    bom = ""
    if text.startswith("\ufeff"):
        bom = "\ufeff"
        text = text[1:]
    return bom + header + text


def _iter_files() -> list[Path]:
    files: list[Path] = []
    for pattern in TARGET_GLOBS:
        for path in ROOT.rglob(pattern):
            if _should_skip(path):
                continue
            if path.is_file():
                files.append(path)
    # deterministic order for repeatability
    return sorted(set(files))


def main() -> int:
    changed = 0
    scanned = 0
    for path in _iter_files():
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="ignore")
        ext = path.suffix.lower()
        if ext == ".py":
            new_text = _insert_python(text, _py_header(path))
        elif ext == ".ps1":
            new_text = _insert_general(text, _ps1_header(path))
        elif ext == ".bat":
            new_text = _insert_general(text, _bat_header(path))
        elif ext == ".psd1":
            new_text = _insert_general(text, _psd1_header(path))
        else:
            continue
        if new_text != text:
            path.write_text(new_text, encoding="utf-8", newline="\n")
            changed += 1
    print(f"Scanned {scanned} files; updated {changed} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
