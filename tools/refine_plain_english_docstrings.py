from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(r"D:/HybridRAG3")
TARGET_FILES = [
    ROOT / "src/core/query_engine.py",
    ROOT / "src/core/retriever.py",
    ROOT / "src/core/llm_router.py",
    ROOT / "src/core/config.py",
    ROOT / "src/core/indexer.py",
    ROOT / "src/core/vector_store.py",
    ROOT / "src/core/embedder.py",
    ROOT / "src/core/grounded_query_engine.py",
    ROOT / "src/core/api_client_factory.py",
    ROOT / "src/core/network_gate.py",
    ROOT / "src/gui/app.py",
    ROOT / "src/gui/core/controller.py",
    ROOT / "src/gui/panels/query_panel.py",
    ROOT / "src/gui/panels/index_panel.py",
    ROOT / "src/gui/panels/settings_panel.py",
]


def split_words(name: str) -> str:
    words = re.split(r"[_\-.]+", name)
    words = [w for w in words if w]
    return " ".join(words)


def make_func_doc(name: str, class_name: str | None = None) -> str:
    if name == "__init__":
        if class_name:
            return f"Plain-English: Sets up the {class_name} object and prepares state used by its methods."
        return "Plain-English: Prepares startup state and dependencies for this module logic."
    if name == "__enter__":
        return "Plain-English: Starts a managed resource block and returns the ready-to-use object."
    if name == "__exit__":
        return "Plain-English: Closes or cleans up resources when a managed block ends."
    if name == "__post_init__":
        return "Plain-English: Applies defaults, validation, and value cleanup right after object creation."
    if name == "_work":
        return "Plain-English: Contains the background-job body that does the heavy work for this action."
    if name in {"build", "_build"}:
        return "Plain-English: Creates this panel's widgets and lays them out in the visible UI."
    if name == "apply_theme":
        return "Plain-English: Reapplies colors and style settings so the view matches the active theme."
    if name == "on_reset":
        return "Plain-English: Restores settings controls back to default values."
    if name == "theme_walk":
        return "Plain-English: Walks child widgets and applies theme colors recursively."
    if name == "current_use_case_key":
        return "Plain-English: Returns the selected use-case key used to route query behavior."
    if name.endswith("_if_active"):
        what = split_words(name[:-10])
        return f"Plain-English: Runs {what} only when this panel is still the active request owner."
    if name == "fallback_score":
        return "Plain-English: Computes a backup confidence score when richer scoring data is unavailable."
    if name == "blocked_setattr":
        return "Plain-English: Prevents accidental mutation of fields that are intentionally read-only."
    if name == "get_status":
        return "Plain-English: Returns a concise status snapshot for display and diagnostics."
    if name == "check_primary_done":
        return "Plain-English: Checks whether the primary model route finished and if failover is needed."

    if name.startswith("dispatch_"):
        what = split_words(name[len("dispatch_"):])
        return f"Plain-English: Starts the {what} workflow and routes work to the right handler."
    if name.startswith("on_"):
        what = split_words(name[len("on_"):])
        return f"Plain-English: Responds to the {what} event and updates state or UI accordingly."
    if name.startswith("get_"):
        what = split_words(name[len("get_"):])
        return f"Plain-English: Returns the current {what} value from active state or configuration."
    if name.startswith("set_"):
        what = split_words(name[len("set_"):])
        return f"Plain-English: Updates the {what} value and keeps related state in sync."
    if name.startswith("update_"):
        what = split_words(name[len("update_"):])
        return f"Plain-English: Refreshes {what} using the latest available data."
    if name.startswith("build_"):
        what = split_words(name[len("build_"):])
        return f"Plain-English: Builds the {what} output used by later steps in the pipeline."
    if name.startswith("query_"):
        what = split_words(name[len("query_"):])
        return f"Plain-English: Runs the {what} query flow and returns a result."
    if name.startswith("calculate_"):
        what = split_words(name[len("calculate_"):])
        return f"Plain-English: Calculates {what} from the inputs provided to this method."
    if name.startswith("switch_"):
        what = split_words(name[len("switch_"):])
        return f"Plain-English: Switches {what} to a new mode or source safely."
    if name.startswith("check_"):
        what = split_words(name[len("check_"):])
        return f"Plain-English: Verifies {what} state before allowing the workflow to continue."
    if name.startswith("prepare_"):
        what = split_words(name[len("prepare_"):])
        return f"Plain-English: Prepares {what} resources before the next processing step."
    if name.startswith("append_"):
        what = split_words(name[len("append_"):])
        return f"Plain-English: Appends {what} data to the current in-memory result."
    if name.startswith("start_"):
        what = split_words(name[len("start_"):])
        return f"Plain-English: Starts the {what} process and tracks its progress."
    if name.startswith("finish_"):
        what = split_words(name[len("finish_"):])
        return f"Plain-English: Finishes the {what} process and performs cleanup steps."
    if name.startswith("emit"):
        return "Plain-English: Broadcasts an event so subscribed components can react."
    if name.startswith("query_"):
        what = split_words(name[len("query_"):])
        return f"Plain-English: Runs the {what} query path and returns the model-ready output."

    words = split_words(name)
    return f"Plain-English: Executes the {words} logic for this component."


def make_class_doc(name: str, module_name: str) -> str:
    words = split_words(name)
    if name.lower().endswith("state"):
        return f"Plain-English: Holds shared {words} values that other methods read and update."
    return f"Plain-English: Centralizes {words} behavior for the {module_name} runtime workflow."


def replace_docstrings(path: Path) -> bool:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    parent: dict[ast.AST, ast.AST] = {}
    for p in ast.walk(tree):
        for c in ast.iter_child_nodes(p):
            parent[c] = p

    lines = source.splitlines(keepends=True)
    edits: list[tuple[int, int, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if not getattr(node, "body", None):
            continue

        first = node.body[0]
        if not isinstance(first, ast.Expr):
            continue
        val = first.value
        if not (isinstance(val, ast.Constant) and isinstance(val.value, str)):
            continue
        text = val.value.strip()
        if not text.startswith("Plain-English:"):
            continue

        indent = " " * first.col_offset
        if isinstance(node, ast.ClassDef):
            new_doc = make_class_doc(node.name, path.stem)
        else:
            cls_name = None
            par = parent.get(node)
            if isinstance(par, ast.ClassDef):
                cls_name = par.name
            new_doc = make_func_doc(node.name, cls_name)

        replacement = f'{indent}"""{new_doc}"""\n'
        edits.append((first.lineno, first.end_lineno, replacement))

    if not edits:
        return False

    edits.sort(key=lambda x: x[0], reverse=True)
    for start, end, replacement in edits:
        lines[start - 1:end] = [replacement]

    new_source = "".join(lines)
    if new_source != source:
        path.write_text(new_source, encoding="utf-8", newline="\n")
        return True
    return False


def main() -> int:
    changed = 0
    for path in TARGET_FILES:
        if path.exists() and replace_docstrings(path):
            changed += 1
    print(f"Updated {changed} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
