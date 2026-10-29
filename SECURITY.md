# Security

Single-user local Beta, not a multi-user service. The unauthenticated API binds
only to IPv4 loopback. Do not expose it to a LAN/public proxy. Host/Origin checks
do not authenticate local programs; another local process can change settings
or submit state. No production security audit has been completed.

Default collection avoids transcripts. Explicit log compatibility parses local
records but does not retain prompt/answer/tool-output text. Snapshots may contain
project paths. Hook digests are not encryption and can be guessable.

SSH uses existing keys, known_hosts, BatchMode and strict host checks. Remote
scripts are trusted code executed as your remote user; review them. No remote
password storage or automatic host trust changes are implemented.

Review hooks in Codex. Never bypass approval/trust policies for monitoring.
Updating this checkout changes the code invoked by an existing Hook; review
updates before running. Report vulnerabilities privately to the owner, without
credentials, full logs, conversations or local databases. No response SLA yet.
