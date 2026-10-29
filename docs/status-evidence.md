# Status evidence audit

Date: 2026-10-21. This is an implementation boundary, not a claim that every
agent version supports all four desired task states.

## Reproduced CLI approval misclassification

On 2026-10-21 the user reported an interactive CLI command-approval prompt
while the dashboard showed working. A targeted read of that session confirmed
the matching command was a response_item/custom_tool_call without a matching
output. The last lifecycle event was task_started. LogReader consumes only
task_started/task_complete/turn_aborted for task classification, so it retained
working. This is a missing approval observation channel, not an idle timeout or
a frontend enum bug. No approval was accepted or rejected during diagnosis.

An outstanding tool call is not sufficient proof of waiting: an executing command
has the same absence of a result. Do not add a timeout or command-text heuristic.
The inspected runtime diagnostic records and thread database schema did not
establish a reliable pending-approval/decision pair for this session.

The installed CLI reports hooks enabled, and the current official
[Codex hooks documentation](https://developers.openai.com/codex/hooks) describes
PermissionRequest. However, detecting a request alone is insufficient: integration
must also verify approval resolution, long-running execution, rejection and
concurrent requests on this installed version. PostToolUse occurs after output,
not immediately after permission is granted. No hook installation or automatic
approval behavior was added. This issue remains unresolved in production.

## Current passive adapters

| Source | Accepted evidence | Result | Limit |
| --- | --- | --- | --- |
| Codex rollout | task_started | working | Last observed task event, not CPU activity |
| Codex rollout | task_complete | done | Turn completion, not proof of successful project delivery |
| Codex rollout | turn_aborted | idle + Turn interrupted message | Not done or task failure |
| Claude session status | explicit working/running/busy, waiting, error, done, idle | Corresponding state | Depends on installed version providing the status file |
| Missing or unsupported status | no recognized signal | status_known=false | Never infer waiting from silence |

Recent local Codex logs contained task_started, task_complete and turn_aborted;
this sample did not establish approval-wait or terminal-failure log events.
The audit printed only event type counts and field names, not message bodies,
tool arguments, identifiers or project paths. Local Claude session files exposed
status/statusUpdatedAt and process identity; the observed status was idle.
Tests for the other Claude values validate mappings, not real lifecycle delivery.

The log reader now associates terminal events with the most recently observed
turn ID when both IDs are available. Delayed completion/interruption from another
turn is ignored. Older records without IDs still use file order for compatibility.
Replaced/truncated logs reset the reader. Malformed record shapes are skipped.
Tool output errors, agent prose and unclassified error events do not imply a
terminal task failure. These boundaries have isolated regression tests.

## Signals requiring a separate integration

[Codex App Server documentation](https://developers.openai.com/codex/app-server)
documents thread/status/changed with waitingOnApproval and turn/completed with
completed, interrupted or failed. This is a runtime protocol, not the rollout
JSONL schema. Launching another app-server does not establish observation of
threads running in an existing process. No new app-server was started, no
thread was resumed, and no model request was made in this audit.

[Claude hook documentation](https://code.claude.com/docs/en/hooks) distinguishes
permission requests, tool failures and StopFailure (a turn ending on API error).
Hooks require version checking and an explicitly configured adapter. A tool
failure alone must not mark the whole task failed. Stop hooks can participate in
continuation decisions, so receiving one is not always proof of final termination.
No hooks were installed or user agent settings modified in this iteration.

## Frontend contract and remaining acceptance

No API fields, enum values or SQLite schema changed. Keep idle for compatibility
until frontend/backend agree on a separate lifecycle detail for not-started and
interrupted sessions. The desired four primary states are working/waiting/error/done;
unknown, paused and disconnected belong to observation status, not task outcomes.

Still required: real approval/request-response transitions, genuine terminal
failures vs successful retry, interruption, reconnect and multi-turn races for
both agents. Do not deliberately cause credential/billing errors or modify user
tasks to generate fixtures. Windows, real SSH and a long resource soak are pending.
Use temporary isolated fixtures for unit tests; never write simulated sessions
into the production dashboard.
