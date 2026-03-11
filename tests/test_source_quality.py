import sqlite3

from src.core.source_quality import (
    assess_source_quality,
    ensure_source_quality_map,
    ensure_source_quality_schema,
    fetch_source_quality_map,
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
