#!/usr/bin/env python3
"""
Find a free TCP port and write FLASK_PORT + FLASK_RUN_PORT to .env.
FLASK_RUN_PORT is what `flask run` reads. FLASK_PORT is what run.py reads
when you use `python run.py`.
"""
import socket
import subprocess
import re
import sys
from pathlib import Path

RESERVED = {
    22, 25, 53, 80, 139, 443, 445, 631, 1716,
    3306, 5000, 5001, 5002, 5357, 5432,
    6379, 8000, 8080, 8081, 9000, 9004, 9090,
    27017, 8787,  # your other project ports visible in ps
}
PORT_RANGE = range(5003, 5100)


def get_listening_ports():
    """Return set of TCP ports currently in LISTEN state."""
    listening = set()
    try:
        result = subprocess.run(
            ["ss", "-tlnH"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 4:
                    match = re.search(r":(\d+)$", parts[3])
                    if match:
                        listening.add(int(match.group(1)))
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return listening


def is_port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def write_env(port):
    """Idempotently set FLASK_PORT and FLASK_RUN_PORT in .env."""
    env_path = Path(".env")
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    keys = {"FLASK_PORT": str(port), "FLASK_RUN_PORT": str(port)}
    seen = set()
    new_lines = []
    for line in lines:
        key = line.split("=", 1)[0] if "=" in line else None
        if key in keys:
            new_lines.append(f"{key}={keys[key]}")
            seen.add(key)
        else:
            new_lines.append(line)
    for k, v in keys.items():
        if k not in seen:
            new_lines.append(f"{k}={v}")
    env_path.write_text("\n".join(new_lines) + "\n")


def main():
    listening = get_listening_ports()
    print(f"🔍 Detected {len(listening)} ports in LISTEN state")

    for port in PORT_RANGE:
        if port in RESERVED or port in listening:
            continue
        if not is_port_free(port):
            continue
        print(f"\n✅ Free port found: {port}")
        write_env(port)
        print(f"📝 Written FLASK_PORT={port} and FLASK_RUN_PORT={port} to .env")
        print(f"\nStart the app with either:")
        print(f"   python run.py")
        print(f"   flask --app run run --debug    (reads FLASK_RUN_PORT)")
        return 0

    print("\n❌ No free port found in range 5003–5099")
    sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
