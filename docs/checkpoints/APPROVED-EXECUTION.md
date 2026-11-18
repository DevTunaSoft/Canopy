# Separate track: immutable-checkout test execution (2026-11-18)

`scripts/run_approved_test_plan.py` stitches together the existing strict JSON plan validator, clean-checkout/HEAD verification and allowlisted test runner. The plan and result **must be outside the source checkout**. The helper does not fetch untrusted code, install packages, create approvals, touch the VM host or run arbitrary user-supplied commands.

Example, on an isolated, pre-authorized disposable VM:
```bash
python3 -m scripts.run_approved_test_plan --plan /tmp/approved-canopy.json --checkout /home/tester/Canopy --output /tmp/canopy-result.json
```

The approval file must contain the exact authorized `DevTunaSoft/Canopy` SHA and selected checks from `unit`, `syntax`, `gtk`. A clean local HEAD and permitted check names are required. **Do not equate this with real authorization**: the VM owner must provide a separate trusted source of approved plan data, verify Git origin/provenance, and isolate the execution environment. If the code itself is malicious, a Python verifier running inside that checkout is not a security boundary. GitHub public PRs must never execute automatically on a personal self-hosted runner.

Synthetic integration tests validate the gating logic; Mint execution and external approval/authentication remain NOT RUN / NOT IMPLEMENTED. The track modifies no Classic GUI or performance sampler sources.
