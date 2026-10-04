#!/usr/bin/env python3
"""
Find duplicate image files by SHA-256 content hash.

Usage:
    python find_duplicate_files.py                # scan uploads/products/ and uploads/
    python find_duplicate_files.py --delete       # delete duplicates, keep first
    python find_duplicate_files.py --folder app/static/uploads/products
"""
import argparse
import hashlib
from collections import defaultdict
from pathlib import Path


def hash_file(path, chunk=65536):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def scan(folder):
    by_hash = defaultdict(list)
    folder = Path(folder)
    if not folder.exists():
        print(f"⚠ Not a folder: {folder}")
        return by_hash
    for f in folder.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            continue
        try:
            h = hash_file(f)
        except Exception as e:
            print(f"  ⚠ couldn't hash {f.name}: {e}")
            continue
        by_hash[h].append(f)
    return by_hash


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", default="app/static/uploads/products")
    ap.add_argument("--delete", action="store_true", help="Delete duplicates (keep first)")
    args = ap.parse_args()

    by_hash = scan(args.folder)
    groups = {h: files for h, files in by_hash.items() if len(files) > 1}

    if not groups:
        print(f"✅ No duplicate files in {args.folder}")
        return

    print(f"Found {len(groups)} group(s) of duplicate files:\n")

    total_dupes = 0
    total_bytes = 0
    to_delete = []

    for h, files in groups.items():
        # Keep the first (alphabetically) — usually the "original" name
        files_sorted = sorted(files)
        keeper = files_sorted[0]
        dupes = files_sorted[1:]
        print(f"  {h[:12]}… ({len(dupes)+1} copies):")
        print(f"     KEEP: {keeper.relative_to('app/static/uploads')}")
        for d in dupes:
            size = d.stat().st_size
            total_bytes += size
            print(f"     DUP:  {d.relative_to('app/static/uploads')}  ({size/1024:.0f} KB)")
            to_delete.append(d)
        total_dupes += len(dupes)
        print()

    print(f"Summary: {total_dupes} duplicate file(s) · would free {total_bytes/1024/1024:.1f} MB")

    if args.delete:
        confirm = input(f"\nDelete {len(to_delete)} file(s)? [y/N] ")
        if confirm.strip().lower() != "y":
            print("Aborted.")
            return
        for f in to_delete:
            try:
                f.unlink()
            except Exception as e:
                print(f"  ❌ {f.name}: {e}")
        print(f"✅ Deleted {len(to_delete)} file(s)")
    else:
        print("\nℹ Dry run. Add --delete to actually remove them.")


if __name__ == "__main__":
    main()
