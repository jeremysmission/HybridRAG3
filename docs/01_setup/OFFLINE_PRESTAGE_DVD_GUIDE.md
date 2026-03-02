# Offline Prestage DVD Guide

Last Updated: 2026-03-02

Use this guide when the target machine cannot download anything and you need
to move the HybridRAG3 offline bundle using one or more optical discs.

---

## Objective

Build once on a connected machine, split/copy across discs as needed, pre-stage
all files into one local folder on the target machine, then run the installer
from that pre-staged folder.

---

## Capacity Reality Check

- DVD single-layer (DVD-R/DVD+R): about 4.7 GB (about 4.38 GiB usable)
- DVD dual-layer (DVD-R DL/DVD+R DL): about 8.5 GB (about 7.92 GiB usable)
- CD-R: about 700 MB (not practical for full bundles)

If your full offline bundle is larger than one disc, use multiple discs and
pre-stage to local disk before running install.

---

## Required Folder Layout

The installer expects a single root folder that contains:

- `HybridRAG3\`
- `scripts\`
- `INSTALL.bat`
- `MANIFEST.txt`
- `MANIFEST_SHA256.txt`
- optional: `wheels\`
- optional: `cache\`
- optional: `installers\`

Order of copy does not matter. Final folder structure does matter.

---

## Workflow A (Recommended): Prestage Then Install

1. On connected build machine, create bundle:

```powershell
cd "D:\HybridRAG3"
powershell -ExecutionPolicy Bypass -File .\tools\build_usb_deploy_bundle.ps1 -DownloadWheels -IncludeOllamaModels
```

2. Copy the bundle to one or more discs.
3. On target machine, create a local staging folder, example:
   `D:\HybridRAG3_PRESTAGE`
4. Copy all disc contents into the same staging folder so one complete layout
   exists.
5. Run:

```cmd
D:\HybridRAG3_PRESTAGE\INSTALL.bat
```

The installer script verifies `MANIFEST_SHA256.txt` before install. If any file
is missing or corrupted, install stops with a clear error.

---

## Workflow B: Run Installer Script Directly with Explicit Bundle Root

If you launch PowerShell manually, you can point to the pre-staged root:

```powershell
powershell -ExecutionPolicy Bypass -File D:\HybridRAG3_PRESTAGE\scripts\usb_install_offline.ps1 -BundleRoot D:\HybridRAG3_PRESTAGE
```

Use `-SkipHashCheck` only for troubleshooting. Do not use it for production
offline installs.

---

## Size Planning Tips

- Minimal footprint: source + wheels + required embed model only
- Larger footprint: add optional LLM models in `cache\ollama_models`
- Full approved model stack is ~26 GB, usually multi-disc unless USB/SSD is used

---

## Security and Source Integrity

- Acquire installers/models/wheels from official sources only
- Keep the generated `MANIFEST_SHA256.txt` with the bundle
- Preserve the manifest unchanged across all discs
- Verify hashes on target machine before install (now default behavior)

