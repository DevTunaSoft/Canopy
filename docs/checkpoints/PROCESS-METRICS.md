# Independent track A — Linux memory telemetry

Scope: standalone `scripts/process_metrics.py`, pure tests; no other implementation files edited. This instrument samples the memory of an **already-running, user-owned PID**, using Linux `/proc/PID/status`, bounded by 120 samples at 10 seconds maximum interval. It neither launches code nor claims to benchmark CPU or startup.

When Mint VM is ready, while Canopy is running under its dedicated test account:

```bash
python3 scripts/process_metrics.py --pid PID --samples 20 --interval 0.5 --output test-results/canopy-memory.json
```

Replace `PID` with the exact Canopy test process PID. This stores last and peak-observed RSS and the kernel-reported high-water mark (KiB). Sampling stops if the process exits. No process names, open files or secrets are collected. Run **only on approved, disposable VM test processes**.

Requirements: future Classic/Modern shared performance measurements and test-lab evidence; actual resource thresholds must be set from verified Mint data. Unit tests use fake `/proc` content and mocked sampling, not Mint hardware. No visual tests or actual Mint measurements have been run for this track. Integrate carefully with the independent screenshot and commit-gate branches, without overwriting shared changes.
