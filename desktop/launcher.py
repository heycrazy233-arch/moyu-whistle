from __future__ import annotations

import argparse
import threading

from cli_ui import run_console_ui
from server import DEFAULT_DB, DEFAULT_HOST, DEFAULT_PORT, create_store, run_server
from ui import pyside_available, run_desktop_ui


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--console", action="store_true")
    args = parser.parse_args()

    store = create_store(args.db)
    server_thread = threading.Thread(
        target=run_server,
        args=(store, args.host, args.port),
        daemon=True,
    )
    server_thread.start()

    if args.console or not pyside_available():
        run_console_ui(store)
        return
    run_desktop_ui(store)


if __name__ == "__main__":
    main()
