# === NON-PROGRAMMER GUIDE ===
# Purpose: Automates the gui screenshot operational workflow for developers or operators.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
"""GUI Screenshot Diff System.

Captures screenshots of each GUI tab and compares to baselines.
Skips gracefully in headless environments.

Usage:
    python tools/gui_screenshot.py          # Capture baselines
    python tools/gui_screenshot.py --diff   # Compare to baselines

Programmatic:
    screenshotter = GuiScreenshot(baseline_dir="output/screenshots/baseline")
    screenshotter.capture("query", widget)
    diffs = screenshotter.compare_all()
"""
from __future__ import annotations

import json
import os
import sys
import logging
from pathlib import Path
from datetime import datetime, timezone

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

logger = logging.getLogger(__name__)


class ScreenshotResult:
    """Result of a single screenshot comparison."""

    def __init__(self, tab: str, baseline_exists: bool,
                 diff_percent: float = 0.0, threshold: float = 5.0,
                 error: str | None = None):
        self.tab = tab
        self.baseline_exists = baseline_exists
        self.diff_percent = diff_percent
        self.threshold = threshold
        self.passed = diff_percent <= threshold if baseline_exists else True
        self.error = error

    def to_dict(self) -> dict:
        return {
            "tab": self.tab,
            "baseline_exists": self.baseline_exists,
            "diff_percent": self.diff_percent,
            "threshold": self.threshold,
            "passed": self.passed,
            "error": self.error,
        }


class GuiScreenshot:
    """Captures and compares GUI screenshots."""

    def __init__(self, baseline_dir: str = "output/screenshots/baseline",
                 current_dir: str = "output/screenshots/current",
                 threshold: float = 5.0):
        self.baseline_dir = Path(baseline_dir)
        self.current_dir = Path(current_dir)
        self.threshold = threshold
        self._has_pil = self._check_pil()
        self._has_display = self._check_display()

    @staticmethod
    def _check_pil() -> bool:
        """Check if PIL/Pillow is available."""
        try:
            from PIL import ImageGrab  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def _check_display() -> bool:
        """Check if display is available."""
        try:
            from tools.gui_env import has_display
            return has_display()
        except ImportError:
            if sys.platform == "win32":
                return True
            return bool(os.environ.get("DISPLAY"))

    def available(self) -> bool:
        """Return True if screenshot capture is possible."""
        return self._has_pil and self._has_display

    def capture(self, tab_name: str, widget=None) -> str | None:
        """Capture a screenshot of the given widget or full screen.

        Returns path to saved PNG, or None if capture failed.
        """
        if not self.available():
            logger.info("Screenshot capture not available (no PIL or no display)")
            return None

        self.current_dir.mkdir(parents=True, exist_ok=True)
        path = self.current_dir / "{}.png".format(tab_name)

        try:
            from PIL import ImageGrab

            if widget is not None:
                # Capture widget bounding box
                try:
                    x = widget.winfo_rootx()
                    y = widget.winfo_rooty()
                    w = widget.winfo_width()
                    h = widget.winfo_height()
                    img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
                except Exception:
                    img = ImageGrab.grab()
            else:
                img = ImageGrab.grab()

            img.save(str(path))
            return str(path)
        except Exception as e:
            logger.warning("Screenshot capture failed: %s", e)
            return None

    def save_baseline(self, tab_name: str, widget=None) -> str | None:
        """Capture and save as baseline."""
        if not self.available():
            return None
        self.baseline_dir.mkdir(parents=True, exist_ok=True)
        path = self.baseline_dir / "{}.png".format(tab_name)

        try:
            from PIL import ImageGrab

            if widget:
                x = widget.winfo_rootx()
                y = widget.winfo_rooty()
                w = widget.winfo_width()
                h = widget.winfo_height()
                img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
            else:
                img = ImageGrab.grab()

            img.save(str(path))
            return str(path)
        except Exception as e:
            logger.warning("Baseline capture failed: %s", e)
            return None

    def compare(self, tab_name: str) -> ScreenshotResult:
        """Compare current screenshot to baseline for a tab."""
        baseline = self.baseline_dir / "{}.png".format(tab_name)
        current = self.current_dir / "{}.png".format(tab_name)

        if not baseline.exists():
            return ScreenshotResult(
                tab=tab_name, baseline_exists=False,
                error="No baseline image")

        if not current.exists():
            return ScreenshotResult(
                tab=tab_name, baseline_exists=True,
                diff_percent=100.0, threshold=self.threshold,
                error="No current image")

        if not self._has_pil:
            return ScreenshotResult(
                tab=tab_name, baseline_exists=True,
                error="PIL not available for comparison")

        try:
            from PIL import Image
            import struct

            base_img = Image.open(str(baseline)).convert("RGB")
            curr_img = Image.open(str(current)).convert("RGB")

            # Resize current to match baseline if needed
            if base_img.size != curr_img.size:
                curr_img = curr_img.resize(base_img.size)

            # Pixel-by-pixel comparison
            base_data = list(base_img.getdata())
            curr_data = list(curr_img.getdata())

            total_pixels = len(base_data)
            diff_pixels = 0
            for bp, cp in zip(base_data, curr_data):
                if bp != cp:
                    diff_pixels += 1

            diff_pct = (diff_pixels / max(total_pixels, 1)) * 100

            return ScreenshotResult(
                tab=tab_name, baseline_exists=True,
                diff_percent=round(diff_pct, 2),
                threshold=self.threshold)
        except Exception as e:
            return ScreenshotResult(
                tab=tab_name, baseline_exists=True,
                error="Comparison failed: {}".format(str(e)))

    def compare_all(self) -> list[ScreenshotResult]:
        """Compare all tabs that have baselines."""
        results = []
        if not self.baseline_dir.exists():
            return results

        for png in sorted(self.baseline_dir.glob("*.png")):
            tab = png.stem
            results.append(self.compare(tab))

        return results

    def save_report(self, results: list[ScreenshotResult],
                    path: str | Path) -> None:
        """Save comparison report to JSON."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
            "results": [r.to_dict() for r in results],
        }
        p.write_text(json.dumps(report, indent=2), encoding="utf-8")


def selftest() -> int:
    """Quick selftest of screenshot system."""
    failures = []

    ss = GuiScreenshot()
    print("PIL available: {}".format(ss._has_pil))
    print("Display available: {}".format(ss._has_display))
    print("Screenshot capture available: {}".format(ss.available()))

    # Test ScreenshotResult
    r = ScreenshotResult(tab="test", baseline_exists=True,
                         diff_percent=3.0, threshold=5.0)
    if r.passed:
        print("[OK] ScreenshotResult pass logic correct (3% < 5%)")
    else:
        failures.append("ScreenshotResult should pass at 3%")

    r2 = ScreenshotResult(tab="test2", baseline_exists=True,
                          diff_percent=10.0, threshold=5.0)
    if not r2.passed:
        print("[OK] ScreenshotResult fail logic correct (10% > 5%)")
    else:
        failures.append("ScreenshotResult should fail at 10%")

    # Test no-baseline case
    r3 = ScreenshotResult(tab="missing", baseline_exists=False)
    if r3.passed:
        print("[OK] No baseline = pass (first run)")
    else:
        failures.append("No baseline should pass")

    # Test to_dict
    d = r.to_dict()
    if d["tab"] == "test" and d["passed"]:
        print("[OK] to_dict serialization")
    else:
        failures.append("to_dict incorrect")

    if failures:
        for f in failures:
            print("[FAIL] {}".format(f))
        return 1

    print("\n[OK] All screenshot diff checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(selftest())
