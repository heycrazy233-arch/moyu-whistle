# Platform layout

The product keeps one common core and thin operating-system entry points.
Platform directories must not fork the API, database schema, state model or web
UI. A platform adapter should be added only when the operating system requires
different process discovery, launch behavior or packaging.

## Common

- `web/`: browser dashboard and settings UI; shared by macOS and Windows.
- `desktop/`: localhost API, SQLite storage, scheduler and SSH polling.
- `remote/`: deterministic Codex/Claude collector, hooks and SSH bridge.
- `floating/`: PySide6 floating window and Guada companion; shared source,
  platform-specific verification and packaging.
- `pet/`: optional user-supplied visual assets and manifest contract.
- `start.py`: shared Python entry point and diagnostics.
- `tests/`: shared deterministic tests.

See `common/README.md` for the contracts that platform code must preserve.

## macOS

`macos/` contains Finder-friendly launchers. The currently verified release is
macOS-only. Root `.command` files remain compatibility wrappers, so existing
instructions and shortcuts continue to work.

## Windows

`windows/` contains CMD/PowerShell entry points and the Windows validation
checklist. Root `.cmd` remains a compatibility wrapper. Windows reuses the same
web/API/database/collector code; it must not grow a second implementation of
those components.

Windows support is still under active adaptation until the checklist in
`windows/README.md` is completed on real Windows machines.
