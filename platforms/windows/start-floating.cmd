@echo off
setlocal
for %%I in ("%~dp0\..\..") do set "MOYU_ROOT=%%~fI"
cd /d "%MOYU_ROOT%" || exit /b 1
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" start.py --floating
) else (
  py -3 start.py --floating
)
if errorlevel 1 pause
