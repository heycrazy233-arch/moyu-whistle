#!/bin/zsh
ROOT="${0:A:h}/../.."
cd -- "$ROOT" || exit 1
if [[ ! -x .venv-floating/bin/python ]]; then
  print '请先按 floating/README.md 安装桌面依赖。'
  read '?按回车关闭'
  exit 1
fi
exec .venv-floating/bin/python floating/main.py
