# Python Learning Curriculum for RF Engineers Transitioning to AI Engineering

## 12-Week Plan Using HybridRAG3 as the Teaching Codebase

**Author:** Claude AI
**Date:** 2026-02-13
**Student Profile:** Jeremy -- RF field engineer at a defense contractor, bachelor's in engineering technology, master's in engineering management, 5 weeks into AI applications development, learning Python through hands-on building with zero prior coding experience
**Teaching Codebase:** HybridRAG3 (Jeremy's RAG system: Python 3.11, SQLite, sentence-transformers, Ollama, openai SDK)

---

## Table of Contents

1. [Curriculum Philosophy](#1-curriculum-philosophy)
2. [Week 1-2: Python Foundations Through HybridRAG3 Code Reading](#weeks-1-2)
3. [Week 3-4: Data Structures and File I/O Through Real Config Management](#weeks-3-4)
4. [Week 5-6: Functions, Modules, and the Router Pattern](#weeks-5-6)
5. [Week 7-8: Error Handling, Logging, and Defensive Programming](#weeks-7-8)
6. [Week 9-10: APIs, HTTP, and Network Programming](#weeks-9-10)
7. [Week 11-12: SQLite, Embeddings, and AI Integration](#weeks-11-12)
8. [Assessment Framework](#assessment-framework)
9. [Resources and References](#resources-and-references)
10. [Certification Roadmap](#certification-roadmap)

---

## 1. Curriculum Philosophy

### Why This Curriculum Is Different

Most Python curricula teach you to write "Hello World," then calculate Fibonacci sequences, then build a todo app. This is backwards for you. You already HAVE a working system (HybridRAG3) that does real engineering work. You don't need to learn Python in the abstract -- you need to understand the Python you're already using so you can debug it, extend it, and explain it.

### The RF Engineer's Advantage

You already think in systems. You understand signal chains, where noise enters, how to isolate variables, and how to trace signal flow from input to output. Python programming is exactly the same mental model:

| RF Concept | Python Equivalent |
|-----------|------------------|
| Signal chain | Data pipeline (function calls passing data) |
| Impedance matching | Type compatibility (strings vs integers vs lists) |
| Filtering | Data validation and cleaning |
| Modulation/Demodulation | Encoding/Decoding (UTF-8, JSON, base64) |
| Multiplexing | Threading/async (parallel processing) |
| Noise floor | Error handling (try/except) |
| Spectrum analyzer | Debugger and logging |
| S-parameters | Function signatures (inputs/outputs) |
| Smith chart | Data flow diagrams |
| Antenna pattern | API endpoint mapping |

### Learning Method: Read, Modify, Break, Fix, Build

Each week follows the same pattern:

1. **READ** existing HybridRAG3 code and annotate what each line does
2. **MODIFY** one small thing and predict what will happen
3. **BREAK** something intentionally and observe the error
4. **FIX** the break, understanding why the fix works
5. **BUILD** a small new feature that uses what you learned

---

## Weeks 1-2: Python Foundations Through HybridRAG3 Code Reading {#weeks-1-2}

### Week 1: Variables, Types, and Basic Operations

**Goal:** Understand what every line in save_session.py does, at the Python language level.

**Day 1-2: Variables and Types**

Open `save_session.py` in VS Code. Let's decode what you're looking at.

```python
# WHAT YOU'LL SEE in save_session.py (line ~15):
SAVE_DIR = r"E:\KnowledgeBase\claude_sessions\raw"

# LET'S BREAK THIS DOWN:
# SAVE_DIR      -- This is a VARIABLE NAME. It's a label for a box that holds data.
#                  Python convention: ALL_CAPS means "this doesn't change" (a constant)
#
# =             -- Assignment operator. "Put what's on the right into the box on the left"
#
# r"..."        -- This is a RAW STRING. The 'r' prefix tells Python:
#                  "Don't interpret backslashes as escape characters"
#                  Without 'r': "E:\Knowled..." -- Python sees \K as an escape sequence
#                  With 'r': r"E:\Knowled..." -- Python treats \ as a literal backslash
#                  RULE: Always use r"..." for Windows file paths
#
# "E:\KnowledgeBase\claude_sessions\raw"
#               -- This is a STRING -- a sequence of text characters.
#                  Strings are always wrapped in quotes (single ' or double ")
```

**RF Analogy:** A variable is like a labeled test point on a circuit board. `SAVE_DIR` is the test point label. `r"E:\KnowledgeBase\..."` is the voltage (value) at that point. The `=` sign is like connecting a wire from the source to the test point.

```python
# MORE EXAMPLES FROM save_session.py:
MIN_CLIPBOARD_SIZE = 50      # INTEGER -- a whole number (no decimal point)
                              # Python type: int

session_num = 1               # Another integer, but lowercase name means
                              # "this WILL change during execution"

clipboard_text = ""           # STRING -- empty string (no characters yet)
                              # Python type: str

word_count = 0                # INTEGER
token_estimate = 0            # INTEGER

is_valid = True               # BOOLEAN -- can only be True or False
                              # Python type: bool
                              # Like a digital signal: HIGH (True) or LOW (False)
```

**Exercise 1.1:** Open save_session.py. Find every variable assignment (lines with `=`). For each one, write a comment identifying the type (str, int, bool, list, dict).

**Exercise 1.2:** Open a Python terminal and experiment:

```python
# Try these in order. Predict the output before pressing Enter.
x = 10
y = 3
print(x + y)      # What do you expect?
print(x * y)      # What do you expect?
print(x / y)      # What do you expect? (Hint: division ALWAYS returns a float)
print(x // y)     # What do you expect? (Floor division -- drops the decimal)
print(x % y)      # What do you expect? (Modulo -- the remainder)
print(x ** y)      # What do you expect? (Exponentiation -- x to the power of y)

# Now with strings:
name = "HybridRAG"
version = "3"
print(name + version)       # String concatenation
print(name + " " + version) # Concatenation with space
# print(name + 3)           # UNCOMMENT THIS -- what error do you get? Why?
print(name + str(3))        # How to fix it: convert int to str first
print(f"{name} version {version}")  # f-string: the BEST way to mix variables into text
```

**Day 3-4: Strings and String Methods**

Your code manipulates text constantly -- file paths, clipboard contents, YAML, JSON. Understanding strings is critical.

```python
# FROM save_session.py -- the sanitize_text() function:

def sanitize_text(text):
    """Remove smart quotes, em-dashes, and other Unicode that breaks PS 5.1"""
    
    # .replace() is a STRING METHOD -- a function built into every string
    # It returns a NEW string with the replacement made (strings are immutable)
    text = text.replace("\u2018", "'")   # Left single smart quote -> straight quote
    text = text.replace("\u2019", "'")   # Right single smart quote (apostrophe)
    text = text.replace("\u201C", '"')   # Left double smart quote
    text = text.replace("\u201D", '"')   # Right double smart quote
    text = text.replace("\u2013", "--")  # En-dash -> double hyphen
    text = text.replace("\u2014", "--")  # Em-dash -> double hyphen
    text = text.replace("\uFEFF", "")    # BOM marker -> removed entirely
    
    # WHAT'S HAPPENING:
    # 1. text.replace(old, new) searches the ENTIRE string for 'old'
    # 2. Every occurrence of 'old' gets replaced with 'new'
    # 3. A NEW string is returned (the original is NOT modified)
    # 4. text = text.replace(...) reassigns the variable to the new string
    #
    # WHY THIS MATTERS:
    # PowerShell 5.1 on your work laptop chokes on Unicode characters.
    # These smart quotes come from Word/Outlook/OneNote.
    # If they sneak into your scripts, PS 5.1 throws syntax errors.
    
    return text  # Return the cleaned string to whoever called this function
```

**RF Analogy:** `sanitize_text()` is like a bandpass filter. The input signal (text) goes through multiple filter stages (each `.replace()` call). Each stage removes a specific unwanted frequency (Unicode character). The output is a clean signal that your receiver (PowerShell 5.1) can process without errors.

**Exercise 1.3:** String method practice. Try these in a Python terminal:

```python
# String methods you'll use constantly in HybridRAG3:
path = r"D:\RAG Source Data\document.pdf"

print(path.split("\\"))       # Split by backslash -> list of parts
print(path.endswith(".pdf"))   # Check file extension -> True
print(path.lower())            # Lowercase everything
print(path.upper())            # Uppercase everything

text = "  Hello, World!  "
print(text.strip())            # Remove leading/trailing whitespace
print(text.lstrip())           # Remove leading whitespace only
print(text.rstrip())           # Remove trailing whitespace only

filename = "2026-02-13_session_01.md"
print(filename.startswith("2026"))    # True
print(filename.replace(".md", ".txt"))  # Change extension

# f-strings (formatted string literals) -- the most useful Python feature:
name = "Jeremy"
session = 3
date = "2026-02-13"
print(f"Session {session} by {name} on {date}")
print(f"File: {date}_session_{session:02d}.md")  # :02d means "2 digits, zero-padded"
```

**Day 5-7: Control Flow (if/elif/else, for loops, while loops)**

```python
# FROM save_session.py -- validation logic:

if not self.clipboard_text or len(self.clipboard_text) < MIN_CLIPBOARD_SIZE:
    # This block runs ONLY IF the clipboard is empty or too short
    messagebox.showerror("No Content", "Clipboard is empty or too short.")
    return  # Exit the function early -- don't try to save
    
# BREAKDOWN:
# if          -- Start a conditional check
# not         -- Boolean negation (like a NOT gate in digital logic)
# self.clipboard_text  -- The variable being tested
#             When a string is empty (""), Python treats it as False
#             When a string has content, Python treats it as True
#             So "not self.clipboard_text" means "if clipboard is empty"
# or          -- Boolean OR (like an OR gate)
#             True if EITHER condition is true
# len()       -- Built-in function that returns the LENGTH of something
# <           -- Less than comparison
# MIN_CLIPBOARD_SIZE  -- The constant we defined earlier (50)
#
# RF ANALOGY: This is like a threshold detector.
# If the input signal (clipboard) is below the noise floor (MIN_CLIPBOARD_SIZE),
# reject the signal (show error, return early).
# Only process signals above the threshold.
```

```python
# FOR LOOPS -- iterating over collections

# Example from primer_generator.py:
for filepath in session_files:
    # This block runs ONCE for each file in the list
    # 'filepath' takes on a different value each iteration
    content = read_file(filepath)
    chunks = split_into_chunks(content)
    # ... process chunks ...

# ENUMERATE -- when you need both the index AND the value:
for i, filepath in enumerate(session_files):
    print(f"Processing file {i+1}/{len(session_files)}: {filepath}")

# RANGE -- generate a sequence of numbers:
for i in range(5):          # 0, 1, 2, 3, 4
    print(i)

for i in range(1, 6):       # 1, 2, 3, 4, 5
    print(i)

for i in range(0, 10, 2):   # 0, 2, 4, 6, 8 (step by 2)
    print(i)

# RF ANALOGY: A for loop is like a frequency sweep.
# range(start_freq, stop_freq, step_size) defines the sweep.
# The loop body is the measurement you take at each frequency.
```

**Exercise 1.4:** Write a script that counts how many `.md` files are in your `E:\KnowledgeBase\claude_sessions\raw` directory:

```python
# count_sessions.py
import os

session_dir = r"E:\KnowledgeBase\claude_sessions\raw"
count = 0

for filename in os.listdir(session_dir):
    if filename.endswith(".md"):
        count += 1
        print(f"  Found: {filename}")

print(f"\nTotal session files: {count}")
```

### Week 2: Lists, Dictionaries, and File Operations

**Day 8-9: Lists**

```python
# Lists are ordered collections. Like an array of measurement samples.

# FROM HybridRAG3 -- collecting chunk results:
chunks = []  # Empty list -- like initializing an empty data buffer

# .append() adds an item to the end of the list
chunks.append({"content": "First chunk...", "score": 0.95})
chunks.append({"content": "Second chunk...", "score": 0.82})
chunks.append({"content": "Third chunk...", "score": 0.71})

# Accessing list items by INDEX (0-based -- first item is index 0):
first = chunks[0]     # First item
last = chunks[-1]     # Last item (negative index counts from end)
top_two = chunks[:2]  # Slicing: items 0 and 1 (first two)

# List comprehension -- Python's most powerful feature for transforming data:
# "Give me the score from each chunk"
scores = [chunk["score"] for chunk in chunks]
# Result: [0.95, 0.82, 0.71]

# "Give me only chunks with score above 0.8"
good_chunks = [chunk for chunk in chunks if chunk["score"] > 0.8]
# Result: [{"content": "First...", "score": 0.95}, {"content": "Second...", "score": 0.82}]

# RF ANALOGY: A list is like a time-domain signal buffer.
# Each element is a sample. You can access by index (time position),
# slice to get a window, filter by threshold, and transform each sample.
```

**Day 10-11: Dictionaries**

```python
# Dictionaries store KEY:VALUE pairs. Like a lookup table or configuration register.

# FROM HybridRAG3 -- configuration:
config = {
    "ollama_model": "llama3:8b",       # String value
    "ollama_port": 11434,               # Integer value
    "top_k": 5,                         # Integer value
    "min_score": 0.3,                   # Float value
    "network_enabled": False,           # Boolean value
    "source_dirs": [                    # List value (nested!)
        r"D:\RAG Source Data",
        r"E:\KnowledgeBase"
    ]
}

# Accessing values by key:
model = config["ollama_model"]           # "llama3:8b"
port = config.get("ollama_port", 11434)  # .get() returns default if key missing

# Modifying values:
config["top_k"] = 10                     # Change existing value
config["new_setting"] = "value"          # Add new key-value pair

# Checking if a key exists:
if "network_enabled" in config:
    print(f"Network: {'ON' if config['network_enabled'] else 'OFF'}")

# Iterating over a dictionary:
for key, value in config.items():
    print(f"  {key}: {value}")

# RF ANALOGY: A dictionary is like the register map of an RF transceiver IC.
# Each register address (key) maps to a value.
# config["ollama_port"] = 11434 is like Register 0x04 = 0x2C9A
# You read registers, write registers, and check if a register exists.
```

**Day 12-14: File Operations**

```python
# FROM save_session.py -- writing a markdown file:

filepath = r"E:\KnowledgeBase\claude_sessions\raw\2026-02-13_session_01.md"

# WRITING a file:
with open(filepath, "w", encoding="utf-8") as f:
    f.write(full_content)

# BREAKDOWN:
# with          -- Context manager. AUTOMATICALLY closes the file when done.
#                  Like auto-zeroing a meter after measurement.
# open()        -- Built-in function to open a file
# filepath      -- Path to the file
# "w"           -- Mode: "w" = write (creates/overwrites), "r" = read, "a" = append
# encoding="utf-8"  -- Character encoding. ALWAYS specify this.
# as f          -- 'f' is the variable name for the file object
# f.write()     -- Write text to the file

# READING a file:
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()      # Read entire file into one string
    # OR
    lines = f.readlines()   # Read into a list of lines

# READING line by line (memory-efficient for large files):
with open(filepath, "r", encoding="utf-8") as f:
    for line in f:           # Python iterates one line at a time
        process(line)        # Only one line in memory at a time

# CHECKING if file exists before reading:
import os
if os.path.exists(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
else:
    print(f"[WARN] File not found: {filepath}")

# pathlib -- the MODERN way to handle paths (recommended):
from pathlib import Path

session_dir = Path(r"E:\KnowledgeBase\claude_sessions\raw")
md_files = list(session_dir.glob("*.md"))       # All .md files
today_files = list(session_dir.glob("2026-02-13*.md"))  # Today's sessions

for f in md_files:
    print(f"  {f.name}: {f.stat().st_size:,} bytes")
```

**PROJECT 1 (end of Week 2):** Write a session analyzer that reads all your saved session markdown files and produces a summary:

```python
# session_analyzer.py
# YOUR FIRST COMPLETE PYTHON PROGRAM
# Reads all session files, extracts metadata, produces a report

import os
from pathlib import Path
from datetime import datetime

# ---- CONFIGURATION ----
SESSION_DIR = Path(r"E:\KnowledgeBase\claude_sessions\raw")
REPORT_FILE = Path(r"E:\KnowledgeBase\session_report.txt")

def analyze_sessions():
    """Scan all session files and produce a summary report."""
    
    session_files = sorted(SESSION_DIR.glob("*.md"))
    
    if not session_files:
        print("[WARN] No session files found")
        return
    
    total_words = 0
    total_files = 0
    sessions_by_date = {}
    
    for filepath in session_files:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        
        words = len(content.split())
        total_words += words
        total_files += 1
        
        # Extract date from filename (2026-02-13_session_01.md)
        date_str = filepath.name[:10]  # First 10 chars = date
        if date_str not in sessions_by_date:
            sessions_by_date[date_str] = []
        sessions_by_date[date_str].append({
            "filename": filepath.name,
            "words": words,
            "size_kb": filepath.stat().st_size / 1024
        })
    
    # ---- GENERATE REPORT ----
    report_lines = []
    report_lines.append(f"SESSION ANALYSIS REPORT")
    report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"{'='*60}")
    report_lines.append(f"Total sessions: {total_files}")
    report_lines.append(f"Total words: {total_words:,}")
    report_lines.append(f"Average words/session: {total_words // max(total_files, 1):,}")
    report_lines.append(f"Date range: {min(sessions_by_date.keys())} to {max(sessions_by_date.keys())}")
    report_lines.append(f"")
    
    for date in sorted(sessions_by_date.keys()):
        sessions = sessions_by_date[date]
        day_words = sum(s["words"] for s in sessions)
        report_lines.append(f"{date}: {len(sessions)} sessions, {day_words:,} words")
        for s in sessions:
            report_lines.append(f"  - {s['filename']}: {s['words']:,} words ({s['size_kb']:.1f} KB)")
    
    # Print to terminal
    report = "\n".join(report_lines)
    print(report)
    
    # Save to file
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n[OK] Report saved to {REPORT_FILE}")


if __name__ == "__main__":
    analyze_sessions()
```

---

## Weeks 3-4: Data Structures and File I/O Through Real Config Management {#weeks-3-4}

### Week 3: YAML, JSON, and Configuration Files

**Why This Matters:** Your entire HybridRAG3 system is configured through YAML and JSON files. Your primers are YAML. Your API responses are JSON. Understanding these formats is non-negotiable.

**Topics covered:**
- YAML parsing with PyYAML
- JSON parsing with built-in `json` module
- Configuration management patterns (config files, environment variables, keyring)
- Building a config validator that checks your HybridRAG3 setup

**PROJECT 2:** Build `config_validator.py` -- a script that checks every config file, environment variable, and dependency in your HybridRAG3 installation and reports what's working and what's broken. Think of it as `rag-diag` but as a learning exercise you build yourself.

### Week 4: Classes and Object-Oriented Programming

**Why This Matters:** Your `save_session.py` already uses classes (`SessionSaver`). Your `llm_router.py` uses the router pattern with classes. Understanding classes is understanding how your code is organized.

**Topics covered:**
- What classes are (blueprints for objects, like a schematic for a circuit)
- `__init__` (the constructor -- like powering up a module)
- Methods (functions that belong to a class)
- Properties and state (data the object remembers between method calls)
- Inheritance (how `OllamaRouter` and `APIRouter` share a common interface)
- The router pattern in `llm_router.py` -- why it exists and how it works

**PROJECT 3:** Refactor one of your utility scripts into a proper class with error handling, logging, and a clean API. Suggested target: build a `SessionManager` class that handles finding, reading, analyzing, and searching session files.

---

## Weeks 5-6: Functions, Modules, and the Router Pattern {#weeks-5-6}

### Week 5: Writing Good Functions

**Topics covered:**
- Function parameters, return values, default arguments
- Type hints (telling Python what types a function expects and returns)
- Docstrings (documenting what a function does)
- Pure functions vs functions with side effects
- The DRY principle (Don't Repeat Yourself)

**Reading assignment:** Annotate every function in `primer_generator.py`. For each function, write: What does it take in? What does it return? What side effects does it have? Could it be simpler?

### Week 6: Modules and Project Structure

**Topics covered:**
- How Python imports work (`import os`, `from pathlib import Path`)
- Creating your own modules (each .py file is a module)
- Package structure (the `__init__.py` file)
- The `if __name__ == "__main__"` pattern (why every script has it)
- Circular imports and how to avoid them
- Understanding HybridRAG3's module dependency graph

**PROJECT 4:** Draw a dependency diagram of all HybridRAG3 Python files. Which file imports from which? Are there any circular dependencies? Can anything be simplified?

---

## Weeks 7-8: Error Handling, Logging, and Defensive Programming {#weeks-7-8}

### Week 7: Exception Handling

**Why This Matters:** The difference between code that works in development and code that works in production is error handling. Your API 401 errors, PowerShell quoting issues, and file permission problems are all exceptions that need to be caught and handled gracefully.

**Topics covered:**
- try/except blocks (catching errors without crashing)
- Specific exception types (FileNotFoundError, ConnectionError, json.JSONDecodeError)
- The exception hierarchy (when to catch broad vs specific)
- Raising your own exceptions
- Context managers (`with` statements) for resource cleanup
- Retry logic with exponential backoff (critical for API calls)

**PROJECT 5:** Add proper error handling to `llm_router.py`. Every external call (Ollama, Azure, OpenRouter) should have: try/except, retry logic, timeout handling, and meaningful error messages that help you diagnose the problem.

### Week 8: Logging and Diagnostics

**Topics covered:**
- Python's `logging` module (replacing `print()` statements)
- Log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Log formatting with timestamps and module names
- File logging for audit trails (NIST 800-171 requirement)
- Building diagnostic tools (`rag-diag` internals)

**PROJECT 6:** Build a `flight_recorder.py` module that logs every HybridRAG3 operation (queries, retrievals, API calls, errors) to a rotating log file with timestamps. This becomes your audit trail.

---

## Weeks 9-10: APIs, HTTP, and Network Programming {#weeks-9-10}

### Week 9: Understanding HTTP and REST APIs

**Why This Matters:** Your llm_router talks to Ollama via HTTP. Your OpenRouter integration calls a REST API. Your Azure endpoint uses HTTPS with authentication headers. Understanding HTTP is understanding how your system communicates.

**Topics covered:**
- HTTP methods (GET, POST, PUT, DELETE)
- Headers, request bodies, response codes (200 OK, 401 Unauthorized, 500 Server Error)
- JSON request/response format
- The `openai` SDK and how it wraps HTTP calls
- Authentication methods (API keys, Bearer tokens, Azure-specific headers)
- Your network lockdown system (environment variables, kill switches)

**PROJECT 7:** Build `api_tester.py` -- a diagnostic tool that tests connectivity to every configured API endpoint (Ollama, OpenRouter, Azure) and reports the status, response time, and any errors. Include a `--dry-run` mode that shows what would be tested without making actual calls.

### Week 10: Security and Network Control

**Topics covered:**
- The three-layer network security model in HybridRAG3
- Environment variables for network control (HF_HUB_OFFLINE, NETWORK_KILL_SWITCH)
- The `keyring` module for secure credential storage
- AES-256 encryption at rest (what it means, how to implement)
- TLS 1.3 in transit (what it means, how Python handles it)
- PII sanitization (detecting and removing sensitive information)

**PROJECT 8:** Build `pii_scanner.py` -- a tool that scans your indexed documents for potential PII (names, emails, phone numbers, SSNs) and reports what it finds. Use regex patterns and string matching. This is a real defense-environment requirement.

---

## Weeks 11-12: SQLite, Embeddings, and AI Integration {#weeks-11-12}

### Week 11: SQLite and Database Operations

**Why This Matters:** HybridRAG3 stores everything in SQLite -- chunks, embeddings metadata, configuration, credential references. Understanding SQL lets you inspect, debug, and extend the database directly.

**Topics covered:**
- SQL basics (SELECT, INSERT, UPDATE, DELETE, WHERE, JOIN)
- Python's `sqlite3` module
- Parameterized queries (preventing SQL injection)
- Database schema design
- Indexing for performance
- WAL mode for concurrent access

**PROJECT 9:** Write a `db_inspector.py` tool that connects to `hybridrag.sqlite3` and provides: table listing, row counts, sample data preview, schema dump, and basic statistics (total chunks, average chunk size, most-indexed files).

### Week 12: Embeddings, Vector Search, and Putting It All Together

**Topics covered:**
- What embeddings are (converting text to numbers that capture meaning)
- How sentence-transformers works
- Cosine similarity (measuring how "close" two embeddings are)
- The HybridRAG3 retrieval pipeline from query to answer
- The complete system architecture as a Python application

**CAPSTONE PROJECT:** Build `hybridrag_lite.py` -- a minimal, self-contained RAG system in a single file. It should: read text files, split them into chunks, compute embeddings with sentence-transformers, store them in SQLite, accept a query, find the most similar chunks, and display the results. This is HybridRAG3 stripped to its essence -- approximately 200 lines of Python that demonstrate you understand every layer of the system you built.

This capstone proves three things:
1. You understand Python well enough to build a working system from scratch
2. You understand RAG architecture well enough to implement it independently
3. You can explain every line to someone else (the nonprogrammer commentary requirement)

---

## Assessment Framework

### Weekly Self-Assessment Checklist

Each week, rate yourself 1-5 on each item:

| Week | Skill | 1 (Lost) | 3 (Getting it) | 5 (Can teach it) |
|------|-------|----------|-----------------|-------------------|
| 1 | I can identify variable types in existing code | | | |
| 1 | I understand string methods and f-strings | | | |
| 2 | I can read and write files with proper encoding | | | |
| 2 | I understand lists, dicts, and list comprehensions | | | |
| 3 | I can parse YAML and JSON configuration files | | | |
| 4 | I understand classes and why llm_router uses them | | | |
| 5 | I can write functions with type hints and docstrings | | | |
| 6 | I understand how Python imports and modules work | | | |
| 7 | I can add error handling that produces useful diagnostics | | | |
| 8 | I can implement logging with audit-grade timestamps | | | |
| 9 | I understand HTTP requests and API authentication | | | |
| 10 | I can explain the network security model | | | |
| 11 | I can write SQL queries and use sqlite3 from Python | | | |
| 12 | I can explain how embeddings and vector search work | | | |

### Band 4 Competency Mapping

Each project maps to Band 4 AI Engineering competencies:

| Project | Band 4 Competency | Evidence |
|---------|-------------------|----------|
| Session Analyzer (P1) | Data processing and analysis | Working code that processes real project data |
| Config Validator (P2) | System integration testing | Automated validation of complex system config |
| SessionManager Class (P3) | Software design patterns | OOP design with clean API |
| Dependency Diagram (P4) | Architecture documentation | Visual system understanding |
| Error Handling (P5) | Production-grade code | Robust error handling for distributed systems |
| Flight Recorder (P6) | Audit and compliance | Defense-grade logging implementation |
| API Tester (P7) | Integration testing | Automated API health checking |
| PII Scanner (P8) | Security engineering | Data protection implementation |
| DB Inspector (P9) | Database engineering | Data management and querying |
| RAG Lite (Capstone) | AI systems engineering | End-to-end AI pipeline implementation |

---

## Resources and References

### Books (in recommended reading order)

1. **"Automate the Boring Stuff with Python"** by Al Sweigart (FREE online) -- Best intro for non-programmers. Read chapters that map to your weekly topics.

2. **"Python Crash Course"** by Eric Matthes -- More structured than Automate. Good for filling gaps.

3. **"Fluent Python"** by Luciano Ramalho -- AFTER the 12 weeks. This is the book that turns you from "writes Python" to "thinks in Python."

### Online Resources

- **Real Python (realpython.com)** -- High-quality tutorials with practical examples
- **Python Documentation (docs.python.org)** -- The official reference. Dense but authoritative.
- **r/learnpython** -- Reddit community for beginners
- **Stack Overflow** -- Search before asking. Your error message is almost certainly already answered.

### YouTube Channels

- **Corey Schafer** -- Best Python tutorials on YouTube. Clear, practical, no fluff.
- **Sentdex** -- Python for AI/ML, relevant to your trajectory
- **ArjanCodes** -- Software design patterns in Python (Week 4-6 level)

---

## Certification Roadmap

### Short-term (3-6 months)

- **AWS Certified AI Practitioner** -- Validates understanding of AI concepts and cloud AI services. Good credential for defense contractor promotion.
- **CompTIA Security+** -- If you don't already have it. Required/recommended for many defense IT roles.

### Medium-term (6-12 months)

- **AWS Certified Machine Learning - Specialty** -- Deeper ML certification. Shows you understand model training, tuning, and deployment.
- **PCEP (Python Certified Entry-Level Programmer)** -- Quick certification that formally validates Python skills.

### Long-term (12-24 months)

- **PCAP (Python Certified Associate Programmer)** -- More advanced Python certification.
- **Certified Kubernetes Application Developer (CKAD)** -- If your systems move to containerized deployment.

### Band 4 Demonstration Portfolio

By the end of this 12-week curriculum, you'll have:

1. 10 working Python projects that demonstrate increasing complexity
2. A fully annotated HybridRAG3 codebase showing deep understanding
3. Diagnostic tools that prove systems engineering capability
4. A capstone project that demonstrates end-to-end AI pipeline knowledge
5. Documentation and comments that prove you can teach what you've learned

This portfolio, combined with HybridRAG3 itself and the Limitless App, makes an extremely strong Band 4 case. You're not just learning Python -- you're building production AI systems for defense environments while learning Python. That's the story.

---

*Curriculum generated 2026-02-13. Designed for Jeremy's specific transition path from RF field engineering to AI applications development. All code examples reference the actual HybridRAG3 codebase and development environment.*
