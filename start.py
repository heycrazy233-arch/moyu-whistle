"""Portable entry point for Moyu Whistle; no automatic installation or approvals."""
import argparse
import importlib.util
import json
import platform
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def doctor():
    result = {
        "product": "moyu-whistle", "python": platform.python_version(),
        "python_supported": sys.version_info >= (3, 11), "platform": platform.system(),
        "ssh_available": shutil.which("ssh") is not None,
        "lsof_available": shutil.which("lsof") is not None,
        "fastapi_available": importlib.util.find_spec("fastapi") is not None,
        "desktop_available": importlib.util.find_spec("PySide6") is not None,
    }
    print(json.dumps(result, indent=2))
    return 0 if result["python_supported"] else 1


def main():
    parser = argparse.ArgumentParser(description="Moyu Whistle local agent monitor")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--doctor", action="store_true")
    modes.add_argument("--background", action="store_true")
    modes.add_argument("--floating", action="store_true")
    modes.add_argument("--install-hooks", action="store_true")
    args = parser.parse_args()
    if args.doctor:
        return doctor()
    if sys.version_info < (3, 11):
        parser.error("Python 3.11 or newer is required for this release")
    if args.install_hooks:
        script, extra = "remote/install_codex_hooks.py", []
    elif args.floating:
        if importlib.util.find_spec("PySide6") is None:
            parser.error("Install floating/requirements.txt in this Python environment first")
        result = subprocess.call([sys.executable, str(ROOT / "desktop/background.py")], cwd=ROOT)
        if result:
            return result
        script, extra = "floating/main.py", []
    elif args.background:
        script, extra = "desktop/background.py", []
    else:
        script, extra = "desktop/server.py", ["--collect"]
        print("Moyu Whistle: http://127.0.0.1:17321/ (Ctrl+C to stop)", flush=True)
    try:
        return subprocess.call([sys.executable, str(ROOT / script), *extra], cwd=ROOT)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
