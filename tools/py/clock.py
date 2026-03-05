# === NON-PROGRAMMER GUIDE ===
# Purpose: Automates the clock operational workflow for developers or operators.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG v3 -- Persistent Clock (tools/py/clock.py)
# ============================================================================
# Writes a running timestamp to clock_log.txt every second.
# Use during installs or long operations to track elapsed time.
#
# Start:  python tools/py/clock.py
# Stop:   Ctrl+C
# Read:   type clock_log.txt  (or: python tools/py/clock.py --read)
#
# INTERNET ACCESS: NONE
# ============================================================================

import sys
import time
import os

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "..", "clock_log.txt")


def format_military(total_seconds):
    """Convert elapsed seconds to DD:HH:MM:SS military format."""
    days = int(total_seconds // 86400)
    remaining = int(total_seconds % 86400)
    hours = remaining // 3600
    remaining = remaining % 3600
    minutes = remaining // 60
    seconds = remaining % 60
    return f"{days:03d}d {hours:02d}:{minutes:02d}:{seconds:02d}"


def read_log():
    """Print the last 20 lines of the clock log."""
    if not os.path.isfile(LOG_FILE):
        print("[WARN] No clock_log.txt found. Run the clock first.")
        return
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
    print(f"--- Clock Log ({len(lines)} entries) ---")
    for line in lines[-20:]:
        print(line.rstrip())
    if len(lines) > 20:
        print(f"... ({len(lines) - 20} earlier entries not shown)")


def run_clock():
    """Tick every second, write elapsed time to log file."""
    print(f"[OK] Clock started. Writing to: {os.path.abspath(LOG_FILE)}")
    print("[OK] Press Ctrl+C to stop.")
    print()

    start = time.time()

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"Clock started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("-" * 40 + "\n")
        f.flush()

        try:
            while True:
                elapsed = time.time() - start
                stamp = format_military(elapsed)
                wall = time.strftime("%H:%M:%S")
                line = f"[{wall}] elapsed {stamp}"

                # Write to file
                f.write(line + "\n")
                f.flush()

                # Print to console every 10 seconds to avoid spam
                total_sec = int(elapsed)
                if total_sec % 10 == 0:
                    print(f"\r  {line}", end="", flush=True)

                time.sleep(1)

        except KeyboardInterrupt:
            elapsed = time.time() - start
            final = format_military(elapsed)
            wall = time.strftime("%H:%M:%S")
            f.write(f"\nClock stopped: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total elapsed: {final}\n")
            print(f"\n\n[OK] Clock stopped. Total elapsed: {final}")
            print(f"[OK] Log saved to: {os.path.abspath(LOG_FILE)}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--read":
        read_log()
    else:
        run_clock()
