# HybridRAG3 -- System Architecture

> Block diagrams showing data flow through the system.
> All diagrams read top to bottom.

---

## Boot Sequence (runs once at startup)

```
         +---------------------+
         |        BOOT         |
         |      pipeline       |
         +---------------------+
                    |
         +----------+----------+----------+
         |          |          |          |
         v          v          v          v
    +--------+ +--------+ +--------+ +--------+
    | CONFIG | | CREDS  | | GATE   | | PROBE  |
    | loader | | keyring| | config | | Ollama |
    | (YAML) | | or env | | mode   | | + API  |
    +--------+ +--------+ +--------+ +--------+
         |          |          |          |
         +----------+----------+----------+
                    |
                    v
            +--------------+
            | BOOT RESULT  |
            | success flag |
            | api_client   |
            | warnings[]   |
            +--------------+
                    |
                    v
          System ready for use
```

---

## Query Path (user asks a question)

```
         "What is the calibration procedure?"
                    |
                    v
            +---------------+
            | QUERY ENGINE  |
            +---------------+
                    |
                    v
            +---------------+
            |   EMBEDDER    |
            | MiniLM-L6-v2  |
            | query -> 384d |
            +---------------+
                    |
                    v
            +---------------+
            |   RETRIEVER   |
            | hybrid search |
            +---------------+
               /         \
              v           v
        +---------+  +---------+
        |  BM25   |  | Vector  |
        | keyword |  | cosine  |
        | (FTS5)  |  | (mmap)  |
        +---------+  +---------+
              \           /
               v         v
            +---------------+
            |  Reciprocal   |
            |  Rank Fusion  |
            |  + min_score  |
            +---------------+
                    |
                    v
         top_k chunks (ranked)
                    |
                    v
            +---------------+
            | PROMPT BUILDER|
            | 9-rule system |
            +---------------+
                    |
                    v
            +---------------+
            |  LLM ROUTER   |
            +---------------+
                    |
             +------+------+
             |             |
             v             v
       +---------+   +---------+
       | OFFLINE |   | ONLINE  |
       | Ollama  |   | API     |
       | local   |   | gated   |
       +---------+   +---------+
             |             |
             |        +----------+
             |        | NETWORK  |
             |        | GATE     |
             |        | check +  |
             |        | audit    |
             |        +----------+
             |             |
             +------+------+
                    |
                    v
            +---------------+
            | QUERY RESULT  |
            | answer        |
            | sources       |
            | tokens, cost  |
            | latency       |
            +---------------+
                    |
                    v
           User sees answer
```

---

## Indexing Path (building the search index)

```
       Source document folder
       (PDF, DOCX, TXT, ...)
                    |
                    v
            +---------------+
            |    INDEXER     |
            +---------------+
                    |
                    v
            +---------------+
            | File scan     |
            | + validator   |
            | (skip bad)    |
            +---------------+
                    |
                    v
            +---------------+
            | Hash check    |
            | (skip files   |
            |  unchanged)   |
            +---------------+
                    |
                    v
            +---------------+
            | File parser   |
            | 24+ formats   |
            +---------------+
                    |
                    v
            +---------------+
            |   CHUNKER     |
            | 1200 chars    |
            | 200 overlap   |
            | smart split   |
            +---------------+
                    |
                    v
            +---------------+
            |   EMBEDDER    |
            | MiniLM-L6-v2  |
            | batch embed   |
            | -> 384d       |
            +---------------+
                    |
                    v
            +---------------+
            | VECTOR STORE  |
            +---------------+
               /         \
              v           v
        +---------+  +-----------+
        | SQLite  |  | Memmap    |
        | chunks  |  | vectors   |
        | meta    |  | 384d      |
        | FTS5    |  | float16   |
        | hashes  |  |           |
        +---------+  +-----------+
```

---

## Storage Layer

```
  <indexed data directory>/
       |
       +-- hybridrag.sqlite3       SQLite: chunks, metadata, FTS5, file hashes
       |
       +-- embeddings.f16.dat      Memmap: float16 vectors, shape [N, 384]
       |
       +-- embeddings_meta.json    Bookkeeping: dim, count, dtype
```

---

## Security Layers

```
  +--------------------------------------------------+
  |              NETWORK GATE                        |
  |  Mode        Allowed destinations                |
  |  --------    --------------------------------    |
  |  OFFLINE     localhost:11434 (Ollama) only       |
  |  ONLINE      localhost + approved API endpoint   |
  +--------------------------------------------------+
          |
          v
  +--------------------------------------------------+
  |          CREDENTIAL MANAGER                      |
  |  Priority    Source                               |
  |  --------    --------------------------------    |
  |  1st         Windows Credential Manager (DPAPI)  |
  |  2nd         Environment variables               |
  |  3rd         Config file (not recommended)       |
  +--------------------------------------------------+
          |
          v
  +--------------------------------------------------+
  |          EMBEDDING LOCKDOWN                      |
  |  HF_HUB_OFFLINE=1 enforced at startup           |
  |  Model loaded from local cache only              |
  +--------------------------------------------------+
```

---

## User Interfaces

```
  +-------------------+   +-------------------+   +-------------------+
  |    PowerShell     |   |       GUI         |   |     REST API      |
  |                   |   |                   |   |                   |
  | start_hybridrag   |   | launch_gui.ps1    |   | rag-server        |
  |                   |   |                   |   |                   |
  | rag-query "..."   |   | tkinter window    |   | localhost:8000    |
  | rag-index         |   | dark/light theme  |   | /query            |
  | rag-status        |   | mode toggle       |   | /index, /health   |
  +-------------------+   +-------------------+   +-------------------+
           \                       |                       /
            +----------+-----------+----------+-----------+
                       |
                       v
                QUERY ENGINE
                (same pipeline)
```
