# Codex approval observer

Install definitions with `python3 remote/install_codex_hooks.py`. Existing hooks
are preserved and backed up. This does not change permission policy or trust
records. Review the added definitions in Codex `/hooks`; new/changed definitions
will not run until the user trusts them. Reopen/resume the CLI if its hook browser
does not pick up the new configuration. Already-open prompts are not replayed.

The command hook emits no output or decision. PermissionRequest writes a small
pending record; PostToolUse removes the matching request. Input is capped at 1 MB,
and only session/turn IDs, a SHA-256 correlation digest and time are stored in
CODEX_HOME/moyu-whistle-hooks.sqlite3. A bounded `hook_receipts` table (256 rows) holds
only session ID, event type, callback time and whether a completion matched a
pending request. It contains no input/output text or approval decisions.
Oversized input is ignored. The observer must
never approve, deny, rewrite tools, inject prompts or call a model.

This is a partial integration, not a verified complete approval lifecycle:

- With the log adapter enabled, current-turn `approvals_reviewer=auto_review` or
  `approval_policy=never` prevents PermissionRequest from becoming human Waiting.
  The context is internal and is not sent in API snapshots. Older-turn pending
  records cannot override an identified current turn. This does not observe an
  explicit fallback from automatic review to a human prompt; that needs its own
  signal. Metadata-only mode or logs without reviewer context lack this filter.
- PermissionRequest can precede automatic decisions by other hooks; those decisions
  are not directly observed.
- PostToolUse arrives after a tool produces output, not at approval time. A long
  running approved command may remain Waiting until its result is observed.
- Rejection without PostToolUse is cleared only at an observed turn boundary or
  new submission.
- Stop callbacks can request continuation elsewhere; later lifecycle/log evidence
  takes precedence. Concurrent turns and multiple independent clients need real
  validation beyond isolated unit tests.
- Hooks must be configured on each remote machine if used there. The standalone
  collector file includes the reader; copying it alone does not install hooks.

2026-10-28 matching correction: Bash and apply_patch now use a versioned digest of
the tool name and command, excluding approval-only descriptions. Other tools keep
their full argument identity (an MCP `description` can be a real argument).
Matching is scoped to a session and turn; repeated identical requests are counted
and each completion consumes only one. This fixes the reproducible case where an
approval description made completion hashes differ. It does not observe the
instant of human approval and must not be presented as that separate fix.

Existing pending rows are preserved during migration. Exact legacy matches can
still clear them; unmatched legacy hashes cannot be reconstructed and remain
until a normal lifecycle cleanup. No production records are manually cleared and
no timeout fabricates a decision. The hook command/config and trust records are
unchanged by this code update. Real callback matching was observed after the
update; a fresh human approval with a long-running command is still required.

Acceptance must use a real harmless approval prompt after trusting the hook:
verify Waiting, then a human approval/rejection, and verify subsequent state.
No approvals are performed by this tool or by its tests. Tests use temporary
directories and do not create fake production agents.

Reference: https://developers.openai.com/codex/hooks
