# Common contracts

The common core is authoritative for both macOS and Windows:

1. The service binds only to `127.0.0.1:17321`.
2. The visible states are Working, Waiting, Error and Idle.
3. Collection is deterministic and stores only the minimum status metadata.
4. SQLite schema and HTTP payloads are identical on every platform.
5. The browser UI under `web/` is the baseline interface on every platform.
6. Hooks observe lifecycle events and never approve commands.

Platform launchers may select executables and process flags, but must delegate
to `start.py`. Platform discovery may determine whether a session is open, but
must return the common collector payload and must not read prompt or tool text.
