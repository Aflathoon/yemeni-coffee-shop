#!/usr/bin/env python3
"""
Optimize images in app/static/images/ and app/static/uploads/**.

- Converts JPEG/PNG to WebP (quality 85, method 6)
- Resizes to max 800px on the long edge
- Skips files under 5 KB (likely icons/spacers)
- Optional: --keep-jpg keeps the source alongside
- Optional: --resize-only to skip conversion (rare)
- Prints a per-file report

Usage:
    python optimize_images.py                     # convert images/ and uploads/
    python optimize_images.py --only images       # just seed images
    python optimize_images.py --only uploads
    python optimize_images.py --dry-run           # report only, no writes
    python optimize_images.py --keep-original
"""
import argparse
import os
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Pillow not installed. Run: pip install Pillow", file=sys.stderr)
    sys.exit(1)

WEBP_QUALITY = 85
MAX_EDGE = 800
MIN_SIZE_BYTES = 5_000

TARGET_DIRS = {
    "images": Path("app/static/images"),
    "uploads": Path("app/static/uploads"),
    "originals": Path("app/static/uploads/originals"),
}


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def should_skip(path):
    if path.suffix.lower() not in (".jpg", ".jpeg", ".png"):
        return True
    if path.stat().st_size < MIN_SIZE_BYTES:
        return True
    return False


def process_one(path, dry_run=False, keep_original=False):
    """Return (before_bytes, after_bytes, status)."""
    before = path.stat().st_size
    target = path.with_suffix(".webp")

    if target.exists() and target.stat().st_mtime >= path.stat().st_mtime:
        return before, target.stat().st_size, "already-optimized"

    if dry_run:
        return before, 0, "would-convert"

    try:
        with Image.open(path) as im:
            im.load()
            # Preserve transparency for PNGs
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                bg = None
            else:
                bg = im.convert("RGB")

            src = bg if bg is not None else im

            # Resize preserving aspect ratio
            w, h = src.size
            longest = max(w, h)
            if longest > MAX_EDGE:
                ratio = MAX_EDGE / longest
                new_size = (int(w * ratio), int(h * ratio))
                src = src.resize(new_size, Image.LANCZOS)

            src.save(target, "WEBP", quality=WEBP_QUALITY, method=6)
    except Exception as e:
        return before, 0, f"error: {e}"

    after = target.stat().st_size

    if keep_original:
        bak = path.with_suffix(path.suffix + ".bak")
        if not bak.exists():
            path.rename(bak)
        else:
            path.unlink()
    else:
        # Remove the original only if the WebP is smaller (avoid replacing good JPEG with larger WebP)
        if after < before:
            path.unlink()
        else:
            target.unlink()
            return before, before, "skipped: webp larger"

    return before, after, "converted"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["images", "uploads", "originals", "all"], default="all")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep-original", action="store_true")
    args = ap.parse_args()

    dirs = []
    if args.only in ("images", "all"):
        dirs.append(TARGET_DIRS["images"])
    if args.only in ("uploads", "all"):
        dirs.append(TARGET_DIRS["uploads"])
    if args.only in ("originals", "all"):
        dirs.append(TARGET_DIRS["originals"])

    files = []
    for d in dirs:
        if not d.exists():
            continue
        files.extend(sorted(d.rglob("*.jpg")))
        files.extend(sorted(d.rglob("*.jpeg")))
        files.extend(sorted(d.rglob("*.png")))

    files = [f for f in files if not should_skip(f) and "/_originals/" not in str(f)]

    print(f"Found {len(files)} image(s) to examine")
    if args.dry_run:
        print("(dry run — nothing will be written)\n")
    print(f"{'file':<60} {'before':>10} {'after':>10} {'saved':>8}  status")
    print("-" * 110)

    total_before = total_after = 0
    converted = skipped = 0

    for f in files:
        before, after, status = process_one(f, dry_run=args.dry_run, keep_original=args.keep_original)
        total_before += before
        total_after += after or before
        if status == "converted":
            converted += 1
        elif status != "already-optimized":
            skipped += 1
        saved = before - after if after else 0
        pct = (saved / before * 100) if before and saved > 0 else 0
        rel = str(f.relative_to(f.parents[len(f.parents) - 4]) if len(f.parents) >= 4 else f)
        print(f"{rel:<60} {human(before):>10} {human(after):>10} {pct:>7.1f}%  {status}")

    print("-" * 110)
    saved_total = total_before - total_after
    pct_total = (saved_total / total_before * 100) if total_before else 0
    print(f"Total: {human(total_before)} → {human(total_after)}  ({human(saved_total)} saved, {pct_total:.1f}%)")
    print(f"Converted: {converted}  ·  skipped: {skipped}")


if __name__ == "__main__":
    main()
