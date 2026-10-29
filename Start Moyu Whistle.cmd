@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" start.py %*
) else (
  py -3 start.py %*
)
if errorlevel 1 pause
