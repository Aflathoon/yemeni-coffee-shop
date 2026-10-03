#!/usr/bin/env python3
"""
Bulk-ingest images from folders into app/static/uploads/<kind>/.

Usage:
    python bulk_upload.py <folder> [<folder2> ...] --kind products
    python bulk_upload.py ~/Pictures/teas --kind products --prefix tea-
    python bulk_upload.py ~/Pictures/teas --kind products --dry-run
    python bulk_upload.py ~/Pictures/teas --kind products --limit 100
"""
import argparse, hashlib, os, re, shutil
from pathlib import Path

ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def normalize_stem(name, prefix=""):
    stem = Path(name).stem.lower()
    stem = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")[:60] or "image"
    return (prefix + stem) if prefix else stem


def file_hash(path, chunk=65536):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()[:12]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folders", nargs="+")
    ap.add_argument("--kind", choices=["products", "posts", "originals"], default="products")
    ap.add_argument("--prefix", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    dest = Path("app/static/uploads") / args.kind
    dest.mkdir(parents=True, exist_ok=True)

    files = []
    for folder in args.folders:
        src = Path(folder).expanduser()
        if not src.is_dir():
            print(f"⚠️  Not a folder: {src}")
            continue
        for root, _, names in os.walk(src):
            for name in names:
                p = Path(root) / name
                if p.suffix.lower() in ALLOWED_EXT:
                    files.append(p)

    files.sort()
    print(f"📂 Found {len(files)} image(s)")

    seen, copied, skipped = set(), 0, {"dup": 0, "exists": 0, "limit": 0, "err": 0}

    for src_file in files:
        if args.limit and copied >= args.limit:
            skipped["limit"] += 1
            continue
        try:
            h = file_hash(src_file)
        except Exception as e:
            print(f"⚠️  {src_file.name}: {e}")
            skipped["err"] += 1
            continue
        if h in seen:
            skipped["dup"] += 1
            continue
        seen.add(h)

        stem = normalize_stem(src_file.name, args.prefix)
        ext = src_file.suffix.lower()
        target = dest / f"{stem}-{h}{ext}"
        if target.exists():
            skipped["exists"] += 1
            continue

        if args.dry_run:
            print(f"  [dry] {src_file} -> {target}")
            copied += 1
            continue
        try:
            shutil.copy2(src_file, target)
            copied += 1
            if copied % 50 == 0:
                print(f"  ... {copied}")
        except Exception as e:
            print(f"❌ {src_file.name}: {e}")
            skipped["err"] += 1

    print(f"\n✅ copied: {copied}")
    print(f"⏭  skipped: {skipped}")
    print(f"📁 dest: {dest}")


if __name__ == "__main__":
    main()
