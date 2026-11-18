# Independent pathway C — deliberate failure injection in CI

A passing test suite cannot establish that the test mechanism reliably detects failures. `scripts/negative_controls.py` runs two actual subprocess-backed `unittest` fixtures in an isolated temporary directory: one known-good test and one deliberately failing assertion. The controller must report PASS for the first and FAIL with nonzero exit code and FAILED text for the second, otherwise the **negative-control gate fails CI**.

```bash
python3 -m scripts.negative_controls
```

This uses the existing bounded `run_check` without altering the Canopy application or actual test suites, and it requires no Mint VM. A separate regression test replaces the runner with a lying always-PASS mock and verifies that the control rejects it. This protects against some false-green result-handling bugs, but does **not** establish trust in a compromised VM, fake process logs, failing GUI automation, unrelated stale artifacts or screenshots. The two independent evidence audit pathways (PRs #30 and #31) cover complementary report/scenario checks.

Test-control fixtures intentionally contain a failing assertion. The controlling script must itself exit **zero only when the failure is correctly detected**. This track is independent of source UI, VM setup, and other branch changes.
