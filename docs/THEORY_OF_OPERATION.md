# HybridRAG3 -- Theory of Operation (High Level)

Last Updated: 2026-02-20

---

## What Is HybridRAG?

HybridRAG is a system that lets you search through hundreds of documents
using natural language questions, and get back accurate, sourced answers.

Think of it like a research assistant that has read every document in your
filing cabinet and can instantly find the relevant paragraphs when you ask
a question like "What frequency does the antenna operate at?" -- except
instead of a person flipping through pages, it is software running on
your own computer.

The "Hybrid" in the name means it combines two different search methods
to find the best results. The "RAG" stands for Retrieval-Augmented
Generation, which is the technical term for "find relevant information
first, then use an AI to write an answer based on that information."

---

## The Big Picture

HybridRAG does two things:

1. **Indexing** -- Reads all your documents once and organizes them
   for fast searching (like building an index at the back of a book)

2. **Querying** -- When you ask a question, it finds the most relevant
   passages and uses an AI to write a direct answer based on those
   passages

---

## How Indexing Works (Step by Step)

Imagine you have a filing cabinet full of PDFs, Word documents, Excel
spreadsheets, and PowerPoint presentations. Here is what happens when
you run the indexer:

### Step 1: Read Every Document

The system opens each file and extracts the text. Different file types
need different tools:
- PDFs are read with a PDF text extractor
- Word documents (.docx) are unzipped (they are actually ZIP files
  containing XML) and the text is pulled out
- Excel spreadsheets have each row converted to a text line
- PowerPoint slides have each text box extracted
- Images are run through OCR (optical character recognition) to convert
  pictures of text into actual text
- Plain text files (.txt, .md, .csv) are just read directly

### Step 2: Break Text Into Chunks

A 500-page PDF might contain 2 million characters. That is too much for
any search system to handle as one piece. So the text is split into
smaller pieces called "chunks" -- about 1,200 characters each (roughly
half a printed page).

The splitting is done intelligently:
- Chunks break at paragraph boundaries when possible, not mid-sentence
- Each chunk overlaps the next by 200 characters, so if an important
  fact spans the boundary, it appears in full in at least one chunk
- Section headings are attached to each chunk, so the system knows that
  a chunk saying "Set the value to 5.0" came from "Section 3.2.1
  Calibration Procedure"

### Step 3: Convert Text to Numbers

Computers cannot understand words directly. To search by meaning (not
just keywords), each chunk of text is converted into a list of 384
numbers called an "embedding vector." This is done by a small AI model
(all-MiniLM-L6-v2, about 80 MB) that runs locally on your computer.

The key property: chunks with similar meanings produce similar number
lists. So "radio frequency range" and "RF operating band" end up with
very similar vectors, even though they share no words. This is what
makes semantic search possible.

### Step 4: Store Everything

Two storage systems hold the indexed data:

- **SQLite database** -- A single file that stores the text of every
  chunk, which file it came from, its position in that file, and a
  keyword search index. Think of this as the "text filing cabinet."

- **Memmap file** -- A binary file that stores all the embedding vectors
  in a compact format (float16, which uses half the storage of normal
  numbers). The computer can search this file without loading it all
  into memory, which means a laptop with 8 GB of RAM can search
  millions of embeddings. Think of this as the "meaning index."

---

## How Querying Works (Step by Step)

When you type a question like "What is the operating frequency?", here
is what happens:

### Step 1: Embed the Question

The same AI model that embedded the document chunks now converts your
question into the same kind of 384-number vector.

### Step 2: Search (Two Ways at Once)

This is the "hybrid" part. Two searches run simultaneously:

- **Vector search** -- Compares your question's vector against every
  stored chunk vector using cosine similarity (a mathematical way of
  measuring how similar two number lists are). Finds chunks whose
  *meaning* matches your question, even if they use different words.

- **Keyword search** -- Searches the text index for chunks containing
  your actual words. This catches exact terms like part numbers,
  acronyms, and technical terms that meaning-based search might miss.

### Step 3: Merge Results (Reciprocal Rank Fusion)

The two search methods produce two ranked lists of results. These are
combined using a technique called Reciprocal Rank Fusion (RRF):
- A chunk ranked high in both lists gets the highest combined score
- A chunk ranked high in only one list still appears, but lower
- This is the same algorithm used by Google and other major search
  engines to combine multiple ranking signals

The top results (typically 5-8 chunks) are selected.

### Step 4: Build Context and Ask the AI

The selected chunks are assembled into a "context" -- a package of
relevant information. This context, along with your original question,
is sent to an AI language model:

- **Offline mode** (default): The AI runs on your own computer via
  a program called Ollama. No internet needed. Slower (up to 3 minutes
  on CPU-only) but completely private.

- **Online mode** (optional): The question and context are sent to a
  company API (like GPT-3.5 Turbo). Much faster (2-5 seconds) but
  requires network access and an API key.

### Step 5: Return the Answer

The AI reads the context and writes a direct answer to your question,
citing which documents the information came from. The answer, sources,
and timing information are returned to you.

---

## The Hallucination Guard

When using the online AI mode, there is a risk the AI might "make up"
information that is not in the source documents. This is called
hallucination. HybridRAG has a 5-layer defense system to prevent this:

1. **Prompt Hardening** -- The instructions sent to the AI explicitly
   tell it to only use information from the provided context and to say
   "I don't know" if the answer is not in the sources.

2. **Claim Extraction** -- After the AI responds, the system breaks the
   answer into individual factual claims.

3. **NLI Verification** -- Each claim is checked against the source
   chunks using a Natural Language Inference model that determines if
   the claim is "supported," "contradicted," or "neutral" relative to
   the evidence.

4. **Confidence Scoring** -- Claims are scored and the overall response
   gets a faithfulness rating. Responses below the threshold are flagged.

5. **Dual-Path Consensus** -- For critical queries, the question can
   be sent to two different AI models and their answers compared. If they
   disagree, the system falls back to a safe, conservative response.

---

## Security: The Network Gate

HybridRAG was designed for environments where accidental data leakage
is unacceptable. A centralized "Network Gate" controls every outbound
network connection:

- **Offline mode** (default) -- Only localhost connections allowed.
  Zero internet traffic. Safe for restricted environments.

- **Online mode** -- Localhost plus one explicitly configured API
  endpoint. Nothing else. No phone-home, no telemetry, no updates.

- **Admin mode** -- Unrestricted, for maintenance only (installing
  packages, downloading models). Must be manually activated.

Every connection attempt (allowed or denied) is logged with a timestamp,
the URL, and the purpose. This creates an audit trail that can be
reviewed.

Three independent layers enforce this:
1. PowerShell environment variables block model downloads at the OS level
2. Python code blocks HuggingFace at the library level
3. The Network Gate blocks all other URLs at the application level

All three must fail simultaneously before any unauthorized data leaves
the machine.

---

## The Boot Pipeline

When HybridRAG starts up, a single "boot pipeline" runs all checks in
order -- like a car's startup sequence:

1. Load configuration from the YAML settings file
2. Resolve credentials (API key from Windows Credential Manager)
3. Validate configuration and credentials together
4. Configure the Network Gate to the correct security mode
5. Test connectivity (Ollama for offline, API for online)
6. Return a ready-to-use system, or a report of exactly what failed

This design means you never get a mysterious crash 10 minutes into
indexing because of a missing setting. Everything is validated upfront.

---

## Where Files Live

```
HybridRAG3/                          The program itself
|-- src/core/                        Core pipeline code
|-- src/parsers/                     File format readers
|-- src/security/                    Credential management
|-- src/diagnostic/                  Health checks and tests
|-- config/default_config.yaml       All settings in one file
+-- start_hybridrag.ps1              Startup script (run this first)

D:\RAG Indexed Data\                 Your search database (separate folder)
|-- hybridrag.sqlite3                Text chunks + keyword index
|-- embeddings.f16.dat               Meaning vectors (compact binary)
+-- embeddings_meta.json             Bookkeeping for the vectors

D:\RAG Source Data\                  Your original documents (unchanged)
+-- (PDFs, Word docs, etc.)          HybridRAG reads but never modifies these
```

---

## Key Design Principles

1. **Offline by default** -- Works without internet after initial setup.
   Network access is opt-in, never opt-out.

2. **Crash safety** -- If the power goes out during indexing, restart
   and it picks up where it left off. No data corruption.

3. **RAM efficiency** -- Processes documents in blocks, not all at once.
   A laptop with 8 GB of RAM can index thousands of documents.

4. **Auditability** -- Every indexing run, every query, and every
   network connection is logged with timestamps and run IDs.

5. **No magic** -- Direct HTTP calls instead of hidden SDK magic.
   Configuration in readable YAML, not buried in code. Every module
   has clear commentary explaining what it does and why.

6. **Graceful degradation** -- If a parser cannot read a file, it skips
   that file and continues. If the AI is unavailable, you still get the
   search results. If a config value is wrong, the boot pipeline tells
   you exactly what to fix.
