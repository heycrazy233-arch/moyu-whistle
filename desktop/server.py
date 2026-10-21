from __future__ import annotations

import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from database import AgentStore
from state import AgentEvent, AgentStatus


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 17321
DEFAULT_DB = Path(__file__).resolve().parents[1] / "work" / "agent-dock.sqlite3"
WEB_DIR = Path(__file__).resolve().parents[1] / "web"


class ApiError(ValueError):
    pass


def create_store(db_path: str | Path | None = None) -> AgentStore:
    return AgentStore(Path(db_path) if db_path else DEFAULT_DB)


def handle_event(store: AgentStore, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        event = AgentEvent.from_payload(payload)
    except ValueError as exc:
        allowed = ", ".join(status.value for status in AgentStatus)
        raise ApiError(f"Invalid event state. Use one of: {allowed}") from exc
    return store.record_event(event)


def create_fastapi_app(store: AgentStore):
    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles
    except ModuleNotFoundError:
        return None

    app = FastAPI(title="Agent Dock", version="0.1.0")
    app.mount("/assets", StaticFiles(directory=WEB_DIR / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def dashboard() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "service": "agent-dock", "version": "0.1.0"}

    @app.get("/api/agents")
    def agents() -> list[dict[str, Any]]:
        return store.list_agents()

    @app.get("/api/events")
    def events(limit: int = 50) -> list[dict[str, Any]]:
        return store.list_events(limit)

    @app.post("/api/events")
    def events_post(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return handle_event(store, payload)
        except ApiError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app


class AgentDockRequestHandler(BaseHTTPRequestHandler):
    store: AgentStore

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(WEB_DIR.resolve())
        except (FileNotFoundError, ValueError):
            self._send_json(404, {"error": "Not found"})
            return
        body = resolved.read_bytes()
        content_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self._send_file(WEB_DIR / "index.html")
            return
        if parsed.path.startswith("/assets/"):
            self._send_file(WEB_DIR / parsed.path.removeprefix("/"))
            return
        if parsed.path == "/health":
            self._send_json(200, {"ok": True, "service": "agent-dock", "version": "0.1.0"})
            return
        if parsed.path == "/api/agents":
            self._send_json(200, self.store.list_agents())
            return
        if parsed.path == "/api/events":
            limit = int(parse_qs(parsed.query).get("limit", ["50"])[0])
            self._send_json(200, self.store.list_events(limit))
            return
        self._send_json(404, {"error": "Not found"})

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/events":
            self._send_json(404, {"error": "Not found"})
            return
        length = int(self.headers.get("Content-Length") or "0")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            result = handle_event(self.store, payload)
        except (json.JSONDecodeError, ApiError, ValueError) as exc:
            self._send_json(400, {"error": str(exc)})
            return
        self._send_json(200, result)


def run_stdlib_server(store: AgentStore, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    AgentDockRequestHandler.store = store
    httpd = ThreadingHTTPServer((host, port), AgentDockRequestHandler)
    print(f"Agent Dock API listening on http://{host}:{port}")
    httpd.serve_forever()


def run_server(store: AgentStore, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    app = create_fastapi_app(store)
    if app is None:
        run_stdlib_server(store, host, port)
        return

    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="warning")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", default=DEFAULT_PORT, type=int)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    args = parser.parse_args()
    run_server(create_store(args.db), args.host, args.port)


if __name__ == "__main__":
    main()
