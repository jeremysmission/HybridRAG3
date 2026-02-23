# HybridRAG3 Codebase Size Breakdown

**Generated: 2026-02-22** | 207 Python files | 74,958 total lines

## Lines of Code by Functional Area

| Function | Files | Code | Commentary | Total | Doc% |
|----------|------:|-----:|-----------:|------:|-----:|
| **Test Suite** | 40 | 15,236 | 4,479 | 23,718 | 22.7% |
| **GUI Application** | 19 | 4,859 | 1,310 | 7,201 | 21.2% |
| **Bulk Transfer & Tools** | 15 | 3,306 | 1,736 | 5,792 | 34.4% |
| **Sync & Work Validation** | 26 | 3,086 | 1,031 | 4,754 | 25.0% |
| **Diagnostics & IBIT** | 11 | 2,376 | 758 | 3,547 | 24.2% |
| **File Parsers** | 28 | 1,928 | 1,462 | 3,987 | 43.1% |
| **Core RAG Pipeline** | 8 | 1,820 | 1,797 | 4,164 | 49.7% |
| **Hallucination Guard** | 12 | 1,629 | 1,136 | 3,185 | 41.1% |
| **Scripts & Model Mgmt** | 10 | 1,454 | 739 | 2,590 | 33.7% |
| **API & HTTP** | 6 | 1,261 | 756 | 2,392 | 37.5% |
| **Config & Boot** | 5 | 1,257 | 1,004 | 2,648 | 44.4% |
| **Monitoring & Logging** | 3 | 361 | 187 | 639 | 34.1% |
| **Cost Tracking** | 1 | 277 | 220 | 562 | 44.3% |
| **File Validation** | 1 | 92 | 91 | 217 | 49.7% |
| **Other (root files)** | 22 | 3,356 | 4,850 | 9,562 | 59.1% |
| **TOTAL** | **207** | **42,298** | **21,556** | **74,958** | **33.8%** |

## Totals

- **Code (executable):** 42,298 lines
- **Commentary (comments + docstrings):** 21,556 lines
- **Blank lines:** 11,104
- **Total:** 74,958 lines
- **Documentation ratio:** 33.8% of non-blank lines

## Comparison to Open-Source RAG Projects

| Project | Type | Python LOC | Notes |
|---------|------|--------:|-------|
| simple-local-rag | Tutorial | ~500 | Single notebook, online-only |
| PrivateGPT | Offline-first | 5,006 | LlamaIndex wrapper, local LLMs |
| Quivr | Online SaaS | 6,102 | Cloud-hosted, API-focused |
| Kotaemon | Hybrid (offline+online) | 25,773 | Gradio UI, multi-model |
| **HybridRAG3** | **Hybrid (offline+online+dual)** | **42,298** | Tkinter GUI, 15 parsers, IBIT, hallucination guard, cost tracker, bulk transfer, eval suite |
| Haystack | Framework | 100,517 | Library, not an application |
| RAGFlow | Enterprise platform | 123,983 | Full SaaS with React frontend |

Source data from GitHub via CodeTabs API (codetabs.com), February 2026.

## Observations

- **Core RAG Pipeline** and **File Validation** hit nearly 50% documentation ratio -- the best-documented areas in the codebase.
- **Tests** are the largest category by far (15K code lines, 36% of all code). That is a healthy ratio for a production system.
- **GUI** at 4,859 code lines is substantial for a Tkinter app (most Tkinter apps are 1-2K).
- **Hallucination Guard** alone (1,629 code lines) is larger than some entire RAG projects like PrivateGPT (5K total).
- The "Other / Root" bucket (22 files, 3,356 code) has high Doc% because it includes Eval files and heavily-commented root scripts.
- A "typical" hybrid offline/online RAG app with a GUI is roughly 15,000-30,000 Python lines. HybridRAG3 is about 1.5-2x that because it is self-contained (no LlamaIndex/LangChain dependency) and includes operational tooling (transfer, diagnostics, eval) that most RAG apps leave to external tools.

## Category Definitions

- **Core RAG Pipeline:** query_engine, grounded_query_engine, retriever, embedder, vector_store, chunker, chunk_ids, llm_router
- **Config & Boot:** config, boot, feature_registry, exceptions, network_gate
- **API & HTTP:** http_client, api_client_factory, FastAPI server/routes/models, MCP server
- **Hallucination Guard:** claim_extractor, nli_verifier, response_scoring, prompt_hardener, golden_probes, startup_bit, dual_path, guard_types, self_test
- **File Parsers:** 28 parsers in src/parsers/ (PDF, DOCX, XLSX, PPTX, images, plain text, etc.)
- **GUI Application:** Tkinter app, panels (query, reference, settings, cost dashboard, API admin, setup wizard, tuning), theme, widgets
- **Diagnostics & IBIT:** health_tests, component_tests, perf_benchmarks, fault_analysis, system_diagnostic, guard_diagnostic, IBIT checks
- **Monitoring & Logging:** logger, run_tracker
- **Cost Tracking:** SQLite-backed cost event recorder with listener pattern
- **File Validation:** Pre-flight and post-parse file integrity checks
- **Bulk Transfer & Tools:** bulk_transfer_v2, scan_source_files, transfer_manifest, transfer_staging, run_index_once, scheduled_scan
- **Scripts & Model Mgmt:** _set_model, _model_meta, _list_models, _check_creds, _profile_status, _set_offline, _set_online, _test_api, _profile_switch
- **Sync & Work Validation:** sync_to_educational, build_wheels_bundle, check_dependencies, validate_offline_models, validate_online_api
- **Test Suite:** 40 test files including virtual_test_framework, conftest, and all pytest modules
