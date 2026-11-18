# Multi-path Linux Mint acceptance matrix — 2026-11-18

## Scope and purpose
This is a *second independent* test acceptance path. It defines high-risk Linux Mint scenarios requiring two different observation sources, rejects a single fake PASS, stale run ID, different Git commit, missing artifact digest, duplicated reports and failed/blocked observations masked by a success summary. It does **not** claim that these observations exist yet.

Mandatory cases (each has two independent oracle identities):
- GTK boot: runner + window observer
- Launcher keyboard: widget interaction + window observer
- Narrow dock: geometry + image inspection
- Corrupt settings: file before/after integrity + recovery UI
- Cinnamon fallback: Mint session manager + reboot/login check
- Idle resource budget: `/proc` sampler + independent observer
- VM recovery: host-side snapshot controller + guest reboot health

Start with all NOT_RUN:
```bash
python3 -m scripts.test_matrix_gate --baseline
```

After externally verifiable, approved Mint evidence exists:
```bash
python3 -m scripts.test_matrix_gate --report /path/to/matrix.json --commit <approved-40-hex-git-sha> --run-id <unique-run-id>
```

**Critical threat model:** This is *structural* two-oracle agreement. It does not verify digest contents, authenticate or cryptographically separate observers, perform real keyboard input, compare screenshots, reboot VMs or exercise hardware. In particular, two forged PASS entries from one compromised process MUST NOT be treated as independent evidence. The future trusted host supervisor must capture observations from isolated processes, verify hashes and provenance, use unique challenges and fail closed on any disagreement. Never mix current and previous run artifacts, and treat a missing oracle as NOT RUN/BLOCKED, not PASS.

Unit tests explicitly inject false-green, oracle disagreement, stale/reused run, wrong commit, missing digest, duplicate cases and block/failure outcomes. The Mint VM is not yet connected. This track remains separate from evidence audit and GUI code.
