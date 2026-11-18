# Isolated guest-result envelope (2026-11-18)

The future Mint guest needs to transport bounded, clearly **untrusted** test results to a host-side checker without pretending a guest report is authoritative. `scripts/guest_result_envelope.py` reads a small JSON result, validates its schema/status, tags the exact approved 40-character commit, unique 128-bit run ID and Linux boot ID, computes a SHA-256 digest, and labels output `UNTRUSTED_GUEST_EVIDENCE` with `host_verified=false`.

Example inside approved Mint VM:
```bash
python3 -m scripts.guest_result_envelope --commit <approved-sha> --run-id <host-issued-32-hex-id> --report /home/tester/reports/run.json --output /home/tester/reports/envelope.json
```

**Security:** This does NOT authenticate the real VM, challenge freshness, check host-side process exits, provide network transport, or give the user/assistant remote access. A compromised guest can forge boot ID, status, hashes and identity. The separate future Windows collector must verify copied bytes, run provenance, boot-state observations, and expected plan; it must mark conflicts INCONCLUSIVE. Do not automatically treat this guest result as a second independent observer.

No Mint VM exists yet. Synthetic tests cover good shape, altered identity, status disagreement, malformed schema and symlink rejection. This track is independent of the Windows bootstrap and host ledger branches.
