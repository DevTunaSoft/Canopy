# LacOS atomic-update tooling

`fixture_gate.py` is a dependency-free, deterministic gate over the synthetic
fixtures in `scratch/lacos_atomic_updates/fixtures/`.

```sh
python tools/lacos_atomic_updates/fixture_gate.py \
  --out scratch/lacos_atomic_updates/evidence/fixture_gate_report.json

PYTHONPATH=. python -m unittest discover \
  -s canopy_features/atomic_updates/tests -t . -v
```

The gate compares each fixture's `expect` claim with the decision computed by
`canopy_features.atomic_updates`, records a SHA-256 for every fixture, and
exits 0 only when every fixture matches. It performs no guest, host, process,
package-manager or network operation. A PASS is `SYNTHETIC`; real-guest update
and rollback remain `BLOCKED/NOT_RUN`.

The tests are intentionally inside the owned package because `tests/` is not
owned by this branch. Foundation CI's `unittest discover -s tests` therefore
does not collect them; run the explicit command above at the exact head.
