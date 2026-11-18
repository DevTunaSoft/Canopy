# Independent test-evidence consistency oracle — 2026-11-18

## Why it exists
The VM test runner may report PASS incorrectly because of missing GTK, skipped tests, a truncated log, partial execution or a broken status aggregation. Never trust one green flag. This checker reads a **separate saved report** and cross-checks each required check's status, numeric exit code, nonzero unittest count, successful summary, absence of skipped GTK tests, log completeness and check-list uniqueness. It refuses contradictory or incomplete reports. Test cases deliberately inject 13 false-success states, plus duplicated JSON keys.

```bash
python3 -m scripts.audit_test_evidence --report /path/to/mint-testlab.json --checks unit syntax gtk
```

Use a trusted **outside-VM** validation process where feasible; a compromised VM can forge both JSON and logs. This is an additional consistency gate, **not proof of test execution, trusted code, image accuracy or cryptographic provenance**. When connecting the Mint VM, add separate trusted process exit observation, fresh per-run nonces, approved commit SHA, hash manifests, image/geometry checks, and snapshot/reset evidence. Compare all independent oracles and classify conflicting observations **INCONCLUSIVE or FAIL**, never PASS. Running this utility inside the same untrusted checkout does not create an independent security boundary.

This branch changes only an isolated verifier, regression tests and this checkpoint. It does not alter the GTK UI or other tracks. Mint/Cinnamon execution NOT RUN.
