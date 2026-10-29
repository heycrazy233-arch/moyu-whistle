# Contributing

Use Python 3.11+ in a virtual environment. Keep changes on a branch. Run:

```sh
python -m unittest discover -s tests
node floating/check-whistle.cjs
python scripts/release_check.py
```

Install desktop dependencies separately. Tests must not inject synthetic agents
into the real service or accept user approvals. Keep docs/architecture.md and
all UI clients aligned. Record OS/version and actual integration verification.
Do not claim a fixture passing proves a real agent works.

Never commit runtime data, environments, credentials, transcripts or recordings.
Artwork requires separate distribution rights. Code licensing is pending the
owner's decision; do not assume redistribution rights without a license.
