from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any


_REQUIRED_PACK_FIELDS = {
    "pack_id",
    "title",
    "updated_at",
    "policy_note",
    "defaults",
    "questions",
}
_REQUIRED_DEFAULT_KEYS = {"transcript_question_id", "gui_smoke_question_id"}
_REQUIRED_QUESTION_FIELDS = {
    "id",
    "title",
    "profile",
    "track",
    "preferred_mode",
    "prompt",
    "expected_evidence",
    "operator_note",
}
_REQUIRED_EVIDENCE_FIELDS = {"kind", "target", "why"}


def default_demo_rehearsal_pack_path() -> Path:
    return Path(__file__).resolve().parents[2] / "docs" / "04_demo" / "DEMO_REHEARSAL_PACK.json"


def load_demo_rehearsal_pack(path: str | Path | None = None) -> dict[str, Any]:
    pack_path = Path(path) if path else default_demo_rehearsal_pack_path()
    payload = json.loads(pack_path.read_text(encoding="utf-8"))
    _validate_pack(payload, pack_path)
    payload["_path"] = str(pack_path)
    return payload


def select_demo_question(
    pack: dict[str, Any],
    *,
    default_key: str,
    question_id: str = "",
) -> dict[str, Any]:
    questions = {
        str(question["id"]): question
        for question in pack.get("questions", [])
    }
    if question_id:
        try:
            return questions[str(question_id)]
        except KeyError as exc:
            raise ValueError(
                "Question id {!r} not found in rehearsal pack".format(question_id)
            ) from exc

    defaults = pack.get("defaults", {})
    try:
        return questions[str(defaults[default_key])]
    except KeyError as exc:
        raise ValueError(
            "Default key {!r} is missing or invalid in rehearsal pack".format(default_key)
        ) from exc


def format_expected_evidence(question: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for item in question.get("expected_evidence", []):
        lines.append(
            "{}: {} ({})".format(
                str(item.get("kind", "")).replace("_", " ").title(),
                str(item.get("target", "")),
                str(item.get("why", "")),
            )
        )
    return lines


def default_demo_validation_report_dir(project_root: str | Path | None = None) -> Path:
    root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]
    return root / "output" / "rehearsal_validation"


def summarize_mode_sequence(mode_sequence: list[str] | tuple[str, ...] | None) -> str:
    collapsed: list[str] = []
    for raw_mode in mode_sequence or []:
        mode = str(raw_mode).strip()
        if not mode:
            continue
        if not collapsed or collapsed[-1] != mode:
            collapsed.append(mode)
    if not collapsed:
        return "unknown"
    if len(set(collapsed)) == 1:
        return collapsed[0]
    return "mixed"


def build_demo_validation_report(
    pack: dict[str, Any],
    question: dict[str, Any],
    *,
    tool_name: str,
    actual_mode: str,
    actual_path: list[str],
    operator_notes: list[str],
    passed: bool,
    status: str,
    primary_artifact: str,
    mode_sequence: list[str] | None = None,
    details: dict[str, Any] | None = None,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "timestamp": (timestamp or datetime.now()).isoformat(),
        "tool": {
            "name": tool_name,
        },
        "pack": {
            "path": pack.get("_path", ""),
            "pack_id": pack.get("pack_id", ""),
            "policy_note": pack.get("policy_note", ""),
        },
        "selected_question": {
            "id": question.get("id", ""),
            "title": question.get("title", ""),
            "profile": question.get("profile", ""),
            "track": question.get("track", ""),
            "preferred_mode": question.get("preferred_mode", ""),
            "prompt": question.get("prompt", ""),
            "expected_evidence": list(question.get("expected_evidence", [])),
            "expected_evidence_lines": format_expected_evidence(question),
            "operator_note": question.get("operator_note", ""),
        },
        "actual_run": {
            "status": status,
            "mode": actual_mode,
            "mode_sequence": list(mode_sequence or []),
            "path_taken": list(actual_path),
            "primary_artifact": primary_artifact,
        },
        "validation": {
            "passed": bool(passed),
            "operator_notes": list(operator_notes),
        },
    }
    if details:
        report["actual_run"]["details"] = details
    return report


def write_demo_validation_report(
    report: dict[str, Any],
    *,
    project_root: str | Path | None = None,
    timestamp: datetime | None = None,
) -> Path:
    report_dir = default_demo_validation_report_dir(project_root)
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = (timestamp or datetime.now()).strftime("%Y-%m-%d_%H%M%S")
    tool_name = _filename_safe(str(report.get("tool", {}).get("name", "validation")))
    question_id = _filename_safe(
        str(report.get("selected_question", {}).get("id", "question"))
    )
    report_path = report_dir / "{}_{}_{}.json".format(stamp, tool_name, question_id)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report_path


def _filename_safe(value: str) -> str:
    safe_chars = []
    for char in value:
        if char.isalnum() or char in {"-", "_"}:
            safe_chars.append(char)
        else:
            safe_chars.append("_")
    collapsed = "".join(safe_chars).strip("_")
    return collapsed or "artifact"


def _validate_pack(pack: dict[str, Any], pack_path: Path) -> None:
    missing = sorted(_REQUIRED_PACK_FIELDS - set(pack))
    if missing:
        raise ValueError(
            "Rehearsal pack {} is missing fields: {}".format(pack_path, ", ".join(missing))
        )

    defaults = pack.get("defaults", {})
    default_missing = sorted(_REQUIRED_DEFAULT_KEYS - set(defaults))
    if default_missing:
        raise ValueError(
            "Rehearsal pack {} is missing default keys: {}".format(
                pack_path, ", ".join(default_missing)
            )
        )

    seen_ids: set[str] = set()
    questions = pack.get("questions", [])
    if not isinstance(questions, list) or not questions:
        raise ValueError("Rehearsal pack {} must define at least one question".format(pack_path))

    for index, question in enumerate(questions, start=1):
        if not isinstance(question, dict):
            raise ValueError(
                "Rehearsal pack {} question #{} is not an object".format(pack_path, index)
            )
        missing_fields = sorted(_REQUIRED_QUESTION_FIELDS - set(question))
        if missing_fields:
            raise ValueError(
                "Rehearsal pack {} question #{} is missing fields: {}".format(
                    pack_path, index, ", ".join(missing_fields)
                )
            )
        question_id = str(question["id"])
        if question_id in seen_ids:
            raise ValueError(
                "Rehearsal pack {} duplicates question id {!r}".format(pack_path, question_id)
            )
        seen_ids.add(question_id)

        evidence = question.get("expected_evidence", [])
        if not isinstance(evidence, list) or not evidence:
            raise ValueError(
                "Rehearsal pack {} question {!r} must define expected_evidence".format(
                    pack_path, question_id
                )
            )
        for evidence_index, item in enumerate(evidence, start=1):
            if not isinstance(item, dict):
                raise ValueError(
                    "Rehearsal pack {} question {!r} evidence #{} is not an object".format(
                        pack_path, question_id, evidence_index
                    )
                )
            missing_evidence = sorted(_REQUIRED_EVIDENCE_FIELDS - set(item))
            if missing_evidence:
                raise ValueError(
                    "Rehearsal pack {} question {!r} evidence #{} is missing fields: {}".format(
                        pack_path,
                        question_id,
                        evidence_index,
                        ", ".join(missing_evidence),
                    )
                )

    for default_key in _REQUIRED_DEFAULT_KEYS:
        if str(defaults[default_key]) not in seen_ids:
            raise ValueError(
                "Rehearsal pack {} default {!r} does not match a question id".format(
                    pack_path, default_key
                )
            )
