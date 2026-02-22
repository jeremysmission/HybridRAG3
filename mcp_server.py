# ============================================================================
# HybridRAG3 -- MCP Server (mcp_server.py)
# ============================================================================
#
# WHAT THIS FILE DOES (plain English):
#   This file turns HybridRAG3 into an MCP "tool server" -- a background
#   process that any MCP-compatible AI client can call
#   to search your indexed documents.
#
#   Think of it like a vending machine for knowledge:
#     - The AI agent puts in a question (via MCP protocol)
#     - This server searches HybridRAG3's vector database
#     - It returns the answer, sources, and metadata
#
# WHAT IS MCP?
#   Model Context Protocol. It's a standard way for AI tools to talk to
#   external services. Instead of the AI having to know how to import
#   your Python code, it just sends a JSON message over stdio, and this
#   server handles the rest.
#
# HOW IT WORKS:
#   1. An MCP client spawns this script as a subprocess
#   2. Communication happens over stdin/stdout (called "stdio transport")
#   3. The client sends tool calls like hybridrag_search(query="...")
#   4. This server runs the HybridRAG3 pipeline and returns results
#   5. The client gets structured data back (answer, sources, scores)
#
# THREE TOOLS EXPOSED:
#   hybridrag_search   -- Search the knowledge base and get an answer
#   hybridrag_status   -- Check what mode/model is active
#   hybridrag_index_status -- How many documents are indexed
#
# REQUIREMENTS:
#   pip install mcp
#   HybridRAG3 must be importable (this file lives in the project root)
#
# LAUNCH:
#   python mcp_server.py          (stdio mode, for MCP clients)
#   Not meant to be run directly -- MCP clients spawn it automatically.
#
# ============================================================================

import os
import sys
import json
import logging
from typing import Optional

# -- Make sure HybridRAG3 is importable from this script's location --
# This file lives at D:\HybridRAG3\mcp_server.py, so we add the parent
# directory to Python's import path so "from src.core..." works.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# -- MCP SDK import --
from mcp.server.fastmcp import FastMCP

# -- Logging goes to stderr so it doesn't interfere with MCP's stdio --
# MCP uses stdout for protocol messages, so all our debug output goes
# to stderr where it won't corrupt the JSON stream.
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("hybridrag_mcp")


# ============================================================================
# LAZY INITIALIZATION
# ============================================================================
# We don't boot HybridRAG3 at import time because:
#   1. The MCP client might just be checking what tools are available
#   2. Booting loads the embedding model (~100MB RAM) which takes seconds
#   3. If boot fails, we want clean error messages, not import crashes
#
# Instead, we boot on the first actual tool call and cache the result.
# This pattern is called "lazy singleton".
# ============================================================================

_engine = None          # QueryEngine instance (initialized on first use)
_config = None          # Config object (initialized on first use)
_vector_store = None    # VectorStore instance (for stats)
_llm_router = None      # LLMRouter instance (for status)
_boot_error = None      # If boot failed, this holds the error message


def _ensure_booted():
    """
    Boot HybridRAG3 if it hasn't been booted yet.

    This function is called before every tool invocation. On the first
    call it runs the full boot pipeline (load config, connect to database,
    load embedding model, check Ollama). On subsequent calls it returns
    immediately because everything is already cached.

    If boot fails, the error is cached so we don't retry every call --
    we just return the stored error message.
    """
    global _engine, _config, _vector_store, _llm_router, _boot_error

    # Already booted successfully -- nothing to do
    if _engine is not None:
        return

    # Already tried and failed -- don't retry
    if _boot_error is not None:
        return

    logger.info("First tool call -- booting HybridRAG3...")

    try:
        # Step 1: Load configuration from config/default_config.yaml
        from src.core.config import load_config, Config
        config_obj = load_config(
            project_dir=SCRIPT_DIR,
            config_filename="default_config.yaml",
        )
        _config = config_obj

        # Step 2: Connect to the vector store (SQLite + memmap embeddings)
        from src.core.vector_store import VectorStore
        db_path = config_obj.paths.database
        embedding_dim = config_obj.embedding.dimension
        store = VectorStore(db_path=db_path, embedding_dim=embedding_dim)
        store.connect()
        _vector_store = store

        # Step 3: Load the embedding model (all-MiniLM-L6-v2, ~100MB)
        from src.core.embedder import Embedder
        embedder = Embedder(model_name=config_obj.embedding.model_name)

        # Step 4: Create the LLM router (handles Ollama + API switching)
        from src.core.llm_router import LLMRouter
        router = LLMRouter(config_obj)
        _llm_router = router

        # Step 5: Create the query engine (the main pipeline)
        from src.core.query_engine import QueryEngine
        _engine = QueryEngine(config_obj, store, embedder, router)

        logger.info("HybridRAG3 booted successfully")

    except Exception as e:
        _boot_error = f"{type(e).__name__}: {str(e)}"
        logger.error("HybridRAG3 boot failed: %s", _boot_error)


# ============================================================================
# MCP SERVER DEFINITION
# ============================================================================
# FastMCP handles all the protocol plumbing:
#   - Parsing incoming JSON-RPC messages from stdin
#   - Routing tool calls to the right Python function
#   - Serializing return values back as JSON-RPC responses to stdout
#   - Handling errors gracefully
# ============================================================================

mcp = FastMCP(
    name="hybridrag",
    # Description shown to AI clients so they know what this server does
    instructions=(
        "HybridRAG3 document search server. "
        "Search indexed technical documents, get AI-generated answers "
        "grounded in source material, and check system status."
    ),
)


# ============================================================================
# TOOL 1: hybridrag_search
# ============================================================================
# This is the main tool. An AI agent calls this to ask a question and
# get an answer backed by real documents from the knowledge base.
#
# Under the hood it runs the full HybridRAG3 pipeline:
#   1. Embed the query using all-MiniLM-L6-v2
#   2. Search the vector database for relevant chunks
#   3. Build context from the top-k chunks
#   4. Send context + question to the LLM (Ollama or API)
#   5. Return the answer with source citations
# ============================================================================

@mcp.tool()
def hybridrag_search(
    query: str,
    use_case: str = "gen",
    top_k: int = 12,
) -> str:
    """
    Search the HybridRAG3 knowledge base and return an AI-generated answer.

    Args:
        query: The question to search for (e.g., "What is the operating frequency?")
        use_case: Which profile to use for scoring. One of: sw, eng, pm, sys, log, draft, fe, cyber, gen. Default: gen.
        top_k: How many document chunks to retrieve. Higher = more context but slower. Default: 12.

    Returns:
        JSON string with answer, sources, chunk count, latency, and mode.
    """
    _ensure_booted()

    # If boot failed, return the error instead of crashing
    if _boot_error:
        return json.dumps({
            "error": f"HybridRAG3 failed to boot: {_boot_error}",
            "answer": "",
            "sources": [],
        })

    try:
        # Override top_k in the config if the caller specified a different value.
        # This lets agents request more or fewer chunks without changing the
        # config file on disk.
        if _config and hasattr(_config, "retrieval"):
            _config.retrieval.top_k = top_k

        # Run the full query pipeline
        result = _engine.query(query)

        # Package the result as a clean JSON object.
        # We include everything an agent might need to cite sources or
        # assess confidence.
        return json.dumps({
            "answer": result.answer,
            "sources": result.sources,
            "chunks_used": result.chunks_used,
            "tokens_in": result.tokens_in,
            "tokens_out": result.tokens_out,
            "cost_usd": result.cost_usd,
            "latency_ms": round(result.latency_ms, 1),
            "mode": result.mode,
            "use_case": use_case,
            "error": result.error or "",
        })

    except Exception as e:
        logger.error("hybridrag_search failed: %s", e)
        return json.dumps({
            "error": f"{type(e).__name__}: {str(e)}",
            "answer": "",
            "sources": [],
        })


# ============================================================================
# TOOL 2: hybridrag_status
# ============================================================================
# Quick health check. Agents can call this to see if HybridRAG3 is
# running, what mode it's in (online vs offline), and what model is active.
# ============================================================================

@mcp.tool()
def hybridrag_status() -> str:
    """
    Return current HybridRAG3 system status.

    Returns:
        JSON string with mode (online/offline), model info, and gate state.
    """
    _ensure_booted()

    if _boot_error:
        return json.dumps({
            "status": "error",
            "error": _boot_error,
        })

    try:
        status = {
            "status": "running",
            "mode": _config.mode if _config else "unknown",
        }

        # Get LLM router status (which model, which provider)
        if _llm_router:
            router_status = _llm_router.get_status()
            status["llm"] = router_status

        # Get network gate state (what network access is allowed)
        try:
            from src.core.network_gate import get_gate
            gate = get_gate()
            status["gate"] = gate.status_report()
        except Exception:
            status["gate"] = "unknown"

        return json.dumps(status)

    except Exception as e:
        logger.error("hybridrag_status failed: %s", e)
        return json.dumps({
            "status": "error",
            "error": str(e),
        })


# ============================================================================
# TOOL 3: hybridrag_index_status
# ============================================================================
# Tells you how much data is indexed. Useful for agents to check whether
# the knowledge base has been populated before trying to search it.
# ============================================================================

@mcp.tool()
def hybridrag_index_status() -> str:
    """
    Return information about the indexed document collection.

    Returns:
        JSON string with chunk count, source file count, embedding dimensions,
        and the source folder path.
    """
    _ensure_booted()

    if _boot_error:
        return json.dumps({
            "status": "error",
            "error": _boot_error,
        })

    try:
        stats = {}

        # Get vector store statistics (chunk count, source count, etc.)
        if _vector_store:
            store_stats = _vector_store.get_stats()
            stats["chunk_count"] = store_stats.get("chunk_count", 0)
            stats["source_count"] = store_stats.get("source_count", 0)
            stats["embedding_count"] = store_stats.get("embedding_count", 0)
            stats["embedding_dim"] = store_stats.get("embedding_dim", 0)

        # Include the source folder path so agents know where docs come from
        if _config and hasattr(_config, "paths"):
            source_folder = getattr(_config.paths, "source_folder", "")
            stats["source_folder"] = source_folder

            # Check if the database file exists and get its size
            db_path = getattr(_config.paths, "database", "")
            if db_path and os.path.isfile(db_path):
                db_size_mb = os.path.getsize(db_path) / (1024 * 1024)
                stats["database_size_mb"] = round(db_size_mb, 1)

        return json.dumps(stats)

    except Exception as e:
        logger.error("hybridrag_index_status failed: %s", e)
        return json.dumps({
            "status": "error",
            "error": str(e),
        })


# ============================================================================
# ENTRY POINT
# ============================================================================
# When an MCP client spawns this script, it connects
# via stdio: the client writes JSON-RPC messages to this process's stdin,
# and reads responses from stdout.
#
# The FastMCP framework handles all the protocol details. We just need
# to call mcp.run() and it takes care of the rest.
# ============================================================================

if __name__ == "__main__":
    logger.info("Starting HybridRAG3 MCP server (stdio transport)...")
    mcp.run(transport="stdio")
