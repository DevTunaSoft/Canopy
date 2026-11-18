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

## 2026-11-18 — Fail-closed working-tree validation

The commit gate now checks **both** the exact approved HEAD SHA and `git status --porcelain=v1 --untracked-files=all`. Modified, staged or untracked worktree files cause BLOCKED instead of a false PASS. Ignored files remain outside the check; future VM deployment must run from a fresh, isolated checkout with no unsafe Git filters/hooks. This remains **local cleanliness validation**, not cryptographic proof that the test plan was authorized or code came from a trusted origin. Regression tests cover a clean tree, dirty/untracked files and a failed status command.

The VM and a secure plan-approval service remain NOT IMPLEMENTED; do not connect a public PR event to a self-hosted runner.
