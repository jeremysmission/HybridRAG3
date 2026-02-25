============================================================================
  HybridRAG3 -- USB Offline Installer Research
  Created: 2026-02-25
  Status:  RESEARCH / PROTOTYPE -- not production-ready
  Scope:   Personal repo only (excluded from Educational sync)
============================================================================

WHAT IS THIS?
  A prototype for building a USB drive that can install HybridRAG3 on any
  Windows computer WITHOUT needing an internet connection. Everything the
  user needs is pre-downloaded onto the USB.

WHY?
  Work laptops often have restricted internet, slow proxies, or no access
  to PyPI at all. A USB installer bypasses all of that. Just plug in the
  USB, double-click INSTALL.bat, and everything installs from local files.

ESTIMATED USB SIZE:
  Component                    Size        Notes
  -------------------------    ---------   --------------------------------
  HybridRAG3 source code       ~60 MB     src, tests, config, tools, docs
  Python 3.11 installer         ~25 MB     Embeddable ZIP or full .exe
  Pip wheel cache (offline)    ~300 MB     All requirements pre-downloaded
  Ollama installer             ~200 MB     Windows .exe
  nomic-embed-text model        274 MB     Required for document search
  phi4-mini model               2.5 GB     Recommended for AI answers
  -------------------------    ---------
  MINIMUM (no phi4-mini)       ~860 MB     Fits on 1 GB USB
  RECOMMENDED (with phi4-mini)  ~3.3 GB    Fits on 4 GB USB
  COMFORTABLE (with headroom)   ~4 GB      8 GB USB recommended

HOW TO BUILD THE USB:
  1. Open PowerShell on the home machine (needs internet)
  2. Run: powershell -ExecutionPolicy Bypass -File "USB Installer Research\build_usb_package.ps1"
  3. It downloads everything into a staging folder
  4. Copy that folder to your USB drive
  5. On the target machine: double-click INSTALL.bat on the USB

FILES IN THIS FOLDER:
  README.txt                  This file (you are reading it)
  build_usb_package.ps1       Builds the USB package (run on home machine)
  usb_install.ps1             The offline installer (runs from USB on target)
  usb_install.bat             Double-click launcher for usb_install.ps1

LIMITATIONS / KNOWN ISSUES:
  - The .venv is built on the target machine, so Python must match the
    wheel architecture (all wheels are win_amd64 / py3-none-any)
  - Ollama models must be manually copied to the right folder on the
    target machine (the script does this automatically)
  - If the target machine has a different Python minor version (e.g., 3.10
    vs 3.11), some binary wheels may need to be re-downloaded
  - This is a PROTOTYPE. Test thoroughly before distributing.

PERSONAL REPO ONLY:
  This folder is excluded from sync_to_educational.py via SKIP_PATTERNS.
  It will NOT appear in the Educational/Work repository.
