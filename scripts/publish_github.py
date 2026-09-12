from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def github_request(path: str, token: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"https://api.github.com{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API failed: {exc.code} {body}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a GitHub repo and push Agent Dock.")
    parser.add_argument("--name", default="agent-dock")
    parser.add_argument("--description", default="Offline-first status center for remote coding agents.")
    parser.add_argument("--public", action="store_true")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("Set GITHUB_TOKEN or GH_TOKEN first.", file=sys.stderr)
        return 2

    repo = github_request(
        "/user/repos",
        token,
        {
            "name": args.name,
            "description": args.description,
            "private": not args.public,
            "auto_init": False,
        },
    )
    clone_url = repo["clone_url"]
    html_url = repo["html_url"]

    remotes = subprocess.run(
        ["git", "remote"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    if "origin" in remotes:
        run(["git", "remote", "set-url", "origin", clone_url])
    else:
        run(["git", "remote", "add", "origin", clone_url])
    run(["git", "push", "-u", "origin", "main"])
    print(html_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
