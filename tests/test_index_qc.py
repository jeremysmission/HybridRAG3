import sqlite3
from pathlib import Path

from src.core.index_qc import (
    build_index_fingerprint,
    compare_fingerprints,
    detect_index_contamination,
)


def _build_chunks_db(db_path: Path, rows: list[tuple[str, int]]) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE chunks (source_path TEXT)")
        for source_path, count in rows:
            conn.executemany(
                "INSERT INTO chunks (source_path) VALUES (?)",
                [(source_path,)] * count,
            )
        conn.commit()
    finally:
        conn.close()


def test_detect_index_contamination_flags_temp_and_outside_root(tmp_path):
    db_path = tmp_path / "hybridrag.sqlite3"
    source_root = tmp_path / "source"
    source_root.mkdir()
    good_doc = source_root / "good.docx"
    temp_doc = Path(r"C:\Users\jerem\AppData\Local\Temp\junk.txt")
    # Use a path that is NOT inside AppData\Local\Temp so it only triggers
    # the outside-root check, not the temp-path heuristic.
    outside_doc = Path(r"D:\other\bad.pdf")

    _build_chunks_db(
        db_path,
        [
            (str(good_doc), 2),
            (str(temp_doc), 1),
            (str(outside_doc), 1),
        ],
    )

    result = detect_index_contamination(db_path, source_root=str(source_root))

    assert result["level"] == "FAIL"
    assert result["suspicious_count"] == 2
    assert result["temp_path_count"] == 1
    assert result["outside_root_count"] == 2


def test_build_index_fingerprint_detects_changed_artifacts(tmp_path):
    db_path = tmp_path / "hybridrag.sqlite3"
    emb_dir = tmp_path / "_embeddings"
    emb_dir.mkdir()
    artifact = emb_dir / "vectors.dat"
    artifact.write_text("abc", encoding="utf-8")
    _build_chunks_db(db_path, [(str(tmp_path / "source" / "a.txt"), 1)])

    baseline = build_index_fingerprint(db_path, emb_dir)

    artifact.write_text("abcd", encoding="utf-8")
    current = build_index_fingerprint(db_path, emb_dir)
    diff = compare_fingerprints(current, baseline)

    assert diff["matches"] is False
    assert str(artifact.resolve()) in diff["changed"]
