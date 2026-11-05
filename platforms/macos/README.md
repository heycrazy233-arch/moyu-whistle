# macOS adapter

This is the verified platform for the current release.

- `start.command`: launches the shared browser/API service.
- `open-floating.command`: launches the shared PySide6 floating window.
- Codex open-session discovery uses `lsof` against writer-lock files.
- Native window, tray, animation and notification behavior has local macOS
  verification coverage.

The root launchers delegate here for compatibility. Keep the existing
`remote/collector.py` path stable because installed Codex hooks use its absolute
path.
