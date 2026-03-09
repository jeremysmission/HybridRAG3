#!/usr/bin/env python3
# === NON-PROGRAMMER GUIDE ===
# Purpose: Automates the query-path probe workflow for developers or operators.
# What to read first: Start at main(), then _run_mode_query_probe().
# Inputs: Config filename, mode(s), and one or more query strings.
# Outputs: JSON and Markdown reports under logs/query_path_probes/<timestamp>/.
# Safety notes: Reads the live index and may call the configured LLM backend when ready.
# ============================
"""
HybridRAG query-path probe

What it does
- Runs the same query set through offline and/or online mode
- Captures retrieval counts, source chunks, context trimming, and prompt budget
- Optionally invokes the LLM for end-to-end latency and answer behavior
- Writes a machine-readable JSON report plus a plain-English Markdown summary

Usage
  python tools/query_path_probe.py --mode both --query "What leadership styles are discussed?"
  python tools/query_path_probe.py --mode offline --query-file queries.txt
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config import load_config
from src.core.embedder import Embedder
from src.core.grounded_query_engine import GroundedQueryEngine
from src.core.llm_router import LLMRouter
from src.core.query_engine import QueryEngine
from src.core.query_engine import _qe_resolve_prompt_budget
from src.core.retriever import _is_structured_lookup_query
from src.core.vector_store import VectorStore
from src.security.credentials import resolve_credentials


DEFAULT_QUERIES = [
    "What leadership styles are discussed and how do they differ?",
    "How do the materials describe behavioral assessments such as MBTI?",
    "What are the strengths or limitations of transformational leadership?",
    "What is the difference between frequency modulation and amplitude modulation in radio communications?",
]


def _runtime_config_filename(config_arg: str | None) -> str:
    if not config_arg:
        return "config.yaml"

    raw = str(config_arg).replace("\\", "/").strip()
    if not raw:
        return "config.yaml"

    if os.path.isabs(raw):
        config_dir = (PROJECT_ROOT / "config").resolve()
        try:
            rel = Path(raw).resolve().relative_to(config_dir)
            return str(rel).replace("\\", "/")
        except ValueError as exc:
            raise SystemExit(
                "--config must point to a file inside this repo's config/ directory"
            ) from exc

    if raw.startswith("./"):
        raw = raw[2:]
    if raw.startswith("config/"):
        raw = raw[len("config/") :]
    return raw or "config.yaml"


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _json_safe_hit(hit: Any, rank: int) -> dict[str, Any]:
    text = getattr(hit, "text", "")
    return {
        "rank": rank,
        "score": round(float(getattr(hit, "score", 0.0) or 0.0), 4),
        "source_path": str(getattr(hit, "source_path", "")),
        "chunk_index": int(getattr(hit, "chunk_index", -1) or -1),
        "preview": str(text).replace("\r", " ").replace("\n", " ")[:240],
    }


def _normalize_path(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        return str(Path(raw).resolve()).lower()
    except Exception:
        return str(Path(raw)).lower()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def _flag_source_paths(hits: list[Any], expected_source_root: str) -> dict[str, Any]:
    suspicious_sources: list[dict[str, Any]] = []
    normalized_root = _normalize_path(expected_source_root)
    root_path = Path(normalized_root) if normalized_root else None

    for hit in hits:
        source_path = str(getattr(hit, "source_path", "") or "")
        flags: list[str] = []
        normalized_source = _normalize_path(source_path)
        source_path_obj = Path(source_path) if source_path else None

        if normalized_source and "\\appdata\\local\\temp\\" in normalized_source:
            flags.append("temp_path")
        if (
            root_path is not None
            and source_path_obj is not None
            and source_path_obj.is_absolute()
            and not _is_relative_to(source_path_obj, root_path)
        ):
            flags.append("outside_expected_root")

        if flags:
            suspicious_sources.append(
                {
                    "source_path": source_path,
                    "flags": flags,
                }
            )

    return {
        "expected_source_root": expected_source_root,
        "suspicious_count": len(suspicious_sources),
        "suspicious_sources": suspicious_sources,
    }


def _prompt_budget_snapshot(engine, query: str, trimmed_context: str) -> dict[str, Any]:
    ctx_window, output_budget = _qe_resolve_prompt_budget(engine)
    prompt_overhead_tokens = 800 + (len(query) // 4) + output_budget
    max_context_tokens = max(ctx_window - prompt_overhead_tokens, 512)
    max_context_chars = max_context_tokens * 4
    return {
        "context_window": ctx_window,
        "output_budget": output_budget,
        "prompt_overhead_tokens": prompt_overhead_tokens,
        "max_context_tokens": max_context_tokens,
        "max_context_chars": max_context_chars,
        "trimmed_context_chars": len(trimmed_context),
    }


def _router_snapshot(engine, creds) -> dict[str, Any]:
    router = engine.llm_router
    cfg = engine.config
    mode = str(cfg.mode).strip().lower()

    selected_backend = "none"
    if mode == "online":
        selected_backend = "api" if getattr(router, "api", None) is not None else "none"
    else:
        if getattr(router, "vllm", None) is not None:
            selected_backend = "vllm"
        elif getattr(router, "ollama", None) is not None:
            selected_backend = "ollama"

    return {
        "mode": mode,
        "selected_backend": selected_backend,
        "ollama_model": getattr(getattr(cfg, "ollama", None), "model", ""),
        "api_model": getattr(getattr(cfg, "api", None), "model", ""),
        "api_deployment": getattr(getattr(cfg, "api", None), "deployment", ""),
        "api_has_endpoint": bool(getattr(creds, "has_endpoint", False)),
        "api_has_key": bool(getattr(creds, "has_key", False)),
        "router_has_api": getattr(router, "api", None) is not None,
        "router_api_ready": bool(
            getattr(getattr(router, "api", None), "client", None) is not None
            or getattr(getattr(router, "api", None), "http_api_client", None) is not None
        ),
        "router_has_ollama": getattr(router, "ollama", None) is not None,
        "router_has_vllm": getattr(router, "vllm", None) is not None,
    }


def _mode_readiness(engine, creds) -> dict[str, Any]:
    mode = str(engine.config.mode).strip().lower()
    ollama_ready = False
    ollama_error = ""
    ollama = getattr(engine.llm_router, "ollama", None)
    if ollama is not None and hasattr(ollama, "is_available"):
        try:
            ollama_ready = bool(ollama.is_available())
        except Exception as exc:
            ollama_error = "{}: {}".format(type(exc).__name__, exc)

    online_ready = bool(getattr(creds, "has_key", False) and getattr(creds, "has_endpoint", False))

    can_invoke = ollama_ready if mode == "offline" else online_ready
    return {
        "mode": mode,
        "ollama_ready": ollama_ready,
        "ollama_error": ollama_error,
        "online_ready": online_ready,
        "api_has_key": bool(getattr(creds, "has_key", False)),
        "api_has_endpoint": bool(getattr(creds, "has_endpoint", False)),
        "can_invoke_llm": can_invoke,
    }


def _manual_pipeline_probe(engine, query: str, expected_source_root: str) -> dict[str, Any]:
    retriever = engine.retriever
    retriever.refresh_settings()

    candidate_k = retriever.reranker_top_n if retriever.reranker_enabled else retriever.top_k
    structured_query = _is_structured_lookup_query(query)
    fts_query = query
    min_score = retriever.min_score

    if structured_query:
        candidate_k = max(candidate_k, min(retriever.top_k * 4, 48))
        fts_query = retriever._expand_structured_fts_query(query)
        min_score = max(0.05, retriever.min_score * 0.5)

    t_search = time.perf_counter()
    if retriever.hybrid_search:
        raw_hits = retriever._hybrid_search(query, candidate_k, fts_query=fts_query)
    else:
        raw_hits = retriever._vector_search(query, candidate_k)
    search_ms = (time.perf_counter() - t_search) * 1000

    hits = list(raw_hits)
    rerank_ms = 0.0
    if retriever.reranker_enabled and hits:
        t_rerank = time.perf_counter()
        hits = retriever._rerank(query, hits)
        rerank_ms = (time.perf_counter() - t_rerank) * 1000

    t_post = time.perf_counter()
    filtered_hits = [h for h in hits if h.score >= min_score]
    if structured_query:
        filtered_hits = retriever._augment_with_adjacent_chunks(filtered_hits)

    final_k = retriever.top_k
    if getattr(engine.config, "mode", "offline") == "offline" and retriever.offline_top_k is not None:
        final_k = min(final_k, retriever.offline_top_k)
    final_hits = filtered_hits[:final_k]
    post_ms = (time.perf_counter() - t_post) * 1000

    t_context = time.perf_counter()
    context = retriever.build_context(final_hits)
    sources = retriever.get_sources(final_hits)
    context_ms = (time.perf_counter() - t_context) * 1000

    t_trim = time.perf_counter()
    trimmed_context = engine._trim_context_to_fit(context, query) if context else context
    trim_ms = (time.perf_counter() - t_trim) * 1000

    prompt_builder = "base"
    prompt = ""
    if final_hits and trimmed_context:
        if getattr(engine, "guard_enabled", False) and getattr(engine, "_guard_available", False):
            prompt_builder = "grounded"
            prompt = engine._build_grounded_prompt(query, trimmed_context, final_hits)
        else:
            prompt = engine._build_prompt(query, trimmed_context)

    return {
        "retrieval_settings": {
            "top_k": retriever.top_k,
            "min_score": retriever.min_score,
            "hybrid_search": retriever.hybrid_search,
            "reranker_enabled": retriever.reranker_enabled,
            "reranker_top_n": retriever.reranker_top_n,
            "offline_top_k": retriever.offline_top_k,
        },
        "source_path_flags": _flag_source_paths(final_hits, expected_source_root),
        "structured_query": structured_query,
        "candidate_k": candidate_k,
        "min_score_applied": min_score,
        "counts": {
            "raw_hits": len(raw_hits),
            "post_rerank_hits": len(hits),
            "post_filter_hits": len(filtered_hits),
            "final_hits": len(final_hits),
        },
        "timings_ms": {
            "search": round(search_ms, 2),
            "rerank": round(rerank_ms, 2),
            "post_filter_finalize": round(post_ms, 2),
            "context_build": round(context_ms, 2),
            "trim": round(trim_ms, 2),
        },
        "budget": _prompt_budget_snapshot(engine, query, trimmed_context or ""),
        "context": {
            "chars_before_trim": len(context or ""),
            "chars_after_trim": len(trimmed_context or ""),
            "trimmed": bool(context and trimmed_context and len(trimmed_context) < len(context)),
        },
        "sources": sources,
        "hits": [_json_safe_hit(hit, idx + 1) for idx, hit in enumerate(final_hits)],
        "prompt_builder": prompt_builder,
        "prompt_preview": prompt[:600],
    }


def _run_end_to_end(engine, query: str, readiness: dict[str, Any], invoke_llm: bool) -> dict[str, Any]:
    if not invoke_llm:
        return {"attempted": False, "skipped_reason": "invoke_llm disabled"}
    if not readiness["can_invoke_llm"]:
        if readiness["mode"] == "online":
            reason = "online credentials incomplete"
        else:
            reason = readiness["ollama_error"] or "ollama unavailable"
        return {"attempted": False, "skipped_reason": reason}

    t0 = time.perf_counter()
    result = engine.query(query)
    wall_ms = (time.perf_counter() - t0) * 1000
    return {
        "attempted": True,
        "wall_ms": round(wall_ms, 2),
        "engine_latency_ms": round(float(getattr(result, "latency_ms", 0.0) or 0.0), 2),
        "answer_preview": str(getattr(result, "answer", "") or "")[:400],
        "error": getattr(result, "error", None),
        "chunks_used": int(getattr(result, "chunks_used", 0) or 0),
        "tokens_in": int(getattr(result, "tokens_in", 0) or 0),
        "tokens_out": int(getattr(result, "tokens_out", 0) or 0),
        "cost_usd": float(getattr(result, "cost_usd", 0.0) or 0.0),
        "sources": getattr(result, "sources", []),
        "grounding_score": getattr(result, "grounding_score", None),
        "grounding_blocked": getattr(result, "grounding_blocked", None),
    }


def _build_engine(mode: str, config_filename: str, args) -> dict[str, Any]:
    cfg = load_config(project_dir=".", config_filename=config_filename)
    cfg = copy.deepcopy(cfg)
    cfg.mode = mode
    if mode == "offline":
        if args.offline_model:
            cfg.ollama.model = args.offline_model
        if args.offline_num_predict:
            cfg.ollama.num_predict = int(args.offline_num_predict)
        if args.offline_context_window:
            cfg.ollama.context_window = int(args.offline_context_window)
    else:
        if args.online_max_tokens:
            cfg.api.max_tokens = int(args.online_max_tokens)
        if args.online_context_window:
            cfg.api.context_window = int(args.online_context_window)

    store = VectorStore(db_path=cfg.paths.database, embedding_dim=cfg.embedding.dimension)
    store.connect()
    embedder = Embedder(model_name=cfg.embedding.model_name)
    router = LLMRouter(cfg, api_key=None)
    if args.engine == "base":
        engine = QueryEngine(cfg, store, embedder, router)
    else:
        engine = GroundedQueryEngine(cfg, store, embedder, router)
    return {
        "config": cfg,
        "store": store,
        "embedder": embedder,
        "router": router,
        "engine": engine,
    }


def _close_engine(bundle: dict[str, Any]) -> None:
    try:
        bundle["store"].close()
    except Exception:
        pass


def _warm_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    engine = bundle["engine"]
    t0 = time.perf_counter()
    error = ""
    try:
        engine.retriever.search("leadership warmup probe")
    except Exception as exc:
        error = "{}: {}".format(type(exc).__name__, exc)
    return {
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2),
        "error": error,
    }


def _run_mode_query_probe(
    mode: str,
    query: str,
    bundle: dict[str, Any],
    creds,
    invoke_llm: bool,
) -> dict[str, Any]:
    engine = bundle["engine"]
    readiness = _mode_readiness(engine, creds)
    expected_source_root = str(
        getattr(getattr(bundle["config"], "paths", None), "source_folder", "") or ""
    )
    return {
        "mode": mode,
        "query": query,
        "router": _router_snapshot(engine, creds),
        "readiness": readiness,
        "manual_pipeline": _manual_pipeline_probe(
            engine,
            query,
            expected_source_root=expected_source_root,
        ),
        "end_to_end": _run_end_to_end(engine, query, readiness, invoke_llm),
    }


def _write_markdown_summary(out_path: Path, report: dict[str, Any]) -> None:
    lines = []
    lines.append("# Query Path Probe Summary")
    lines.append("")
    lines.append("Generated: `{}`".format(report["timestamp"]))
    lines.append("Config: `{}`".format(report["config_filename"]))
    lines.append("Engine: `{}`".format(report["engine"]))
    lines.append("")
    for query_block in report["queries"]:
        lines.append("## Query")
        lines.append("")
        lines.append(query_block["query"])
        lines.append("")
        for mode_result in query_block["modes"]:
            mode = mode_result["mode"]
            manual = mode_result["manual_pipeline"]
            end_to_end = mode_result["end_to_end"]
            lines.append("### {}".format(mode.capitalize()))
            lines.append("")
            lines.append(
                "- hits raw/post-filter/final: `{}/{}/{}`".format(
                    manual["counts"]["raw_hits"],
                    manual["counts"]["post_filter_hits"],
                    manual["counts"]["final_hits"],
                )
            )
            lines.append(
                "- context chars before/after trim: `{}/{}`".format(
                    manual["context"]["chars_before_trim"],
                    manual["context"]["chars_after_trim"],
                )
            )
            lines.append(
                "- timings ms search/context/trim: `{}/{}/{}`".format(
                    manual["timings_ms"]["search"],
                    manual["timings_ms"]["context_build"],
                    manual["timings_ms"]["trim"],
                )
            )
            lines.append(
                "- prompt budget chars: `{}`".format(
                    manual["budget"]["max_context_chars"]
                )
            )
            if manual["source_path_flags"]["suspicious_count"]:
                lines.append(
                    "- suspicious sources: `{}`".format(
                        manual["source_path_flags"]["suspicious_count"]
                    )
                )
            if end_to_end["attempted"]:
                lines.append(
                    "- end-to-end ms engine/wall: `{}/{}`".format(
                        end_to_end["engine_latency_ms"],
                        end_to_end["wall_ms"],
                    )
                )
                lines.append(
                    "- end-to-end error: `{}`".format(end_to_end["error"])
                )
            else:
                lines.append(
                    "- end-to-end skipped: `{}`".format(
                        end_to_end["skipped_reason"]
                    )
                )
            if manual["hits"]:
                lines.append("- top sources:")
                for hit in manual["hits"][:3]:
                    lines.append(
                        "  - `{}` score=`{}` chunk=`{}`".format(
                            Path(hit["source_path"]).name,
                            hit["score"],
                            hit["chunk_index"],
                        )
                    )
            lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def _load_queries(args) -> list[str]:
    queries: list[str] = []
    for query in args.query:
        q = str(query).strip()
        if q:
            queries.append(q)
    if args.query_file:
        with open(args.query_file, "r", encoding="utf-8") as fh:
            for line in fh:
                q = line.strip()
                if q:
                    queries.append(q)
    if not queries:
        queries = list(DEFAULT_QUERIES)
    return queries


def main() -> None:
    ap = argparse.ArgumentParser(description="Trace query architecture across offline/online modes.")
    ap.add_argument("--config", default="config/config.yaml", help="Config filename/path inside repo config/.")
    ap.add_argument("--engine", choices=("grounded", "base"), default="grounded", help="Use the guarded query engine or the plain core query engine.")
    ap.add_argument("--mode", choices=("offline", "online", "both"), default="both")
    ap.add_argument("--query", action="append", default=[], help="Query string to probe. Repeatable.")
    ap.add_argument("--query-file", default="", help="Optional text file with one query per line.")
    ap.add_argument("--offline-model", default="", help="Override cfg.ollama.model for probe runs.")
    ap.add_argument("--offline-num-predict", type=int, default=0, help="Override cfg.ollama.num_predict for probe runs.")
    ap.add_argument("--offline-context-window", type=int, default=0, help="Override cfg.ollama.context_window for probe runs.")
    ap.add_argument("--online-max-tokens", type=int, default=0, help="Override cfg.api.max_tokens for probe runs.")
    ap.add_argument("--online-context-window", type=int, default=0, help="Override cfg.api.context_window for probe runs.")
    ap.add_argument("--skip-llm", action="store_true", help="Capture retrieval/prompt traces without calling the LLM.")
    args = ap.parse_args()

    config_filename = _runtime_config_filename(args.config)
    queries = _load_queries(args)
    modes = ["offline", "online"] if args.mode == "both" else [args.mode]
    timestamp = _now_stamp()

    out_dir = PROJECT_ROOT / "logs" / "query_path_probes" / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

    creds = resolve_credentials(use_cache=False)
    bundles = {mode: _build_engine(mode, config_filename, args) for mode in modes}
    warmups = {mode: _warm_bundle(bundle) for mode, bundle in bundles.items()}

    report: dict[str, Any] = {
        "timestamp": timestamp,
        "config_filename": config_filename,
        "engine": args.engine,
        "modes": modes,
        "warmups": warmups,
        "queries": [],
    }
    try:
        for query in queries:
            print("")
            print("QUERY: {}".format(query))
            query_block = {"query": query, "modes": []}
            for mode in modes:
                print("  [{}] probing...".format(mode))
                mode_result = _run_mode_query_probe(
                    mode=mode,
                    query=query,
                    bundle=bundles[mode],
                    creds=creds,
                    invoke_llm=(not args.skip_llm),
                )
                query_block["modes"].append(mode_result)
                manual = mode_result["manual_pipeline"]
                end_to_end = mode_result["end_to_end"]
                print(
                    "    hits raw/post/final = {}/{}/{} | search={}ms | ctx={} -> {} chars | suspicious={}".format(
                        manual["counts"]["raw_hits"],
                        manual["counts"]["post_filter_hits"],
                        manual["counts"]["final_hits"],
                        manual["timings_ms"]["search"],
                        manual["context"]["chars_before_trim"],
                        manual["context"]["chars_after_trim"],
                        manual["source_path_flags"]["suspicious_count"],
                    )
                )
                if end_to_end["attempted"]:
                    print(
                        "    end-to-end wall={}ms engine={}ms error={}".format(
                            end_to_end["wall_ms"],
                            end_to_end["engine_latency_ms"],
                            end_to_end["error"],
                        )
                    )
                else:
                    print("    end-to-end skipped: {}".format(end_to_end["skipped_reason"]))

            report["queries"].append(query_block)
    finally:
        for bundle in bundles.values():
            _close_engine(bundle)

    json_path = out_dir / "probe_report.json"
    md_path = out_dir / "SUMMARY.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_markdown_summary(md_path, report)

    print("")
    print("Wrote:")
    print("  {}".format(json_path))
    print("  {}".format(md_path))


if __name__ == "__main__":
    main()
