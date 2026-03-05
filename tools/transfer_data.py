# === NON-PROGRAMMER GUIDE ===
# Purpose: Automates the transfer data operational workflow for developers or operators.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
"""
Standalone data transfer -- no GUI, no Ollama, no embedder.
Copies source documents to the indexed data staging folder.

USAGE:
    python tools/transfer_data.py <source_folder> <destination_folder>

EXAMPLE:
    python tools/transfer_data.py "D:\RAG Source Data" "D:\RAG Indexed Data\staging"
"""
import os
import sys
import shutil
import hashlib
import time

def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def transfer(src, dst):
    if not os.path.isdir(src):
        print("[FAIL] Source not found: {}".format(src))
        return 1

    os.makedirs(dst, exist_ok=True)
    print()
    print("  SOURCE:      {}".format(src))
    print("  DESTINATION: {}".format(dst))
    print()

    copied = 0
    skipped = 0
    failed = 0
    total_bytes = 0
    t0 = time.time()

    for root, dirs, files in os.walk(src):
        for fname in files:
            src_path = os.path.join(root, fname)
            rel = os.path.relpath(src_path, src)
            dst_path = os.path.join(dst, rel)

            try:
                # Skip if identical file already exists
                if os.path.isfile(dst_path):
                    if os.path.getsize(src_path) == os.path.getsize(dst_path):
                        if md5(src_path) == md5(dst_path):
                            skipped += 1
                            continue

                os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                shutil.copy2(src_path, dst_path)
                size = os.path.getsize(dst_path)
                total_bytes += size
                copied += 1
                print("  [OK] {} ({})".format(rel, _fmt_size(size)))
            except Exception as e:
                failed += 1
                print("  [FAIL] {} -- {}".format(rel, e))

    elapsed = time.time() - t0
    print()
    print("  DONE in {:.1f}s".format(elapsed))
    print("  Copied:  {}  ({})".format(copied, _fmt_size(total_bytes)))
    print("  Skipped: {}  (already exist)".format(skipped))
    print("  Failed:  {}".format(failed))
    print()
    return 0 if failed == 0 else 1


def _fmt_size(b):
    if b < 1024:
        return "{} B".format(b)
    if b < 1024 * 1024:
        return "{:.1f} KB".format(b / 1024)
    return "{:.1f} MB".format(b / 1024 / 1024)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print()
        print("  Usage: python tools/transfer_data.py <source> <destination>")
        print()
        print("  Example:")
        print('    python tools/transfer_data.py "D:\\RAG Source Data" "D:\\RAG Indexed Data\\staging"')
        print()
        sys.exit(1)

    sys.exit(transfer(sys.argv[1], sys.argv[2]))
