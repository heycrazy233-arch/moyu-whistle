"""Inspect or rename the existing origin repository without printing credentials."""
import argparse
import json
import os
import re
import subprocess
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rename", action="store_true")
    args = parser.parse_args()
    remote = subprocess.check_output(["git", "remote", "get-url", "origin"], text=True).strip()
    parsed = urlparse(remote)
    if parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.username:
        raise SystemExit("Expected a credential-free https://github.com origin")
    slug = parsed.path.strip("/").removesuffix(".git")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", slug):
        raise SystemExit("Invalid origin repository")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        result = subprocess.run(["git", "credential", "fill"], input=f"url={remote}\n\n",
                                text=True, capture_output=True, timeout=30,
                                env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
        fields = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        token = fields.get("password")
    if not token:
        raise SystemExit("No GitHub credential available; configure Git authentication first")
    def api(path, payload=None):
        req = Request("https://api.github.com" + path,
                      data=json.dumps(payload).encode() if payload is not None else None,
                      method="PATCH" if payload is not None else "GET",
                      headers={"Authorization":f"Bearer {token}", "Accept":"application/vnd.github+json",
                               "Content-Type":"application/json", "X-GitHub-Api-Version":"2022-11-28"})
        try:
            with urlopen(req, timeout=20) as response:
                return json.load(response)
        except HTTPError as exc:
            raise SystemExit(f"GitHub returned HTTP {exc.code}; verify repository permissions/scopes") from None
    repo = api("/repos/" + slug)
    print(json.dumps({k:repo.get(k) for k in ("full_name", "private", "default_branch", "permissions")}, indent=2))
    if args.rename:
        if not repo.get("permissions", {}).get("admin"):
            raise SystemExit("Repository admin permission is required for renaming")
        repo = api("/repos/" + repo["full_name"], {"name":"moyu-whistle"})
        subprocess.run(["git", "remote", "set-url", "origin", repo["clone_url"]], check=True)
        print("Renamed repository: " + repo["html_url"])


if __name__ == "__main__":
    main()
