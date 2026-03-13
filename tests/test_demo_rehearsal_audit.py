import json
import sqlite3
from datetime import datetime

from src.tools.demo_rehearsal_audit import (
    _meaningful_terms,
    _required_term_count,
    audit_demo_rehearsal_pack,
    write_demo_rehearsal_audit_report,
)


def _make_demo_db(tmp_path, rows):
    db_path = tmp_path / "demo.sqlite3"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE chunks (
            source_path TEXT,
            chunk_index INTEGER,
            text TEXT
        )
        """
    )
    conn.executemany(
        "INSERT INTO chunks (source_path, chunk_index, text) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    return db_path


def test_meaningful_terms_drop_connectors_and_keep_signal_words():
    terms = _meaningful_terms(
        "section 7.3 calibration interval plus quarterly review cadence"
    )

    assert "section" not in terms
    assert "plus" not in terms
    assert "7.3" in terms
    assert "calibration" in terms
    assert "quarterly" in terms


def test_required_term_count_scales_with_phrase_size():
    assert _required_term_count(0) == 1
    assert _required_term_count(2) == 2
    assert _required_term_count(4) == 3
    assert _required_term_count(7) == 5


def test_audit_demo_rehearsal_pack_passes_path_and_citation_targets(tmp_path):
    db_path = _make_demo_db(
        tmp_path,
        [
            (
                r"D:\Corpus\Leadership_Playbook.pdf",
                3,
                "The leadership comparison table covers transformational, "
                "transactional, and servant leadership in one summary.",
            ),
        ],
    )
    pack = {
        "_path": str(tmp_path / "pack.json"),
        "pack_id": "demo_pack",
        "title": "Demo Pack",
        "questions": [
            {
                "id": "leadership",
                "title": "Leadership",
                "preferred_mode": "online",
                "expected_evidence": [
                    {"kind": "path", "target": "Leadership_Playbook.pdf"},
                    {
                        "kind": "citation_target",
                        "target": (
                            "leadership comparison table covering transformational, "
                            "transactional, and servant leadership"
                        ),
                    },
                ],
            }
        ],
    }

    report = audit_demo_rehearsal_pack(pack, db_path=db_path)

    assert report["ok"] is True
    assert report["summary"]["checks"] == 2
    assert report["summary"]["passed"] == 2
    citation = report["questions"][0]["checks"][1]
    assert citation["ok"] is True
    assert citation["matches"][0]["preferred_source_match"] is True
    assert citation["matches"][0]["matched_term_count"] >= citation["required_term_count"]


def test_audit_demo_rehearsal_pack_allows_keyword_match_for_descriptive_target(tmp_path):
    db_path = _make_demo_db(
        tmp_path,
        [
            (
                r"D:\Corpus\Maintenance_Procedure_Guide.docx",
                7,
                "Section 7.3 states that calibration interval checks are reviewed "
                "on a quarterly cadence by the maintenance team.",
            ),
        ],
    )
    pack = {
        "_path": str(tmp_path / "pack.json"),
        "pack_id": "demo_pack",
        "title": "Demo Pack",
        "questions": [
            {
                "id": "maintenance",
                "title": "Maintenance",
                "preferred_mode": "offline",
                "expected_evidence": [
                    {"kind": "path", "target": "Maintenance_Procedure_Guide.docx"},
                    {
                        "kind": "citation_target",
                        "target": (
                            "section 7.3 calibration interval plus quarterly review cadence"
                        ),
                    },
                ],
            }
        ],
    }

    report = audit_demo_rehearsal_pack(pack, db_path=db_path)

    assert report["ok"] is True
    citation = report["questions"][0]["checks"][1]
    assert citation["ok"] is True
    assert citation["matches"][0]["matched_term_count"] >= citation["required_term_count"]


def test_write_demo_rehearsal_audit_report_uses_timestamped_name(tmp_path):
    report = {
        "ok": True,
        "timestamp": "2026-03-12T20:40:00",
        "pack": {"pack_id": "demo_pack"},
        "index": {"db_path": str(tmp_path / "demo.sqlite3")},
        "summary": {"questions": 1, "checks": 2, "passed": 2, "failed": 0},
        "questions": [],
    }

    report_path = write_demo_rehearsal_audit_report(
        report,
        project_root=tmp_path,
        timestamp=datetime(2026, 3, 12, 20, 40, 0),
    )

    assert report_path.name == "2026-03-12_204000_demo_rehearsal_audit.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["summary"]["passed"] == 2


def test_audit_prefers_named_source_for_citation_targets(tmp_path):
    db_path = _make_demo_db(
        tmp_path,
        [
            (
                r"D:\Corpus\Other.pdf",
                1,
                "Subject Leader Manager Essence Change Stability appears in this decoy row.",
            ),
            (
                r"D:\Corpus\Leadership vs. Management.pdf",
                6,
                "Subject Leader Manager Essence Change Stability Focus Leading people Managing work",
            ),
        ],
    )
    pack = {
        "_path": str(tmp_path / "pack.json"),
        "pack_id": "demo_pack",
        "title": "Demo Pack",
        "questions": [
            {
                "id": "leadership",
                "title": "Leadership",
                "preferred_mode": "online",
                "expected_evidence": [
                    {"kind": "path", "target": "Leadership vs. Management.pdf"},
                    {
                        "kind": "citation_target",
                        "target": "Subject Leader Manager Essence Change Stability",
                    },
                ],
            }
        ],
    }

    report = audit_demo_rehearsal_pack(pack, db_path=db_path)

    citation = report["questions"][0]["checks"][1]
    assert citation["ok"] is True
    assert citation["matches"][0]["preferred_source_match"] is True
    assert citation["matches"][0]["source_path"].endswith("Leadership vs. Management.pdf")
