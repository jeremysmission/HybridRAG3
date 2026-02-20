#!/usr/bin/env python3
# ============================================================================
# HybridRAG v3 -- Wheels Bundle Builder (build_wheels_bundle.py)
# ============================================================================
# PURPOSE:
#   Run this on the HOME PC to download all Python dependencies as .whl
#   files for offline installation on the work laptop. This is the fallback
#   when PyPI is blocked by enterprise firewall.
#
# WHAT IT DOES:
#   1. Reads requirements.txt
#   2. Downloads all wheels for the target platform (Windows, Python 3.11)
#   3. Packages them into a wheels/ folder
#   4. Copies requirements.txt alongside for reference
#
# USAGE (on home PC):
#   python build_wheels_bundle.py
#   python build_wheels_bundle.py --platform win_amd64 --python 3.11
#
# THEN:
#   Copy the wheels/ folder into the transfer package before zipping.
#   On the work laptop: python check_dependencies.py --wheels
#
# INTERNET ACCESS: YES (downloads from PyPI)
# ============================================================================

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def log(tag: str, message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [{tag}] {message}")


def find_requirements() -> Path:
    """Find requirements.txt in project root or current directory."""
    candidates = [
        Path(__file__).resolve().parent / "requirements.txt",
        Path(__file__).resolve().parents[2] / "requirements.txt",
        Path.cwd() / "requirements.txt",
    ]
    for p in candidates:
        if p.exists():
            return p
    return Path("requirements.txt")


def main():
    parser = argparse.ArgumentParser(
        description="HybridRAG v3 -- Build Wheels Bundle for Offline Install"
    )
    parser.add_argument(
        "--requirements", type=str, default=None,
        help="Path to requirements.txt (auto-detected if not specified)",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Output directory for wheels (default: wheels/ next to this script)",
    )
    parser.add_argument(
        "--platform", type=str, default="win_amd64",
        help="Target platform (default: win_amd64)",
    )
    parser.add_argument(
        "--python", type=str, default="3.11",
        help="Target Python version (default: 3.11)",
    )
    args = parser.parse_args()

    # Resolve paths
    req_path = Path(args.requirements) if args.requirements else find_requirements()
    script_dir = Path(__file__).resolve().parent
    output_dir = Path(args.output) if args.output else script_dir / "wheels"

    log("INFO", "=" * 55)
    log("INFO", "HybridRAG v3 -- Wheels Bundle Builder")
    log("INFO", f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("INFO", "=" * 55)
    print("")

    # Check requirements.txt exists
    if not req_path.exists():
        log("FAIL", f"requirements.txt not found at: {req_path}")
        log("FAIL", "Specify path with: --requirements /path/to/requirements.txt")
        sys.exit(1)

    log("OK", f"Using requirements: {req_path}")
    log("INFO", f"Target platform: {args.platform}")
    log("INFO", f"Target Python: {args.python}")
    log("INFO", f"Output directory: {output_dir}")
    print("")

    # Clean output directory
    if output_dir.exists():
        log("INFO", "Cleaning existing wheels directory...")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Download wheels
    log("INFO", "Downloading wheels from PyPI (this may take a few minutes)...")
    print("")

    # Build pip download command
    # Use --only-binary :all: to get wheels, not source tarballs
    # Platform-specific downloads for Windows target
    python_tag = f"cp{args.python.replace('.', '')}"

    cmd = [
        sys.executable, "-m", "pip", "download",
        "-r", str(req_path),
        "-d", str(output_dir),
        "--platform", args.platform,
        "--python-version", args.python,
        "--implementation", "cp",
        "--abi", python_tag,
        "--only-binary", ":all:",
    ]

    log("INFO", f"Running: {' '.join(cmd[:6])}...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    if result.returncode != 0:
        log("WARN", "Some wheels could not be downloaded as platform-specific")
        log("INFO", "Retrying without platform constraint for pure-Python packages...")
        print("")

        # Retry without platform constraint for pure-python packages
        cmd_fallback = [
            sys.executable, "-m", "pip", "download",
            "-r", str(req_path),
            "-d", str(output_dir),
        ]
        result2 = subprocess.run(
            cmd_fallback, capture_output=True, text=True, timeout=600,
        )
        if result2.returncode != 0:
            log("FAIL", "pip download failed:")
            for line in result2.stderr.strip().split("\n")[-5:]:
                log("FAIL", f"  {line}")
            sys.exit(1)

    # Copy requirements.txt into wheels dir for reference
    shutil.copy2(req_path, output_dir.parent / "requirements.txt")

    # Count results
    whl_files = list(output_dir.glob("*.whl"))
    tar_files = list(output_dir.glob("*.tar.gz"))
    total = len(whl_files) + len(tar_files)

    print("")
    log("OK", f"Downloaded {total} packages ({len(whl_files)} wheels, "
        f"{len(tar_files)} source)")

    # Calculate total size
    total_bytes = sum(f.stat().st_size for f in output_dir.iterdir())
    total_mb = total_bytes / (1024 * 1024)
    log("INFO", f"Total size: {total_mb:.1f} MB")

    print("")
    log("INFO", "=" * 55)
    log("OK", "Wheels bundle ready!")
    log("INFO", f"  Location: {output_dir}")
    log("INFO", f"  Packages: {total}")
    log("INFO", f"  Size: {total_mb:.1f} MB")
    log("INFO", "")
    log("INFO", "Next steps:")
    log("INFO", "  1. Include wheels/ folder in the transfer zip")
    log("INFO", "  2. On work laptop: python check_dependencies.py --wheels")
    log("INFO", "=" * 55)


if __name__ == "__main__":
    main()
