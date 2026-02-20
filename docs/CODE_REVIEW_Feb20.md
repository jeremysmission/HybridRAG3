# HybridRAG v3 -- Code Review & Virtual Test Report

**Date:** 2026-02-20
**Scope:** Full codebase review -- core pipeline, parsers, hallucination guard, security, tests
**Method:** Static analysis, syntax verification, logical review, cross-module consistency checks

---

## 1. VIRTUAL TEST RESULTS

### Syntax Compilation: ALL PASS

Every `.py` file in the project compiles without syntax errors:

| Module Group | Files | Result |
|---|---|---|
| `src/core/` | 14 files | ALL OK |
| `src/parsers/` | 10 files | ALL OK |
| `src/core/hallucination_guard/` | 12 files | ALL OK |
| `tests/` | 11 files | ALL OK |

---

## 2. BUGS FOUND (Ordered by Severity)

### BUG-HIGH-001: boot.py reads wrong YAML key for Ollama host

**File:** `src/core/boot.py:273`
**Severity:** HIGH -- Ollama health check ignores user config

```python
# CURRENT (WRONG):
ollama_host = config.get("ollama", {}).get("host", "http://localhost:11434")

# CONFIG YAML uses "base_url", not "host":
# ollama:
#   base_url: http://localhost:11434
```

**Impact:** The boot Ollama health check always uses `http://localhost:11434` regardless of what the user configured in `default_config.yaml`. If someone changed `base_url` to a remote Ollama server, boot would still check localhost, report "Ollama not running," and mark offline mode as unavailable even though the real Ollama is reachable.

**Fix:**
```python
ollama_host = config.get("ollama", {}).get("base_url", "http://localhost:11434")
```

---

### BUG-HIGH-002: ThreadPoolExecutor timeout does not actually work in PDF OCR

**File:** `src/parsers/pdf_ocr_fallback.py:231-238`
**Severity:** HIGH -- Can hang the entire indexing process

```python
with ThreadPoolExecutor(max_workers=1) as ex:
    fut = ex.submit(_ocr_page_image_to_text, img, lang)
    try:
        page_text = fut.result(timeout=timeout_s)
    except FuturesTimeoutError:
        details["pages_timed_out"] += 1
        continue  # exits 'with' block -> calls shutdown(wait=True) -> BLOCKS
```

**Impact:** When the timeout fires, `continue` exits the `with` block, which calls `executor.shutdown(wait=True)`. This blocks until the Tesseract thread finishes -- so the "timeout" doesn't actually time out. If Tesseract hangs on a corrupt page, the entire process hangs indefinitely.

**Fix:** Use `shutdown(wait=False, cancel_futures=True)` (Python 3.9+) or restructure to reuse a single executor outside the loop.

---

### BUG-HIGH-003: XLSX parser leaks file handles in read_only mode

**File:** `src/parsers/office_xlsx_parser.py:36`
**Severity:** HIGH -- Causes "Too many open files" errors during batch indexing

```python
wb = openpyxl.load_workbook(str(path), data_only=True, read_only=True)
# ... processing ...
# wb.close() is NEVER called
```

**Impact:** In `read_only=True` mode, openpyxl keeps file handles open. Without explicit `wb.close()`, handles leak. Indexing 50+ Excel files can exhaust the OS file descriptor limit (`OSError: [Errno 24] Too many open files`).

**Fix:** Add `try/finally` with `wb.close()`.

---

### BUG-MED-001: Custom TimeoutError shadows Python's builtin

**File:** `src/core/exceptions.py:272`
**Severity:** MEDIUM -- Can cause confusing exception handling

```python
class TimeoutError(HybridRAGError):  # shadows builtins.TimeoutError
```

**Impact:** Code that does `except TimeoutError` may catch the wrong one depending on import order. Python's built-in `TimeoutError` (raised by `socket.timeout`, `asyncio`, etc.) is different from this custom class. If someone writes `except TimeoutError` expecting to catch network timeouts, they'll catch the wrong type.

**Fix:** Rename to `RequestTimeoutError` or `ApiTimeoutError`.

---

### BUG-MED-002: APIRouter crashes on empty choices array

**File:** `src/core/llm_router.py:619`
**Severity:** MEDIUM -- Unhandled IndexError on malformed API response

```python
answer_text = response.choices[0].message.content
```

**Impact:** If the API returns an empty `choices` list (which can happen during overload, content filtering, or malformed responses), this raises `IndexError` with no helpful message. The broad `except Exception` on line 646 catches it, but the error message won't indicate the actual cause.

**Fix:** Add a guard:
```python
if not response.choices:
    self.logger.error("api_empty_response", hint="No choices in API response")
    return None
answer_text = response.choices[0].message.content
```

---

### BUG-MED-003: Logger creates duplicate file handlers on repeated calls

**File:** `src/monitoring/logger.py:101-121`
**Severity:** MEDIUM -- Causes duplicate log entries and file handle accumulation

```python
def get_file_logger(self, name: str, log_type: str = "app") -> structlog.BoundLogger:
    # Adds a NEW FileHandler every time this is called
    handler = logging.FileHandler(log_file, encoding="utf-8")
    py_logger = logging.getLogger(name)
    py_logger.addHandler(handler)  # duplicates if called twice with same name
```

**Impact:** Every call to `get_app_logger("app")` adds another `FileHandler` to the same Python logger. After 10 calls, each log entry is written 10 times. Wastes disk I/O and makes logs hard to read.

**Fix:** Check if handler already exists before adding:
```python
py_logger = logging.getLogger(name)
if not any(isinstance(h, logging.FileHandler) for h in py_logger.handlers):
    py_logger.addHandler(handler)
```

---

### BUG-MED-004: OllamaRouter creates new TCP connection per query

**File:** `src/core/llm_router.py:170`
**Severity:** MEDIUM -- Performance degradation, unnecessary TCP overhead

```python
def query(self, prompt: str) -> Optional[LLMResponse]:
    ...
    with httpx.Client(timeout=...) as client:  # new connection every query
        resp = client.post(...)
```

**Impact:** Each query creates a new `httpx.Client`, performs TCP + TLS handshake, sends the request, then tears down the connection. For batch queries or interactive sessions, this adds unnecessary latency. `httpx.Client` is designed for connection pooling and reuse.

**Fix:** Create the client once in `__init__` and reuse it. Add a `close()` method for cleanup.

---

### BUG-MED-005: Inconsistent Tesseract environment variable names

**File:** `src/parsers/image_parser.py:86` vs `src/parsers/pdf_ocr_fallback.py:137`
**Severity:** MEDIUM -- Configuration confusion

```python
# image_parser.py:
tesseract_cmd_env = __import__("os").getenv("TESSERACT_CMD")

# pdf_ocr_fallback.py:
tess_cmd = os.environ.get("HYBRIDRAG_TESSERACT_CMD", "")
```

**Impact:** Setting `HYBRIDRAG_TESSERACT_CMD` works for PDF OCR but not image OCR, and vice versa. A user will think they configured Tesseract correctly when only half the OCR pipeline sees it.

**Fix:** Standardize on `HYBRIDRAG_TESSERACT_CMD` in both files.

---

### BUG-MED-006: EML parser doesn't decode HTML entities

**File:** `src/parsers/eml_parser.py:44-79`
**Severity:** MEDIUM -- Corrupted text in search index

The `_strip_html` function removes HTML tags but doesn't decode entities like `&amp;`, `&lt;`, `&gt;`, `&nbsp;`. Text like "AT&amp;T" stays as "AT&amp;T" instead of "AT&T".

**Impact:** Keyword search for "AT&T" won't match "AT&amp;T" in the FTS5 index. This affects all HTML-formatted emails.

**Fix:** Add `import html` and call `html.unescape(text)` after stripping tags.

---

### BUG-MED-007: PIL images never closed in OCR parsers

**Files:** `src/parsers/pdf_ocr_fallback.py:226`, `src/parsers/image_parser.py:102`
**Severity:** MEDIUM -- Memory leak during batch processing

PIL `Image.open()` and `convert_from_path()` return objects that keep file handles and image data in memory. Neither parser closes them explicitly. During batch indexing of many images or PDFs with OCR, this accumulates gigabytes of uncollectable memory.

**Fix:** Use `with` statements or call `img.close()` in `finally` blocks.

---

### BUG-MED-008: Global state mutation in threaded OCR

**File:** `src/parsers/pdf_ocr_fallback.py:139`
**Severity:** MEDIUM -- Race condition in concurrent indexing

```python
def _ocr_page_image_to_text(img, lang="eng"):
    ...
    pytesseract.pytesseract.tesseract_cmd = tess_cmd  # global state
```

**Impact:** If multiple files are OCR'd concurrently (e.g., via threading or multiprocessing), they race on `pytesseract.tesseract_cmd`. Should be set once at import time, not per-call.

---

### BUG-MED-009: DOCX parser misses table content

**File:** `src/parsers/office_docx_parser.py:36-39`
**Severity:** MEDIUM -- Silent content loss for engineering documents

Only `doc.paragraphs` is extracted. Tables, headers, and footers are ignored. For engineering documents where specifications live in tables, this means critical data is never indexed.

**Fix:** Add `doc.tables` iteration:
```python
for table in doc.tables:
    for row in table.rows:
        for cell in row.cells:
            parts.append(cell.text.strip())
```

---

### BUG-MED-010: EML `_safe_decode` may receive str instead of bytes

**File:** `src/parsers/eml_parser.py:229, 242`
**Severity:** MEDIUM -- Potential AttributeError crash

When using `policy=policy.default`, `msg.get_payload(decode=True)` on text parts may return `str` instead of `bytes`. Calling `.decode()` on a `str` raises `AttributeError`.

**Fix:** Add type guard at top of `_safe_decode`:
```python
if isinstance(payload, str):
    return payload
```

---

## 3. LOW-SEVERITY ISSUES

| # | File | Line | Issue |
|---|---|---|---|
| L-01 | `image_parser.py` | 80-86 | Dead code: `env_cmd` assigned but never used, triple reassignment of `tesseract_cmd_env` |
| L-02 | `image_parser.py` | 86 | Uses `__import__("os")` anti-pattern instead of normal import |
| L-03 | `plain_text_parser.py` | 28 | `errors="ignore"` silently drops undecodable bytes; `errors="replace"` would preserve content presence |
| L-04 | `plain_text_parser.py` | -- | No file size limit; a 10GB log file would OOM the process |
| L-05 | `pdf_parser.py` | 253, 341 | Redundant `(text or "")` guards -- `text` is always str |
| L-06 | `pdf_parser.py` | 330 | OCR `used` set to False even after partial OCR execution |
| L-07 | `pdf_ocr_fallback.py` | 248-251 | Page-level exceptions swallowed with no diagnostic data |
| L-08 | `eml_parser.py` | 290 | SHA1 for fingerprinting -- SHA256 preferred |
| L-09 | `office_pptx_parser.py` | 39 | Grouped shapes and table shapes not recursively traversed |
| L-10 | `text_parser.py` | 39 | New parser instance created per file (stateless, wasteful) |
| L-11 | `credentials.py` | 509 | `_nested_get` returns None for falsy values including `0` and `False` |
| L-12 | `feature_registry.py` | 324 | `color_hint` variable assigned but never used (leftover) |

---

## 4. CROSS-CUTTING SUGGESTIONS

### 4.1 Connection/Resource Management Pattern

Several modules create resources per-call that should be created once:
- `OllamaRouter` creates `httpx.Client` per query
- Parsers create `Image` objects without closing
- XLSX parser opens workbooks without closing

**Recommendation:** Establish a "resource lifecycle" pattern:
- Create in `__init__` or `connect()`
- Reuse across calls
- Close in `close()` or `__del__`
- Use context managers where possible

### 4.2 Parser Base Class

All parsers follow the same pattern (`parse(path) -> str`, `parse_with_details(path) -> (str, dict)`) but there's no enforced base class or protocol. Adding an abstract base class would:
- Catch missing methods at import time
- Document the expected interface
- Enable type checking

### 4.3 Environment Variable Consolidation

The project uses three naming conventions for env vars:
- `HYBRIDRAG_*` (canonical)
- `AZURE_OPENAI_*` (Azure SDK convention)
- `TESSERACT_CMD` vs `HYBRIDRAG_TESSERACT_CMD`

**Recommendation:** Standardize all HybridRAG-specific env vars with `HYBRIDRAG_` prefix and document the mapping clearly in one place.

### 4.4 Error Recovery in Indexer

The indexer has good crash-safety via `INSERT OR IGNORE`, but the parsers have inconsistent error reporting. Some swallow exceptions silently (OCR fallback), some return empty strings, some raise. A standardized `ParseResult(text, warnings, errors)` return type would improve diagnostic quality.

### 4.5 Config Validation at Load Time

`default_config.yaml` has empty string defaults for `paths.database`, `paths.embeddings_cache`, and `paths.source_folder`. If someone forgets to set these in `start_hybridrag.ps1`, the system will silently use the current working directory. Adding a boot validation check ("are paths configured?") would prevent subtle bugs.

---

## 5. WHAT'S WORKING WELL

These aspects of the codebase are solid and well-engineered:

1. **Deterministic chunk IDs** (`chunk_ids.py`) -- Excellent crash-safety design. INSERT OR IGNORE with content-based IDs means restarts are fully resumable.

2. **3-layer network security** -- PowerShell env vars + Python env enforcement + NetworkGate runtime checks. Defense in depth, properly documented.

3. **Exception hierarchy** (`exceptions.py`) -- Clear, well-categorized errors with fix suggestions and error codes. The `exception_from_http_status()` helper eliminates scattered if/elif chains.

4. **Credential resolution** (`credentials.py`) -- Single source of truth with clear priority ordering, masked logging, and backward-compatible aliases. Well-documented env var mapping.

5. **Health check design** -- Simple `(ok, message)` tuple pattern is easy to consume in any UI. Clean separation from VectorStore.

6. **Hybrid search with RRF** (`retriever.py`) -- Solid algorithm choice. RRF avoids the score-scale mismatch problem between vector and keyword results.

7. **Comprehensive documentation** -- Every file has clear header comments explaining what, why, and how. Design decisions are documented inline with alternatives considered.

8. **Feature registry** (`feature_registry.py`) -- Clean GUI-ready design with category grouping, impact notes, and dependency tracking.

---

## 6. PRIORITY FIX ORDER

If addressing these in order of impact:

1. **BUG-HIGH-001** (boot.py Ollama key name) -- One-line fix, high impact
2. **BUG-HIGH-003** (XLSX file handle leak) -- Small fix, prevents crashes during batch indexing
3. **BUG-MED-001** (TimeoutError shadow) -- Rename to avoid confusion
4. **BUG-MED-002** (empty choices guard) -- One-line guard prevents crashes
5. **BUG-MED-003** (duplicate logger handlers) -- Prevents log noise
6. **BUG-MED-005** (Tesseract env var inconsistency) -- Quick alignment fix
7. **BUG-MED-006** (HTML entity decoding) -- Improves search quality
8. **BUG-MED-009** (DOCX table extraction) -- Significant content improvement
9. **BUG-HIGH-002** (OCR timeout) -- Requires design change, but prevents hangs
10. **BUG-MED-004** (httpx client reuse) -- Performance improvement

---

*Report generated by automated code review. All line numbers verified against current codebase.*
