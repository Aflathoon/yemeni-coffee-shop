"""
Codebase indexer + file reader for the AI code assistant.

Reads the project tree, filters to source files, allows targeted reads.
Safe: never returns secrets (.env, .git, .venv, instance/).
"""
import os
from pathlib import Path


# Directories to skip
SKIP_DIRS = {
    ".venv", ".git", "__pycache__", "instance", "node_modules",
    ".pytest_cache", ".mypy_cache", "migrations/versions", "static/uploads",
    "static/images", ".idea", ".vscode",
}

# File extensions we consider "source"
SOURCE_EXTS = {".py", ".html", ".css", ".js", ".json", ".md", ".txt", ".envrc", ".toml", ".yml", ".yaml"}

# Files we never read
SKIP_FILES = {".env", ".env.local", ".env.production", "shop.db"}

# Size limits
MAX_FILE_SIZE = 500 * 1024     # 500 KB per file
MAX_TOTAL_READ = 200 * 1024    # 200 KB total across all reads


def project_root():
    """The repo root (parent of app/)."""
    return Path(__file__).resolve().parent.parent


def _is_skipped(path):
    p = path.as_posix()
    for s in SKIP_DIRS:
        if f"/{s}/" in f"/{p}/" or p.endswith(f"/{s}"):
            return True
    return False


def list_files():
    """
    Return relative paths of all source files (for the picker / index).
    """
    root = project_root()
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        # prune skipped dirs in-place
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and d not in (".venv", ".git")]
        for fn in filenames:
            if fn in SKIP_FILES:
                continue
            f = Path(dirpath) / fn
            if _is_skipped(f):
                continue
            if f.suffix.lower() not in SOURCE_EXTS:
                continue
            rel = f.relative_to(root).as_posix()
            out.append(rel)
    return sorted(out)


def read_file(rel_path, max_bytes=MAX_FILE_SIZE):
    """
    Read a file's contents. Returns dict {ok, content, size, error}.
    Rel path is relative to project root.
    """
    # Prevent path traversal
    if ".." in rel_path or rel_path.startswith("/"):
        return {"ok": False, "error": "Invalid path", "content": ""}

    root = project_root()
    full = (root / rel_path).resolve()

    # Ensure the resolved path is still inside root
    try:
        full.relative_to(root.resolve())
    except ValueError:
        return {"ok": False, "error": "Path outside project", "content": ""}

    if not full.is_file():
        return {"ok": False, "error": f"Not found: {rel_path}", "content": ""}

    if full.name in SKIP_FILES:
        return {"ok": False, "error": "File excluded from AI reads", "content": ""}

    size = full.stat().st_size
    if size > max_bytes:
        return {"ok": False, "error": f"File too large ({size} bytes)", "content": ""}

    try:
        content = full.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"ok": False, "error": f"Read error: {e}", "content": ""}

    return {"ok": True, "content": content, "size": size}


def read_many(rel_paths, max_total=MAX_TOTAL_READ):
    """
    Read multiple files, capped at max_total bytes.
    Returns {path: content} for files that loaded.
    """
    out = {}
    total = 0
    for p in rel_paths:
        r = read_file(p)
        if not r["ok"]:
            continue
        chunk = r["content"]
        if total + len(chunk) > max_total:
            # Take partial to stay under budget
            remaining = max_total - total
            if remaining < 1000:
                break
            out[p] = chunk[:remaining] + f"\n\n# [truncated at {remaining} bytes]"
            total = max_total
            break
        out[p] = chunk
        total += len(chunk)
    return out


def guess_relevant_files(problem_text, limit=8):
    """
    Heuristic: match keywords in the problem statement to filenames.
    Returns list of relative paths.
    """
    text = problem_text.lower()
    all_files = list_files()

    # Keyword → file hints
    hints = {
        "product": ["app/models.py", "app/admin/routes.py", "app/templates/admin/product_edit.html"],
        "blog": ["app/blog/routes.py", "app/templates/blog/index.html", "app/templates/blog/detail.html"],
        "article": ["app/models.py", "app/admin/routes.py", "app/templates/admin/article_edit.html"],
        "wholesale": ["app/wholesale/auth.py", "app/wholesale/catalog.py", "app/models.py"],
        "cart": ["app/main/routes.py", "app/templates/cart.html"],
        "checkout": ["app/main/routes.py", "app/templates/checkout.html"],
        "order": ["app/models.py", "app/admin/routes.py", "app/orders.py"],
        "campaign": ["app/models.py", "app/campaigns.py", "app/admin/routes.py"],
        "tier": ["app/tiers.py", "app/models.py", "app/admin/routes.py"],
        "email": ["app/mail.py", "app/orders.py"],
        "telegram": ["app/telegram.py"],
        "ai": ["app/ai.py", "app/health.py"],
        "health": ["app/health.py", "app/templates/admin/assistant_health.html"],
        "template": ["app/templates/base.html", "app/templates/admin_base.html"],
        "navbar": ["app/templates/base.html"],
        "sidebar": ["app/templates/admin_base.html"],
        "campaign": ["app/campaigns.py", "app/models.py"],
        "hero": ["app/templates/index.html", "app/main/routes.py"],
        "carousel": ["app/templates/index.html"],
        "import": ["app/admin/routes.py", "app/templates/admin/import_uploads.html"],
        "invoice": ["app/models.py", "app/orders.py"],
        "seed": ["app/seed_data.py"],
        "route": ["app/main/routes.py", "app/admin/routes.py"],
    }

    picked = set()
    for kw, files in hints.items():
        if kw in text:
            for f in files:
                if f in all_files:
                    picked.add(f)

    # Also match any filename mentioned literally
    for f in all_files:
        base = f.split("/")[-1].lower()
        if base in text and len(base) > 3:
            picked.add(f)

    # Always include models and __init__ as context
    for f in ["app/models.py", "app/__init__.py"]:
        if f in all_files:
            picked.add(f)

    # Cap
    result = sorted(picked)[:limit]
    return result
