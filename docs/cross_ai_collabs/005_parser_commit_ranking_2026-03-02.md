# Parser/Indexer Commit Ranking and Technique Baseline
## Date: 2026-03-02
## Scope
HybridRAG3 parser/indexer reliability commits, ranked against current OCR/parsing best practices.

---

## External Best-Practice Baseline (Primary Sources)
1. Use native text extraction first for digitally born PDFs; OCR only when needed.
2. Use OCR mode controls that distinguish skip/force/redo behavior for mixed documents.
3. Apply image preprocessing for OCR quality (deskew, binarization tuning, denoise, erosion/dilation as needed).
4. Use file signature/MIME detection in addition to file extension when routing parsers.
5. Track explicit skip reasons and per-format failure histograms for operations.

Notes:
- Items 1-3 are directly supported by pypdf/Tesseract/OCRmyPDF docs.
- Item 4 is directly supported by Tika/libmagic docs.
- Item 5 is an engineering inference from operational reliability practice.

---

## Ranked Commits (Best -> Worst)

### 1) `3f84ef7` -- Add CI guard tests and harden indexer registry fallback
Why ranked #1:
- Highest regression-prevention value per LOC.
- Adds hard guardrails for config/registry drift and parser dependency presence.
- Converts silent future breakage into immediate CI failure.

Decision: `KEEP` (gold standard for this class of failures)

### 2) `fb54cb5` -- Fix parser coverage gap: expand allowlist + parser deps
Why ranked #2:
- Fixes the root production-impact issue (formats filtered before parser).
- Restores intended parser surface area and dependency coverage.

Decision: `KEEP`

### 3) `262ece1` -- Harden parser/indexer guardrails + readiness docs
Why ranked #3:
- Improves operator readiness and practical reliability workflows.
- Adds concrete operational docs and safer regression runner.

Decision: `KEEP`, with cleanup (see Drops below)

### 4) `0c962b9` -- Expanded parsing to 63 extensions
Why ranked #4:
- Massive capability gain and strong stress-test intent.
- But integration debt remained (allowlist/deps mismatch surfaced later).

Decision: `KEEP`, but treat as "capability added before full production integration."

### 5) `71a0790` -- Indexer refactor + smoke test
Why ranked #5:
- Good architecture and testability improvement.
- Lower direct impact than guardrails/coverage fixes.

Decision: `KEEP`

### 6) `e8a236b` -- HTML/HTTP parser expansion
Why ranked #6:
- Useful, but narrower blast radius and lower impact on skip-rate problem.

Decision: `KEEP`

### 7) `354813b` -- Large suite/test restructuring + binary detection fixes
Why ranked #7:
- Valuable but broad and mixed scope; difficult to isolate reliability impact.
- High change volume increases review complexity.

Decision: `KEEP`, but prefer smaller scoped follow-up commits.

---

## Dropped "Worst" Patterns

### Dropped now
1. Root-level temporary scripts committed as product artifacts:
   - `.tmp_download_online_bank.ps1` (deleted)
   - `.tmp_parser_compare.py` (deleted)

Reason:
- These are session scratch tools, not stable product interfaces.
- They increase repo noise and complicate long-term maintenance.

### Already dropped in current indexer path
1. Generic empty skip reason with no parser context.
2. Unrestricted plaintext fallback attempts on binary-like formats.

Reason:
- Both patterns hide root cause and inflate ambiguous skip rates.

---

## Next Technique Upgrades (Based on Baseline)
1. Add MIME/signature sniffing pre-routing (`libmagic`/Tika-style approach) to catch extension spoofing.
2. Add page-level OCR telemetry (timeout/megapixel/downsample counters) similar to OCRmyPDF mode observability.
3. Add OCR confidence-based retry/preprocess policy for image-heavy corpora.

