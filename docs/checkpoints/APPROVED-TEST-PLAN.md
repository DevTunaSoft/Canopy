# Independent track C — approved-commit test-plan gate

This independent, low-dependency module provides a small building block for an unattended Mint VM. `scripts/verify_test_plan.py` reads a **manually or explicitly approved JSON test plan**, allowing only the exact repository `DevTunaSoft/Canopy`, an immutable lowercase 40-character Git commit SHA and checks `unit`, `syntax`, `gtk`. It compares the current local checkout HEAD with the requested commit. Mutable names like `main`, arbitrary commands and other repositories are rejected.

Usage example (replace the SHA with an authorized real commit):
```json
{"version":1,"repository":"DevTunaSoft/Canopy","commit":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","checks":["unit","syntax","gtk"]}
```

```bash
python3 scripts/verify_test_plan.py --plan /path/to/approved-plan.json --checkout /path/to/Canopy
```

**Security boundary:** This is only an equality/allowlist check. It does not establish who approved the plan, validate cryptographic authorship, ensure a trusted origin remote, isolate executing code, or authorize running untrusted PRs. Never expose GitHub token credentials or host filesystem to the test worker. Provisioning, signed approvals, a private workflow, artifact upload and disposable VM reset require separate implementation and explicit setup consent.

Tests use mocked Git output. No Linux Mint VM or actual approved worker execution has occurred. This branch touches only isolated gate code/tests/docs, not screenshot or memory telemetry modules.
