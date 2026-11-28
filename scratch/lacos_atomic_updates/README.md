# Synthetic atomic-update fixtures

All files here are **synthetic**. They contain no real deployment, digest,
credential, executable, path, URL or guest observation. Real-guest update,
rollback and verification status is `BLOCKED/NOT_RUN`.

- `fixtures/`: valid-shape fixtures consumed by
  `tools/lacos_atomic_updates/fixture_gate.py`. The `expect` field is a claim
  checked against the decision, not a self-fulfilling verdict.
- `hostile/`: intentionally malformed fixtures used as negative controls by
  `canopy_features/atomic_updates/tests/`. Every one must raise
  `AtomicUpdatesError`; none is consumed by the gate as a valid fixture.

Digests are repeated hex characters chosen for readability; they identify no
real OSTree commit.
