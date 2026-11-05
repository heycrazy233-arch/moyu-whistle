# Windows adapter

Windows reuses the common browser UI, localhost API, SQLite database, state
model, hooks and collector. The files in this directory only handle Windows
launching and validation.

## Entry points

- `start.cmd`: start the browser/API service.
- `start-floating.cmd`: start the optional PySide6 floating window.
- `doctor.ps1`: check Python, OpenSSH, paths and shared diagnostics without
  changing the machine.

The root `Start Moyu Whistle.cmd` delegates to `start.cmd`.

## What still needs real Windows validation

- Verify Codex writer-lock detection with desktop and terminal Codex. The code
  now uses the Win32 sharing violation rather than `lsof`.
- Install/review hooks and verify Waiting -> Working/Idle transitions.
- Verify Claude Code's actual session-status location and lifecycle.
- Exercise PySide6 transparency, always-on-top behavior, tray restoration,
  multi-monitor scaling and animated GIF pause/resume.
- Measure five-second polling CPU, disk I/O and handle use over a workday.
- Package a signed installer only after source-mode validation passes.
- SSH polling currently targets POSIX remotes. A Windows PowerShell remote
  collector still needs a separately validated command adapter.

Until these checks pass, Windows is a development target, not a supported
release.
