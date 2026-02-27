from __future__ import annotations
import os
from dataclasses import dataclass
from datetime import datetime

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


@dataclass
class AppPaths:
    downloads_root: str
    diagnostics_root: str

    def new_run_folder(self, run_id: str) -> str:
        path = os.path.join(self.diagnostics_root, run_id)
        os.makedirs(path, exist_ok=True)
        return path

    @classmethod
    def default(cls) -> AppPaths:
        return cls(
            downloads_root=os.path.join(_PROJECT_ROOT, "output", "downloads"),
            diagnostics_root=os.path.join(_PROJECT_ROOT, "output", "diagnostics"),
        )


def dated_download_dir(root: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(root, today)


def make_download_filename(name: str, ext: str) -> str:
    ts = datetime.now().strftime("%H%M%S")
    safe_name = name.replace(" ", "_").replace("/", "_")
    return f"{safe_name}_{ts}.{ext}"
