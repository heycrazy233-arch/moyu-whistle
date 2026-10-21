"""Validated local monitoring preferences and SSH snapshot polling."""
import copy
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import threading
import time


DEFAULT = {"enabled": True, "interval": 15, "scheduled": False,
           "start": "09:00", "end": "18:00", "allow_logs": False, "servers": []}


def validate(value):
    if not isinstance(value, dict):
        raise ValueError("Settings must be an object")
    result = copy.deepcopy(DEFAULT)
    for key in ("enabled", "scheduled", "allow_logs"):
        if type(value.get(key)) is not bool:
            raise ValueError(f"Invalid {key}")
        result[key] = value[key]
    interval = value.get("interval")
    if type(interval) is not int or not 5 <= interval <= 3600:
        raise ValueError("Interval must be 5–3600 seconds")
    result["interval"] = interval
    for key in ("start", "end"):
        if not isinstance(value.get(key), str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value[key]):
            raise ValueError("Invalid time")
        result[key] = value[key]
    if result["scheduled"] and result["start"] == result["end"]:
        raise ValueError("Start and end must differ; disable the schedule for all-day collection")
    servers = value.get("servers")
    if not isinstance(servers, list) or len(servers) > 8:
        raise ValueError("At most 8 SSH servers")
    names = set()
    for row in servers:
        if not isinstance(row, dict):
            raise ValueError("Invalid server")
        name, host, script = (row.get(k, "") for k in ("name", "host", "script"))
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}", name) or name in names:
            raise ValueError("Server names must be unique simple aliases")
        if not isinstance(host, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.@:\[\]-]{0,253}", host):
            raise ValueError("Use an SSH alias or user@host (port has a separate field)")
        if not isinstance(script, str) or not re.fullmatch(r"[A-Za-z0-9_/][A-Za-z0-9_./-]{0,250}\.py", script):
            raise ValueError("Collector path must be a plain .py path, relative to the remote home or absolute")
        port = row.get("port")
        if type(port) is not int or not 1 <= port <= 65535 or type(row.get("enabled")) is not bool:
            raise ValueError("Invalid SSH port or enabled flag")
        names.add(name)
        result["servers"].append(dict(name=name, host=host, port=port, script=script, enabled=row["enabled"]))
    return result


def in_window(settings, now=None):
    if not settings["enabled"]:
        return False
    if not settings["scheduled"]:
        return True
    current = (now or datetime.now()).strftime("%H:%M")
    start, end = settings["start"], settings["end"]
    return start <= current < end if start < end else current >= start or current < end


class Settings:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.value = copy.deepcopy(DEFAULT)
        if self.path.exists():
            self.value = validate(json.loads(self.path.read_text(encoding="utf-8")))

    def get(self):
        with self.lock:
            return copy.deepcopy(self.value)

    def save(self, value):
        value = validate(value)
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(".tmp")
            temp.write_text(json.dumps(value, indent=2), encoding="utf-8")
            os.replace(temp, self.path)
            self.value = value
        return self.get()


def ssh_command(profile, allow_logs):
    remote = ["python3", profile["script"], "--snapshot", "--server", profile["name"]]
    if not allow_logs:
        remote.append("--metadata-only")
    return ["ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "ConnectTimeout=5", "-o", "ConnectionAttempts=1", "-p", str(profile["port"]),
            profile["host"], " ".join(shlex.quote(part) for part in remote)]


class Monitor:
    def __init__(self, settings, collector, store, ingest):
        self.settings, self.collector, self.store, self.ingest = settings, collector, store, ingest
        self.stop = threading.Event()
        self.guard = threading.Lock()
        self.states = {}
        self.threads = []

    def start(self):
        for slot in range(-1, 8):
            thread = threading.Thread(target=self.worker, args=(slot,), daemon=True)
            thread.start()
            self.threads.append(thread)

    def status(self):
        config = self.settings.get()
        names = {self.collector.server} | {"ssh:" + p["name"] for p in config["servers"]}
        with self.guard:
            states = {name: copy.deepcopy(state) for name, state in self.states.items() if name in names}
        return {"active": in_window(config), "timezone": datetime.now().astimezone().tzname(), "sources": states}

    def worker(self, slot):
        due, previous = 0, None
        while not self.stop.wait(1):
            config = self.settings.get()
            profile = config["servers"][slot] if slot >= 0 and slot < len(config["servers"]) else None
            if slot >= 0 and profile is None:
                continue
            name = self.collector.server if slot == -1 else "ssh:" + profile["name"]
            signature = (config["interval"], config["allow_logs"], config["enabled"], config["scheduled"], config["start"], config["end"], str(profile))
            if signature != previous:
                due, previous = 0, signature
            if not in_window(config) or (profile and not profile["enabled"]):
                with self.guard:
                    self.states[name] = {"state": "paused"}
                due = 0
                continue
            if time.monotonic() < due:
                continue
            began = time.monotonic()
            try:
                if profile:
                    result = subprocess.run(ssh_command(profile, config["allow_logs"]), capture_output=True,
                                            text=True, timeout=12)
                    if result.returncode:
                        raise ValueError("SSH failed: check host trust, key authentication and collector path")
                    if len(result.stdout) > 1_000_000:
                        raise ValueError("Remote response too large")
                    agents = json.loads(result.stdout)
                else:
                    self.collector.metadata_only = not config["allow_logs"]
                    agents = self.collector.scan()
                # Ignore results arriving after schedule/config changes.
                if self.settings.get() != config or not in_window(config):
                    continue
                self.ingest(self.store, {"server": name, "agents": agents})
                state = {"state": "online", "duration_ms": round((time.monotonic() - began) * 1000),
                         "last_checked": time.time(), "count": len(agents)}
            except Exception as exc:
                state = {"state": "error", "error": "SSH authentication, host trust, collector version or network error" if profile else type(exc).__name__}
            with self.guard:
                self.states[name] = state
            due = time.monotonic() + config["interval"]
