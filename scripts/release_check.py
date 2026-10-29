"""Audit distributable source files; never print potential secret contents."""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    names = subprocess.check_output(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=ROOT)
    problems = []
    paths = set(names.decode().split("\0")) - {""}
    for name in sorted(paths):
        path = ROOT / name
        if not path.is_file():
            continue
        if (path.suffix.lower() in ('.sqlite3', '.db', '.mov', '.part', '.pem', '.key', '.log')
                or name.startswith(('work/', '.venv/', '.venv-floating/')) or path.name == '.env'):
            problems.append((name, 'runtime/private artifact'))
            continue
        if path.stat().st_size > 2_000_000:
            problems.append((name, 'large artifact requires explicit release review'))
            continue
        try:
            source = path.read_text(encoding='utf-8')
        except UnicodeError:
            problems.append((name, 'binary artifact requires distribution review'))
            continue
        patterns = (r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
                    r'\b(?:ghp_|github_pat_)[A-Za-z0-9_]{30,}',
                    r'/Users/[A-Za-z0-9_.-]+/', r'C:\\Users\\[A-Za-z0-9_.-]+\\')
        if any(re.search(pattern, source) for pattern in patterns):
            problems.append((name, 'potential credential or personal absolute path'))
    for name, reason in problems:
        print(f'REVIEW {name}: {reason}')
    print(f'Release source audit: {len(problems)} issue(s). Manual review is still required.')
    return bool(problems)


if __name__ == '__main__':
    raise SystemExit(main())
