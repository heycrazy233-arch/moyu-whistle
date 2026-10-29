# Beta release checklist

- [ ] Python tests on Windows/macOS/Linux, Python 3.11 and 3.13.
- [ ] FastAPI and standard-library server tests.
- [ ] Native floating-window tests on real Windows/macOS displays.
- [ ] Real local and POSIX SSH remote agent tests with recorded versions.
- [ ] Human approval, completion, rejection, interrupt and reconnect tests.
- [ ] Async question correlation independently verified before claiming support.
- [ ] scripts/release_check.py and staged diff reviewed for private data.
- [ ] License and separate artwork distribution permission confirmed.
- [ ] Repository visibility unchanged unless explicitly requested.
- [ ] Pushed commit and actual GitHub Actions results verified.

Remaining gaps prevent a stable/production-ready designation. Creating this
checklist or a CI workflow does not count as passing it.
