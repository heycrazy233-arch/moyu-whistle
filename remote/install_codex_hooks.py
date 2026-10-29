"""Install observer definitions, never trust or approve them on the user's behalf."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time


def install(home):
    home = Path(home)
    path = home/'hooks.json'
    value = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(value, dict) or not isinstance(value.get('hooks', {}), dict):
        raise ValueError('Unsupported existing hooks configuration')
    hooks = value.setdefault('hooks', {})
    argv = [sys.executable, str(Path(__file__).with_name('collector.py').resolve()),
            '--hook', '--codex-home', str(home.resolve())]
    command = subprocess.list2cmdline(argv) if os.name == 'nt' else shlex.join(argv)
    for event in ('PermissionRequest', 'PostToolUse', 'UserPromptSubmit', 'Stop', 'Interrupt', 'SessionEnd'):
        entries = hooks.setdefault(event, [])
        if not isinstance(entries, list):
            raise ValueError('Unsupported existing hook event')
        if not any(handler.get('command') == command for group in entries
                   for handler in group.get('hooks', [])):
            entries.append({'hooks':[{'type':'command', 'command':command, 'timeout':2}]})
    home.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, home/f'hooks.json.moyu-whistle-backup-{time.time_ns()}')
    temporary = path.with_suffix('.moyu-whistle.tmp')
    temporary.write_text(json.dumps(value, indent=2)+'\n', encoding="utf-8")
    temporary.replace(path)
    print('Observer definitions installed. Review and trust them using /hooks in Codex.')


if __name__ == '__main__':
    install(os.environ.get('CODEX_HOME', str(Path.home()/'.codex')))
