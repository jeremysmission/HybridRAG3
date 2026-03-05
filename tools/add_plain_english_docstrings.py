from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(r"D:/HybridRAG3")
TARGET_DIRS = [ROOT / "src" / "core", ROOT / "src" / "gui"]


def words(name: str) -> str:
    parts = re.split(r"[_\-.]+", name.lower())
    return " ".join([p for p in parts if p][:8]) or "this operation"


def describe_node(node: ast.AST) -> str:
    if isinstance(node, ast.ClassDef):
        return f"Plain-English: This class groups logic for {words(node.name)}."
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if node.name.startswith("test_"):
            return f"Plain-English: This test checks behavior related to {words(node.name[5:])}."
        return f"Plain-English: This function handles {words(node.name)}."
    return "Plain-English: This block supports the module workflow."


def has_docstring(node: ast.AST) -> bool:
    body = getattr(node, "body", None)
    if not body:
        return False
    first = body[0]
    if isinstance(first, ast.Expr):
        val = first.value
        if isinstance(val, ast.Constant) and isinstance(val.value, str):
            return True
    return False


def gather_insertions(tree: ast.AST) -> list[tuple[int, str]]:
    inserts: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        if has_docstring(node):
            continue

        first_stmt = body[0]
        line = first_stmt.lineno
        indent = " " * getattr(first_stmt, "col_offset", 4)
        text = describe_node(node).replace('"""', "'''")
        insert = f'{indent}"""{text}"""\n'
        inserts.append((line, insert))

    # apply bottom-up
    inserts.sort(key=lambda x: x[0], reverse=True)
    return inserts


def process_file(path: Path) -> bool:
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        source = path.read_text(encoding="utf-8", errors="ignore")

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False

    inserts = gather_insertions(tree)
    if not inserts:
        return False

    lines = source.splitlines(keepends=True)
    for line_no, text in inserts:
        idx = max(0, min(line_no - 1, len(lines)))
        lines.insert(idx, text)

    path.write_text("".join(lines), encoding="utf-8", newline="\n")
    return True


def iter_targets() -> list[Path]:
    out: list[Path] = []
    for d in TARGET_DIRS:
        out.extend(d.rglob("*.py"))
    return sorted(set(out))


def main() -> int:
    changed = 0
    total = 0
    for p in iter_targets():
        total += 1
        if process_file(p):
            changed += 1
    print(f"Scanned {total} files; added docstrings in {changed} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
