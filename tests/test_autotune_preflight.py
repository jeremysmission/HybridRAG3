import importlib.util
import json
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _load_tool_module(name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_expected_source_names_uses_basenames_and_deduplicates(tmp_path):
    mod = _load_tool_module("autotune_preflight_test_expected", "tools/autotune_preflight.py")
    dataset = tmp_path / "golden.json"
    dataset.write_text(
        json.dumps(
            [
                {"expected_sources": ["Docs/Field_Deployment_Guide.docx", "PM_Risk_Register.pdf"]},
                {"expected_sources": ["Field_Deployment_Guide.docx"]},
                {"expected_sources": []},
            ]
        ),
        encoding="utf-8",
    )

    names = mod._expected_source_names(dataset)

    assert names == {"field_deployment_guide.docx", "pm_risk_register.pdf"}


def test_index_stats_reports_chunk_and_distinct_source_counts(tmp_path):
    mod = _load_tool_module("autotune_preflight_test_index", "tools/autotune_preflight.py")
    db_path = tmp_path / "hybridrag.sqlite3"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE chunks (source_path TEXT)")
        conn.executemany(
            "INSERT INTO chunks (source_path) VALUES (?)",
            [
                (str(tmp_path / "Field_Deployment_Guide.docx"),),
                (str(tmp_path / "Field_Deployment_Guide.docx"),),
                (str(tmp_path / "PM_Risk_Register.pdf"),),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    stats = mod._index_stats(db_path)

    assert stats["ok"] is True
    assert stats["chunk_count"] == 3
    assert stats["source_count"] == 2
    assert stats["basenames"] == {"field_deployment_guide.docx", "pm_risk_register.pdf"}


def test_corpus_alignment_fails_when_index_does_not_match_dataset():
    mod = _load_tool_module("autotune_preflight_test_align_fail", "tools/autotune_preflight.py")

    result = mod._corpus_alignment(
        {"field_deployment_guide.docx", "pm_risk_register.pdf"},
        {"random_work_doc.docx"},
    )

    assert result["level"] == "FAIL"
    assert result["coverage_pct"] == 0


def test_corpus_alignment_warns_on_partial_match():
    mod = _load_tool_module("autotune_preflight_test_align_warn", "tools/autotune_preflight.py")

    result = mod._corpus_alignment(
        {"field_deployment_guide.docx", "pm_risk_register.pdf"},
        {"field_deployment_guide.docx", "random_work_doc.docx"},
    )

    assert result["level"] == "WARN"
    assert result["coverage_pct"] == 50
    assert result["matched"] == ["field_deployment_guide.docx"]
    assert result["missing"] == ["pm_risk_register.pdf"]


def test_ollama_model_present_accepts_latest_tag_variants():
    mod = _load_tool_module("autotune_preflight_test_model", "tools/autotune_preflight.py")

    assert mod._ollama_model_present("phi4-mini", {"phi4-mini:latest", "nomic-embed-text:latest"})
    assert not mod._ollama_model_present("phi4:14b-q4_k_m", {"phi4-mini:latest"})
