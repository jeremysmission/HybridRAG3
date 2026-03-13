from __future__ import annotations

import copy
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .access_tags import normalize_access_tags
from .generation_params import snapshot_backend_generation_settings
from .query_mode import resolve_query_mode_settings
from .request_access import get_request_access_context


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _truncate_text(value: Any, limit: int = 1600) -> tuple[str, bool]:
    text = str(value or "")
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _basename(path: str) -> str:
    raw = str(path or "").replace("\\", "/").rstrip("/")
    return raw.rsplit("/", 1)[-1] if raw else ""


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
        source_path = str(_hit_value(hit, "source_path", "") or "")
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
            suspicious_sources.append({"source_path": source_path, "flags": flags})

    return {
        "expected_source_root": expected_source_root,
        "suspicious_count": len(suspicious_sources),
        "suspicious_sources": suspicious_sources,
    }


def _hit_value(hit: Any, key: str, default: Any = None) -> Any:
    if isinstance(hit, dict):
        return hit.get(key, default)
    return getattr(hit, key, default)


def hit_to_debug_dict(
    hit: Any,
    rank: int,
    *,
    stage: str,
    reason: str = "",
) -> dict[str, Any]:
    source_path = str(_hit_value(hit, "source_path", "") or "")
    text, truncated = _truncate_text(_hit_value(hit, "text", ""))
    return {
        "rank": rank,
        "stage": stage,
        "reason": reason,
        "score": round(_safe_float(_hit_value(hit, "score", 0.0)), 4),
        "source_file": _basename(source_path),
        "source_path": source_path,
        "chunk_index": _safe_int(_hit_value(hit, "chunk_index", -1), -1),
        "access_tags": list(normalize_access_tags(_hit_value(hit, "access_tags", ()))),
        "access_tag_source": str(_hit_value(hit, "access_tag_source", "") or ""),
        "text": text,
        "text_chars": len(str(_hit_value(hit, "text", "") or "")),
        "text_truncated": truncated,
    }


def _empty_access_control_trace() -> dict[str, Any]:
    return {
        "enabled": False,
        "actor": "",
        "actor_source": "",
        "actor_role": "",
        "allowed_doc_tags": [],
        "document_policy_source": "",
        "authorized_hits": 0,
        "denied_hits": 0,
    }


def minimal_retrieval_trace(hits: list[Any]) -> dict[str, Any]:
    return {
        "counts": {
            "raw_hits": len(hits),
            "post_rerank_hits": len(hits),
            "post_filter_hits": len(hits),
            "post_augment_hits": len(hits),
            "final_hits": len(hits),
            "dropped_hits": 0,
            "denied_hits": 0,
        },
        "hits": {
            "raw": [hit_to_debug_dict(hit, idx + 1, stage="raw") for idx, hit in enumerate(hits)],
            "post_rerank": [hit_to_debug_dict(hit, idx + 1, stage="post_rerank") for idx, hit in enumerate(hits)],
            "post_filter": [hit_to_debug_dict(hit, idx + 1, stage="post_filter") for idx, hit in enumerate(hits)],
            "post_augment": [hit_to_debug_dict(hit, idx + 1, stage="post_augment") for idx, hit in enumerate(hits)],
            "final": [hit_to_debug_dict(hit, idx + 1, stage="final") for idx, hit in enumerate(hits)],
            "dropped": [],
            "denied": [],
        },
        "source_path_flags": {"expected_source_root": "", "suspicious_count": 0, "suspicious_sources": []},
        "access_control": _empty_access_control_trace(),
    }


def build_retrieval_trace(
    retriever,
    *,
    query: str,
    raw_hits: list[Any],
    post_rerank_hits: list[Any],
    post_filter_hits: list[Any],
    post_augment_hits: list[Any],
    final_hits: list[Any],
    dropped_hits: list[dict[str, Any]],
    denied_hits: list[dict[str, Any]],
    structured_query: bool,
    fts_query: str,
    candidate_k: int,
    min_score_applied: float,
    timings_ms: dict[str, float],
    expected_source_root: str,
    access_control: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "query": str(query or ""),
        "structured_query": bool(structured_query),
        "fts_query": str(fts_query or ""),
        "candidate_k": int(candidate_k),
        "min_score_applied": float(min_score_applied),
        "retrieval_settings": {
            "top_k": int(getattr(retriever, "top_k", 0) or 0),
            "offline_top_k": getattr(retriever, "offline_top_k", None),
            "min_score": float(getattr(retriever, "min_score", 0.0) or 0.0),
            "hybrid_search": bool(getattr(retriever, "hybrid_search", False)),
            "reranker_enabled": bool(getattr(retriever, "reranker_enabled", False)),
            "reranker_top_n": int(getattr(retriever, "reranker_top_n", 0) or 0),
            "rrf_k": int(getattr(retriever, "rrf_k", 0) or 0),
            "block_rows": int(getattr(retriever, "block_rows", 0) or 0),
        },
        "counts": {
            "raw_hits": len(raw_hits),
            "post_rerank_hits": len(post_rerank_hits),
            "post_filter_hits": len(post_filter_hits),
            "post_augment_hits": len(post_augment_hits),
            "final_hits": len(final_hits),
            "dropped_hits": len(dropped_hits),
            "denied_hits": len(denied_hits),
        },
        "timings_ms": {
            key: round(_safe_float(value), 2)
            for key, value in (timings_ms or {}).items()
        },
        "source_path_flags": _flag_source_paths(post_augment_hits, expected_source_root),
        "hits": {
            "raw": [hit_to_debug_dict(hit, idx + 1, stage="raw") for idx, hit in enumerate(raw_hits)],
            "post_rerank": [
                hit_to_debug_dict(hit, idx + 1, stage="post_rerank")
                for idx, hit in enumerate(post_rerank_hits)
            ],
            "post_filter": [
                hit_to_debug_dict(hit, idx + 1, stage="post_filter")
                for idx, hit in enumerate(post_filter_hits)
            ],
            "post_augment": [
                hit_to_debug_dict(hit, idx + 1, stage="post_augment")
                for idx, hit in enumerate(post_augment_hits)
            ],
            "final": [hit_to_debug_dict(hit, idx + 1, stage="final") for idx, hit in enumerate(final_hits)],
            "dropped": copy.deepcopy(dropped_hits),
            "denied": copy.deepcopy(denied_hits),
        },
        "access_control": copy.deepcopy(access_control or _empty_access_control_trace()),
    }


def _query_trace_history_limit(engine: Any) -> int:
    limit = _safe_int(getattr(engine, "query_trace_history_limit", 20), 20)
    return max(1, limit)


def record_query_trace(engine, payload: dict[str, Any]) -> dict[str, Any]:
    snapshot = copy.deepcopy(payload or {})
    engine.last_query_trace = snapshot

    history = getattr(engine, "recent_query_traces", None)
    if history is None:
        history = []
    elif not isinstance(history, list):
        history = list(history)

    history.append(copy.deepcopy(snapshot))
    limit = _query_trace_history_limit(engine)
    if len(history) > limit:
        history = history[-limit:]
    engine.recent_query_traces = history
    return snapshot


def new_query_trace(engine, user_query: str, *, stream: bool, engine_kind: str) -> dict[str, Any]:
    cfg = engine.config
    mode = str(getattr(cfg, "mode", "offline") or "offline").strip().lower()
    backend_name = "api" if mode == "online" else "ollama"
    backend_cfg = getattr(cfg, backend_name, None)
    retrieval_cfg = getattr(cfg, "retrieval", None)
    paths_cfg = getattr(cfg, "paths", None)
    access_context = get_request_access_context()

    return {
        "trace_id": uuid4().hex,
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "query": str(user_query or ""),
        "mode": mode,
        "active_profile": str(getattr(cfg, "active_profile", "") or ""),
        "engine_kind": engine_kind,
        "stream": bool(stream),
        "paths": {
            "source_folder": str(getattr(paths_cfg, "source_folder", "") or ""),
            "database": str(getattr(paths_cfg, "database", "") or ""),
            "embeddings_cache": str(getattr(paths_cfg, "embeddings_cache", "") or ""),
        },
        "settings": {
            "retrieval": {
                "top_k": int(getattr(retrieval_cfg, "top_k", 0) or 0) if retrieval_cfg else 0,
                "min_score": float(getattr(retrieval_cfg, "min_score", 0.0) or 0.0) if retrieval_cfg else 0.0,
                "hybrid_search": bool(
                    getattr(retrieval_cfg, "hybrid_search", getattr(retrieval_cfg, "hybrid", False))
                ) if retrieval_cfg else False,
                "reranker_enabled": bool(
                    getattr(retrieval_cfg, "reranker_enabled", getattr(retrieval_cfg, "reranker", False))
                ) if retrieval_cfg else False,
                "reranker_top_n": int(getattr(retrieval_cfg, "reranker_top_n", 0) or 0) if retrieval_cfg else 0,
            },
            "query": resolve_query_mode_settings(cfg),
            "backend": {
                "name": backend_name,
                "model": str(getattr(backend_cfg, "model", "") or ""),
                "deployment": str(getattr(backend_cfg, "deployment", "") or ""),
                "endpoint": str(getattr(backend_cfg, "endpoint", "") or ""),
                "base_url": str(getattr(backend_cfg, "base_url", "") or ""),
                "api_version": str(getattr(backend_cfg, "api_version", "") or ""),
                **snapshot_backend_generation_settings(backend_cfg),
            },
        },
        "access": {
            "enabled": bool(access_context),
            "actor": str(access_context.get("actor", "") or ""),
            "actor_source": str(access_context.get("actor_source", "") or ""),
            "actor_role": str(access_context.get("actor_role", "") or ""),
            "allowed_doc_tags": list(access_context.get("allowed_doc_tags", ()) or ()),
            "document_policy_source": str(
                access_context.get("document_policy_source", "") or ""
            ),
        },
        "retrieval": {},
        "context": {},
        "prompt": {},
        "llm": {},
        "decision": {},
        "result": {},
        "grounding": {},
    }


def attach_result_trace(
    engine,
    result,
    trace: dict[str, Any],
    *,
    decision_path: str,
    retrieval_trace: dict[str, Any] | None = None,
    context_before_trim: str = "",
    context_after_trim: str = "",
    prompt_builder: str = "",
    prompt_preview: str = "",
    llm_response: Any = None,
    llm_stream_error: str = "",
    sources: list[dict[str, Any]] | None = None,
    grounding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = copy.deepcopy(trace or {})
    payload["retrieval"] = copy.deepcopy(
        retrieval_trace if retrieval_trace is not None else minimal_retrieval_trace([])
    )
    payload["context"] = {
        "chars_before_trim": len(context_before_trim or ""),
        "chars_after_trim": len(context_after_trim or ""),
        "trimmed": bool(context_before_trim and context_after_trim and len(context_after_trim) < len(context_before_trim)),
        "sources": copy.deepcopy(sources or getattr(result, "sources", []) or []),
    }
    payload["prompt"] = {
        "builder": str(prompt_builder or ""),
        "preview": str(prompt_preview or "")[:800],
    }
    payload["llm"] = {
        "model": str(getattr(llm_response, "model", "") or ""),
        "tokens_in": _safe_int(getattr(llm_response, "tokens_in", getattr(result, "tokens_in", 0)), 0),
        "tokens_out": _safe_int(getattr(llm_response, "tokens_out", getattr(result, "tokens_out", 0)), 0),
        "latency_ms": round(
            _safe_float(getattr(llm_response, "latency_ms", 0.0) or 0.0), 2
        ),
        "stream_error": str(llm_stream_error or ""),
        "router_last_error": str(getattr(getattr(engine, "llm_router", None), "last_error", "") or ""),
    }
    payload["decision"] = {
        "path": str(decision_path or ""),
        "error": str(getattr(result, "error", "") or ""),
    }
    payload["result"] = {
        "answer_preview": str(getattr(result, "answer", "") or "")[:800],
        "error": str(getattr(result, "error", "") or ""),
        "chunks_used": _safe_int(getattr(result, "chunks_used", 0), 0),
        "tokens_in": _safe_int(getattr(result, "tokens_in", 0), 0),
        "tokens_out": _safe_int(getattr(result, "tokens_out", 0), 0),
        "cost_usd": round(_safe_float(getattr(result, "cost_usd", 0.0), 0.0), 6),
        "latency_ms": round(_safe_float(getattr(result, "latency_ms", 0.0), 0.0), 2),
        "mode": str(getattr(result, "mode", "") or ""),
    }
    payload["grounding"] = copy.deepcopy(grounding or {})

    recorded = record_query_trace(engine, payload)
    result.debug_trace = copy.deepcopy(recorded)
    return recorded


def format_query_trace_text(trace: dict[str, Any] | None) -> str:
    if not trace:
        return "No query trace captured yet."

    retrieval = trace.get("retrieval", {})
    counts = retrieval.get("counts", {})
    settings = trace.get("settings", {})
    backend = settings.get("backend", {})
    query_settings = settings.get("query", {})
    decision = trace.get("decision", {})
    access = trace.get("access", {})
    access_control = retrieval.get("access_control", {})
    lines = [
        "Latest Query Trace",
        "==================",
        "Query: {}".format(trace.get("query", "")),
        "Mode: {} | Profile: {} | Engine: {} | Stream: {}".format(
            trace.get("mode", ""),
            trace.get("active_profile", "(base)") or "(base)",
            trace.get("engine_kind", ""),
            trace.get("stream", False),
        ),
        "Decision: {}".format(decision.get("path", "")),
        "",
        "Paths",
        "-----",
        "Source: {}".format(trace.get("paths", {}).get("source_folder", "")),
        "Index DB: {}".format(trace.get("paths", {}).get("database", "")),
        "",
        "Backend",
        "-------",
        "Backend: {} | Model: {} | Deployment: {}".format(
            backend.get("name", ""),
            backend.get("model", ""),
            backend.get("deployment", ""),
        ),
        "Context window: {} | Max tokens: {} | Num predict: {} | Temperature: {}".format(
            backend.get("context_window", 0),
            backend.get("max_tokens", 0),
            backend.get("num_predict", 0),
            backend.get("temperature", 0.0),
        ),
        "Top p: {} | Seed: {} | Presence penalty: {} | Frequency penalty: {}".format(
            backend.get("top_p", 0.0),
            backend.get("seed", 0),
            backend.get("presence_penalty", 0.0),
            backend.get("frequency_penalty", 0.0),
        ),
        "",
        "Query Policy",
        "------------",
        "Grounding bias: {} | Open knowledge: {} | Guard enabled: {}".format(
            query_settings.get("grounding_bias", ""),
            query_settings.get("allow_open_knowledge", ""),
            query_settings.get("guard_enabled", ""),
        ),
        "Guard threshold: {} | Min chunks: {} | Min score: {} | Action: {}".format(
            query_settings.get("guard_threshold", ""),
            query_settings.get("guard_min_chunks", ""),
            query_settings.get("guard_min_score", ""),
            query_settings.get("guard_action", ""),
        ),
        "",
        "Access",
        "------",
        "Enabled: {} | Actor: {} | Source: {} | Role: {}".format(
            access.get("enabled", False),
            access.get("actor", ""),
            access.get("actor_source", ""),
            access.get("actor_role", ""),
        ),
        "Allowed tags: {}".format(", ".join(access.get("allowed_doc_tags", []) or []) or "(unrestricted)"),
        "Policy source: {}".format(access.get("document_policy_source", "") or "(none)"),
        "",
        "Retrieval Counts",
        "----------------",
        "raw={} rerank={} filter={} augment={} final={} dropped={} denied={}".format(
            counts.get("raw_hits", 0),
            counts.get("post_rerank_hits", 0),
            counts.get("post_filter_hits", 0),
            counts.get("post_augment_hits", 0),
            counts.get("final_hits", 0),
            counts.get("dropped_hits", 0),
            counts.get("denied_hits", 0),
        ),
        "Access filter: enabled={} policy={} authorized={} denied={}".format(
            access_control.get("enabled", False),
            access_control.get("document_policy_source", "") or "(none)",
            access_control.get("authorized_hits", 0),
            access_control.get("denied_hits", 0),
        ),
    ]

    final_hits = retrieval.get("hits", {}).get("final", [])
    if final_hits:
        lines.extend(["", "Final Hits", "----------"])
        for hit in final_hits:
            lines.extend(
                [
                    "[{rank}] score={score} | {file} | chunk {chunk}".format(
                        rank=hit.get("rank", "?"),
                        score=hit.get("score", 0.0),
                        file=hit.get("source_file", "(unknown)"),
                        chunk=hit.get("chunk_index", -1),
                    ),
                    hit.get("source_path", ""),
                    hit.get("text", ""),
                    "",
                ]
            )

    dropped_hits = retrieval.get("hits", {}).get("dropped", [])
    if dropped_hits:
        lines.extend(["Dropped Hits", "------------"])
        for hit in dropped_hits[:12]:
            lines.append(
                "[{stage}] {reason} | score={score} | {file} | chunk {chunk}".format(
                    stage=hit.get("stage", "drop"),
                    reason=hit.get("reason", ""),
                    score=hit.get("score", 0.0),
                    file=hit.get("source_file", "(unknown)"),
                    chunk=hit.get("chunk_index", -1),
                )
            )
        if len(dropped_hits) > 12:
            lines.append("... {} more dropped hits".format(len(dropped_hits) - 12))

    denied_hits = retrieval.get("hits", {}).get("denied", [])
    if denied_hits:
        lines.extend(["Denied Hits", "-----------"])
        for hit in denied_hits[:12]:
            lines.append(
                "[{stage}] {reason} | score={score} | {file} | chunk {chunk}".format(
                    stage=hit.get("stage", "deny"),
                    reason=hit.get("reason", ""),
                    score=hit.get("score", 0.0),
                    file=hit.get("source_file", "(unknown)"),
                    chunk=hit.get("chunk_index", -1),
                )
            )
        if len(denied_hits) > 12:
            lines.append("... {} more denied hits".format(len(denied_hits) - 12))

    context = trace.get("context", {})
    lines.extend(
        [
            "",
            "Context",
            "-------",
            "chars before trim={} | after trim={} | trimmed={}".format(
                context.get("chars_before_trim", 0),
                context.get("chars_after_trim", 0),
                context.get("trimmed", False),
            ),
            "",
            "LLM",
            "---",
            "model={} | tokens_in={} | tokens_out={} | latency_ms={}".format(
                trace.get("llm", {}).get("model", ""),
                trace.get("llm", {}).get("tokens_in", 0),
                trace.get("llm", {}).get("tokens_out", 0),
                trace.get("llm", {}).get("latency_ms", 0.0),
            ),
            "result latency_ms={} | cost_usd={} | error={}".format(
                trace.get("result", {}).get("latency_ms", 0.0),
                trace.get("result", {}).get("cost_usd", 0.0),
                trace.get("result", {}).get("error", ""),
            ),
        ]
    )

    grounding = trace.get("grounding", {})
    if grounding:
        lines.extend(
            [
                "",
                "Grounding",
                "---------",
                "score={} | safe={} | blocked={}".format(
                    grounding.get("score", ""),
                    grounding.get("safe", ""),
                    grounding.get("blocked", ""),
                ),
            ]
        )

    suspicious = retrieval.get("source_path_flags", {}).get("suspicious_sources", [])
    if suspicious:
        lines.extend(["", "Source Path Flags", "-----------------"])
        for item in suspicious:
            lines.append(
                "{} :: {}".format(
                    item.get("source_path", ""),
                    ", ".join(item.get("flags", [])),
                )
            )

    return "\n".join(lines).strip() + "\n"
