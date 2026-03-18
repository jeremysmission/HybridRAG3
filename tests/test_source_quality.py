import sqlite3

from src.core.source_quality import (
    assess_source_quality,
    ensure_source_quality_map,
    ensure_source_quality_schema,
    fetch_source_quality_map,
    refresh_all_source_quality_records,
    upsert_source_quality_records,
)


def test_assess_source_quality_marks_saved_resource_as_suspect():
    record = assess_source_quality(
        r"D:\capture\course_files\_files\saved_resource.html",
        "Navigation next topic previous topic report a bug",
    )

    assert record["retrieval_tier"] == "suspect"
    assert record["is_saved_resource"] == 1
    assert record["is_html_capture"] == 1


def test_assess_source_quality_marks_clean_docx_as_serve():
    record = assess_source_quality(
        r"D:\docs\manual.docx",
        "This chapter explains the recommended citation format and source evidence handling.",
    )

    assert record["retrieval_tier"] == "serve"
    assert record["quality_score"] >= 0.90
    assert record["has_missing_path"] == 0


def test_assess_source_quality_marks_known_junk_sources_as_suspect():
    cases = [
        r"D:\RAG Source Data\Testing_Addon_Pack\Unanswerable_Question_Bank.pdf",
        r"D:\RAG Source Data\golden_seeds_engineer.json",
        r"D:\RAG Source Data\archives\HybridRAG3_Role_Corpus_Pack.zip",
        r"C:\Users\jerem\AppData\Local\Temp\_pipeline_test_doc.txt",
    ]

    for path in cases:
        record = assess_source_quality(path, "Representative source text that would otherwise look clean.")
        assert record["retrieval_tier"] == "suspect"
        assert record["quality_score"] < 0.75


def test_ensure_source_quality_map_backfills_missing_rows():
    conn = sqlite3.connect(":memory:")
    ensure_source_quality_schema(conn)

    quality_map = ensure_source_quality_map(
        conn,
        {
            "": "bare row",
            r"D:\capture\saved_resource.html": "theme auto light dark previous topic next topic",
        },
    )

    assert quality_map[""]["retrieval_tier"] == "suspect"
    assert quality_map[r"D:\capture\saved_resource.html"]["retrieval_tier"] == "suspect"

    fetched = fetch_source_quality_map(conn, quality_map.keys())
    assert set(fetched) == set(quality_map)


def test_upsert_source_quality_records_replaces_existing_row():
    conn = sqlite3.connect(":memory:")
    ensure_source_quality_schema(conn)

    source_path = r"D:\docs\spec.md"
    upsert_source_quality_records(
        conn,
        [
            assess_source_quality(
                source_path,
                "Clean primary source text for answer grounding.",
            )
        ],
    )
    upsert_source_quality_records(
        conn,
        [
            {
                "source_path": source_path,
                "source_type": "md",
                "retrieval_tier": "archive",
                "quality_score": 0.40,
                "is_html_capture": 0,
                "is_saved_resource": 0,
                "is_boilerplate": 1,
                "has_missing_path": 0,
                "has_encoded_blob": 0,
                "flags_json": '["manual_override"]',
                "updated_at": "2026-03-11T00:00:00+00:00",
            }
        ],
    )

    row = fetch_source_quality_map(conn, [source_path])[source_path]
    assert row["retrieval_tier"] == "archive"
    assert row["is_boilerplate"] == 1
    assert row["quality_score"] == 0.40


def test_ensure_source_quality_map_refreshes_stale_existing_rows():
    conn = sqlite3.connect(":memory:")
    ensure_source_quality_schema(conn)

    source_path = r"D:\RAG Source Data\golden_seeds_engineer.json"
    conn.execute(
        """
        INSERT INTO source_quality (
            source_path, source_type, retrieval_tier, quality_score,
            is_html_capture, is_saved_resource, is_boilerplate,
            has_missing_path, has_encoded_blob, flags_json, updated_at
        ) VALUES (?, ?, ?, ?, 0, 0, 0, 0, 0, ?, ?)
        """,
        (source_path, "json", "serve", 0.92, "[]", "2026-03-01T00:00:00+00:00"),
    )
    conn.commit()

    quality_map = ensure_source_quality_map(
        conn,
        {source_path: "Representative source text that would otherwise look clean."},
    )

    record = quality_map[source_path]
    assert record["retrieval_tier"] == "suspect"
    assert "golden_seed_file" in record["flags_json"]
    assert record["quality_score"] < 0.75


def test_refresh_all_source_quality_records_reassesses_existing_chunks():
    conn = sqlite3.connect(":memory:")
    ensure_source_quality_schema(conn)
    conn.execute(
        """
        CREATE TABLE chunks (
            chunk_pk INTEGER PRIMARY KEY AUTOINCREMENT,
            source_path TEXT,
            chunk_index INTEGER,
            text TEXT
        )
        """
    )

    stale_path = r"D:\RAG Source Data\Testing_Addon_Pack\Unanswerable_Question_Bank.pdf"
    clean_path = r"D:\RAG Source Data\Docs\real_manual.pdf"
    conn.execute(
        "INSERT INTO chunks (source_path, chunk_index, text) VALUES (?, ?, ?)",
        (stale_path, 0, "Representative test artifact chunk."),
    )
    conn.execute(
        "INSERT INTO chunks (source_path, chunk_index, text) VALUES (?, ?, ?)",
        (clean_path, 0, "Primary technical manual content."),
    )
    conn.execute(
        """
        INSERT INTO source_quality (
            source_path, source_type, retrieval_tier, quality_score,
            is_html_capture, is_saved_resource, is_boilerplate,
            has_missing_path, has_encoded_blob, flags_json, updated_at
        ) VALUES (?, ?, ?, ?, 0, 0, 0, 0, 0, ?, ?)
        """,
        (stale_path, "pdf", "serve", 0.92, "[]", "2026-03-01T00:00:00+00:00"),
    )
    conn.commit()

    stats = refresh_all_source_quality_records(conn)
    rows = fetch_source_quality_map(conn, [stale_path, clean_path])

    assert stats["total_sources"] == 2
    assert stats["refreshed"] >= 2
    assert rows[stale_path]["retrieval_tier"] == "suspect"
    assert "test_or_demo_artifact" in rows[stale_path]["flags_json"]
    assert rows[clean_path]["retrieval_tier"] == "serve"
