# Independent host-owned run ledger (2026-11-18)

A Mint guest's reported PASS is not authoritative. `scripts/testlab_run_ledger.py` models **host-generated** unpredictable 128-bit run IDs associated with approved immutable commits, bounded attempts (three by default), unique evidence names and SHA-256 digests. It rejects missing evidence before a PASS and uses exclusive report creation so an earlier run cannot be silently overwritten. Its tests simulate stale/duplicate artifacts, invalid state transitions, and retry exhaustion.

Example host-side operation, from approved code:
```powershell
py -3 -m scripts.testlab_run_ledger --commit <approved-full-40-hex-sha> --output-dir C:\CanopyLab\runs
```

The model is not a service. It currently neither schedules recurring runs nor starts Mint, transfers evidence, verifies producer identity, performs snapshot restoration, or proves the hash came from an independent observer. These must be supplied by a trusted Windows-host supervisor and tested end to end. Keep the ledger **outside** the guest, its working directory, and any guest shared folder; a guest must not be able to mutate it. Never treat host-generated report entries and a guest's self-supplied data as two independent oracles.
