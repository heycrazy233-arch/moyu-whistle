"""Start the local backend independently of the invoking terminal session."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import ProxyHandler, build_opener


ROOT = Path(__file__).resolve().parents[1]


def healthy():
    try:
        with build_opener(ProxyHandler({})).open('http://127.0.0.1:17321/health', timeout=1) as response:
            value = json.load(response)
            return value.get('ok') is True and value.get('service') == 'moyu-whistle'
    except (OSError, ValueError):
        return False


def main():
    if healthy():
        print('Moyu Whistle is already available at http://127.0.0.1:17321/')
        return
    work = ROOT/'work'
    work.mkdir(exist_ok=True)
    log = work/'backend.log'
    options = ({'creationflags': subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
               if os.name == 'nt' else {'start_new_session': True})
    with log.open('ab') as stream:
        process = subprocess.Popen([sys.executable, '-u', str(ROOT/'desktop/server.py'), '--collect'],
                                   cwd=ROOT, stdin=subprocess.DEVNULL, stdout=stream, stderr=stream,
                                   close_fds=True, **options)
    for _ in range(20):
        if process.poll() is not None:
            raise SystemExit(f'Backend exited ({process.returncode}); see {log}')
        if healthy():
            (work/'backend.pid').write_text(str(process.pid)+'\n')
            print(f'Moyu Whistle ready: http://127.0.0.1:17321/ (PID {process.pid}); log: {log}')
            return
        time.sleep(0.25)
    raise SystemExit(f'Health check timed out; backend PID {process.pid} may still be starting. See {log}')


if __name__ == '__main__':
    main()
