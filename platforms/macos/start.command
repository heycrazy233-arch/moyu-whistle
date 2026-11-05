#!/bin/sh
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd) || exit 1
cd -- "$ROOT" || exit 1
if [ -x .venv/bin/python ]; then
  exec .venv/bin/python start.py "$@"
fi
exec python3 start.py "$@"
