from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import threading
import time
import socket
import os
import math
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from database import AgentStore
from state import AgentEvent, AgentStatus
from settings import Settings, Monitor, in_window


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 17321
DEFAULT_DB = Path(__file__).resolve().parents[1] / "work" / "moyu-whistle.sqlite3"
WEB_DIR = Path(__file__).resolve().parents[1] / "web"


class ApiError(ValueError):
    pass


def local_request_allowed(host, origin):
    try:
        return (urlparse("http://" + host).hostname in ("127.0.0.1", "localhost", "::1")
                and (not origin or origin == "http://" + host))
    except ValueError:
        return False


def handle_collector(store, payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("server"), str) or not payload["server"]:
        raise ApiError("server is required")
    agents = payload.get("agents")
    if not isinstance(agents, list) or len(agents) > 500:
        raise ApiError("agents must be an array of at most 500 sessions")
    cleaned = []
    for agent in agents:
        if not isinstance(agent, dict) or not agent.get("session_id"):
            raise ApiError("session_id is required")
        try:
            event = AgentEvent.from_payload(dict(agent, server=payload["server"]))
        except (TypeError, ValueError) as exc:
            raise ApiError("Invalid agent event") from exc
        row = event.to_dict()
        row["agent_key"] = f"{event.server}:{event.agent_type}:{event.session_id}"
        for key in ("evidence", "presence"):
            row[key] = str(agent.get(key, "unknown"))[:100]
        row["status_known"] = agent.get("status_known") is True
        client = agent.get("client_type")
        row["client_type"] = client if event.agent_type == "codex" and client in ("desktop", "terminal", "vscode") else "unknown"
        try:
            row["last_activity"] = float(agent.get("last_activity", 0))
        except (TypeError, ValueError) as exc:
            raise ApiError("Invalid activity timestamp") from exc
        if not math.isfinite(row["last_activity"]) or row["last_activity"] < 0:
            raise ApiError("Invalid activity timestamp")
        cleaned.append(row)
    store.record_collector(payload["server"], cleaned)
    return {"ok": True, "count": len(cleaned)}


def create_store(db_path: str | Path | None = None) -> AgentStore:
    store = AgentStore(Path(db_path) if db_path else DEFAULT_DB)
    store.settings = Settings(store.db_path.with_suffix(".settings.json"))
    store.monitor = None
    return store


def settings_view(store):
    return {"settings": store.settings.get(), "monitor": store.monitor.status() if store.monitor else {"active": False, "sources": {}, "timezone": "", "running": False}}


def dashboard_agents(store):
    config = store.settings.get()
    sources = store.monitor.status()["sources"] if store.monitor else {}
    rows = store.list_agents()
    for row in rows:
        # Keep legacy storage/input compatible; the live task view has four states.
        if row["event"] == "done":
            row.update(event="idle", status_label="Idle", status_color="#60a5fa")
        source = row["server"]
        profiles = {"ssh:" + p["name"]: p for p in config["servers"]}
        paused = not in_window(config) or (source.startswith("ssh:") and not profiles.get(source, {}).get("enabled"))
        row["collection_paused"] = paused
        if "received_at" in row:
            row["collector_online"] = not paused and sources.get(source, {}).get("state") != "error" and time.time() - row["received_at"] < max(30, config["interval"] * 3 + 15)
    return rows


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

    app = FastAPI(title="Moyu Whistle", version="0.2.0-beta.1")

    @app.middleware("http")
    async def local_requests(request, call_next):
        from fastapi.responses import JSONResponse
        host = request.headers.get("host", "")
        origin = request.headers.get("origin")
        if not local_request_allowed(host, origin):
            return JSONResponse({"error": "Local same-origin access only"}, status_code=403)
        if request.method == "POST":
            if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
                return JSONResponse({"error": "JSON content type required"}, status_code=400)
            size = 0
            body = bytearray()
            async for chunk in request.stream():
                size += len(chunk)
                if size > 1_000_000:
                    return JSONResponse({"error": "Invalid request size"}, status_code=413)
                body.extend(chunk)
            request._body = bytes(body)
        return await call_next(request)
    app.mount("/assets", StaticFiles(directory=WEB_DIR / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def dashboard():
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "service": "moyu-whistle", "version": "0.2.0-beta.1"}

    @app.get("/api/agents")
    def agents() -> list[dict[str, Any]]:
        return dashboard_agents(store)

    @app.get("/api/settings")
    def settings_get():
        return settings_view(store)

    @app.post("/api/settings")
    def settings_post(payload: dict[str, Any]):
        try:
            store.settings.save(payload)
            return settings_view(store)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/events")
    def events(limit: int = 50) -> list[dict[str, Any]]:
        return store.list_events(limit)

    @app.post("/api/events")
    def events_post(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return handle_event(store, payload)
        except ApiError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/collectors")
    def collectors_post(payload: dict[str, Any]):
        try:
            return handle_collector(store, payload)
        except ApiError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app


class MoyuWhistleRequestHandler(BaseHTTPRequestHandler):
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
            if not resolved.is_file():
                raise ValueError("Not a file")
        except (OSError, ValueError):
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
        if not self._local_request():
            return
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self._send_file(WEB_DIR / "index.html")
            return
        if parsed.path.startswith("/assets/"):
            self._send_file(WEB_DIR / parsed.path.removeprefix("/"))
            return
        if parsed.path == "/health":
            self._send_json(200, {"ok": True, "service": "moyu-whistle", "version": "0.2.0-beta.1"})
            return
        if parsed.path == "/api/agents":
            self._send_json(200, dashboard_agents(self.store))
            return
        if parsed.path == "/api/settings":
            self._send_json(200, settings_view(self.store))
            return
        if parsed.path == "/api/events":
            try:
                limit = int(parse_qs(parsed.query).get("limit", ["50"])[0])
            except ValueError:
                self._send_json(400, {"error": "Invalid limit"})
                return
            self._send_json(200, self.store.list_events(limit))
            return
        self._send_json(404, {"error": "Not found"})

    def do_POST(self) -> None:
        if not self._local_request():
            return
        route = urlparse(self.path).path
        if route not in {"/api/events", "/api/collectors", "/api/settings"}:
            self._send_json(404, {"error": "Not found"})
            return
        try:
            if self.headers.get_content_type() != "application/json":
                raise ValueError("JSON content type required")
            length = int(self.headers.get("Content-Length") or "0")
            if not 0 < length <= 1_000_000:
                raise ValueError("Invalid request size")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if route == "/api/settings":
                self.store.settings.save(payload)
                result = settings_view(self.store)
            else:
                result = handle_collector(self.store, payload) if route == "/api/collectors" else handle_event(self.store, payload)
        except (json.JSONDecodeError, ApiError, ValueError, TypeError) as exc:
            self._send_json(400, {"error": str(exc)})
            return
        self._send_json(200, result)

    def _local_request(self):
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        if not local_request_allowed(host, origin):
            self._send_json(403, {"error": "Local same-origin access only"})
            return False
        return True


def run_stdlib_server(store: AgentStore, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    MoyuWhistleRequestHandler.store = store
    httpd = ThreadingHTTPServer((host, port), MoyuWhistleRequestHandler)
    print(f"Moyu Whistle API listening on http://{host}:{port}")
    httpd.serve_forever()


def run_server(store: AgentStore, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    if host not in ("127.0.0.1", "localhost"):
        raise ValueError("Only IPv4 loopback binding is supported; use SSH for remote collection")
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
    parser.add_argument("--collect", action="store_true", help="Collect this machine's real Codex and Claude sessions")
    args = parser.parse_args()
    store = create_store(args.db)
    if args.collect:
        sys.path.insert(0, str(WEB_DIR.parent / "remote"))
        from collector import Collector
        collector = Collector(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")),
                              os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude")),
                              store.local_source(socket.gethostname()))

        store.monitor = Monitor(store.settings, collector, store, handle_collector)
        store.monitor.start()
    try:
        run_server(store, args.host, args.port)
    finally:
        if store.monitor:
            store.monitor.stop.set()


if __name__ == "__main__":
    main()
