# OCR Diversion Process Flow Cheat Sheet
## Date: 2026-03-02
## Purpose
Run high-volume indexing reliably when many files are scan/image-heavy and OCR results vary.

---

## Core Idea
- Main source pass should stay clean and fast.
- OCR-dependent files are routed to an `_ocr_diversions` queue for triage.
- Recovered files are returned and re-indexed.

---

## Flow (Operator View)
1. Prepare source set (copied program data, not original live data).
2. Run indexing on source.
3. OCR-dependent no-text files are diverted to `_ocr_diversions/` with reason sidecars.
4. Triage diversion queue:
   - keep and OCR-fix valuable files
   - archive/delete worthless files
5. Move fixed files back to source (same relative path preferred).
6. Re-run indexing.

---

## Copy vs Move Policy
- `Copy`:
  - Original stays in source.
  - Safer for review and rollback.
  - Risk: duplicated files if you also keep diverted copy.
- `Move`:
  - File leaves source during triage.
  - Cleaner main indexing set.
  - Must restore file to source after OCR fix.

Recommended when source is already a copied dataset:
- Use `Move` for cleaner operations.

---

## Path and Naming Behavior
- Diversion queue preserves relative path and filename.
- Example:
  - Source: `D:\RAG Source Data\A\B\scan001.pdf`
  - Diversion: `D:\RAG Source Data\_ocr_diversions\A\B\scan001.pdf`
- Reason sidecar:
  - `scan001.pdf.reason.txt`
  - Contains source path and skip reason.

---

## Hash/Reindex Behavior
- Hash key is `size:mtime_ns`.
- If file returns to source unchanged and already indexed:
  - hash match -> skipped as unchanged.
- If OCR/fix changes size or modified time:
  - hash mismatch -> old chunks deleted -> file re-indexed.

---

## Daily Runbook
1. Run main indexing.
2. Review:
   - `skip_reason_counts`
   - `skip_extension_counts`
3. Open `_ocr_diversions`.
4. Prioritize by value:
   - contracts/specs/compliance first
   - low-value screenshots last
5. OCR-fix selected files.
6. Move fixed files back to source.
7. Re-run indexing.
8. Archive/delete unresolved junk after retention window.

---

## Quick Commands
Route OCR-dependent files into queue:

```powershell
python tools/route_ocr_dependent_files.py `
  --source "D:\RAG Source Data" `
  --queue-output "D:\RAG Source Data\_ocr_diversions" `
  --mode move `
  --pdf-min-native-chars 40 `
  --pdf-probe-pages 3
```

OCR tuning env vars:

```powershell
$env:HYBRIDRAG_OCR_DPI="300"
$env:HYBRIDRAG_OCR_TIMEOUT_S="45"
$env:HYBRIDRAG_OCR_MAX_PAGES="20"
$env:HYBRIDRAG_OCR_LANG="eng"
```

---

## Decision Rules
- Keep and fix when:
  - document has business/technical value
  - partial text is recoverable with OCR/preprocessing
- Archive/delete when:
  - blank images
  - decorative graphics with no text
  - corrupted duplicates with no recovery value

---

## Common Mistakes
- Re-indexing `_ocr_diversions` recursively by accident.
- Moving files back to wrong folder, breaking source traceability.
- Deleting diverted files before writing a retention/approval policy.

---

## Minimum Governance
- Keep diversion manifest + reason files.
- Record retention rule (e.g., 30 days before purge).
- Track weekly:
  - diverted count
  - recovered count
  - deleted count
  - top skip reasons
