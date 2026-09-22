#!/usr/bin/env python3
"""Cross-platform launcher for PC Parts Desk (Linux + Windows)."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
VENV_DIR = BACKEND / ".venv"
REQ = BACKEND / "requirements.txt"
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"


def venv_python() -> Path:
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def venv_uvicorn() -> Path:
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "uvicorn.exe"
    return VENV_DIR / "bin" / "uvicorn"


def ensure_venv() -> None:
    py = venv_python()
    if not py.exists():
        print("Creating Python venv…")
        subprocess.check_call([sys.executable, "-m", "venv", str(VENV_DIR)])
        pip = [
            str(py),
            "-m",
            "pip",
            "install",
            "-r",
            str(REQ),
        ]
        subprocess.check_call(pip)
    else:
        # Keep deps present without forcing reinstall every launch
        pass


def ensure_frontend() -> None:
    if not (FRONTEND / "node_modules").exists():
        print("Installing frontend dependencies…")
        npm = shutil.which("npm")
        if not npm:
            sys.exit("npm not found — install Node.js 20+ from https://nodejs.org")
        subprocess.check_call([npm, "install"], cwd=FRONTEND)


def ensure_env() -> None:
    if not ENV_FILE.exists() and ENV_EXAMPLE.exists():
        ENV_FILE.write_text(ENV_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
        print("Created .env from .env.example — edit OLLAMA_URL if needed.")


def main() -> None:
    if not shutil.which("node") and not shutil.which("npm"):
        sys.exit("Node.js / npm not found — install Node.js 20+")

    ensure_venv()
    ensure_frontend()
    ensure_env()

    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND) + os.pathsep + env.get("PYTHONPATH", "")

    uvicorn = venv_uvicorn()
    if not uvicorn.exists():
        # fallback: python -m uvicorn
        back_cmd = [
            str(venv_python()),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
        ]
    else:
        back_cmd = [
            str(uvicorn),
            "app.main:app",
            "--app-dir",
            str(BACKEND),
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
        ]

    print("Starting API on http://127.0.0.1:8765 …")
    backend = subprocess.Popen(
        back_cmd,
        cwd=ROOT if uvicorn.exists() else BACKEND,
        env=env,
    )

    npm = shutil.which("npm")
    assert npm
    print("Starting UI on http://127.0.0.1:5173 …")
    frontend = subprocess.Popen(
        [npm, "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173"],
        cwd=FRONTEND,
    )

    def shutdown(*_args: object) -> None:
        for proc in (frontend, backend):
            if proc.poll() is None:
                proc.terminate()
        time.sleep(0.5)
        for proc in (frontend, backend):
            if proc.poll() is None:
                proc.kill()
        sys.exit(0)

    if sys.platform != "win32":
        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)

    try:
        while True:
            if backend.poll() is not None:
                print("Backend exited with", backend.returncode)
                shutdown()
            if frontend.poll() is not None:
                print("Frontend exited with", frontend.returncode)
                shutdown()
            time.sleep(0.5)
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()
