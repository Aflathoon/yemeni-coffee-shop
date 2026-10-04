#!/usr/bin/env python3
"""Helper: generate + apply migrations. Usage: python migrate.py "message"."""
import sys, subprocess
from pathlib import Path

msg = sys.argv[1] if len(sys.argv) > 1 else "auto migration"

if not Path("migrations").exists():
    print("→ Initializing migrations/")
    subprocess.run(["flask", "--app", "run", "db", "init"], check=True)

print(f"→ Generating migration: {msg}")
subprocess.run(["flask", "--app", "run", "db", "migrate", "-m", msg], check=True)

print("→ Applying migration")
subprocess.run(["flask", "--app", "run", "db", "upgrade"], check=True)

print("✅ Done")
