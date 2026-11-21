# Qt idle resource evidence: do not mistake a snapshot for acceptance

The targets in `docs/QUALITY.md` are **not verified release results**:
shell-owned PSS ≤200 MiB, average shell-owned CPU ≤1% of one core for
**at least five continuous idle minutes** on the reference machine.
Scope and platform must be recorded. A compositor, service and unrelated
desktop process cannot be silently included or excluded.

## Existing evidence is deliberately insufficient

The compiled-Qt preview's `tools/measure_qt.py` in Classic draft #100
produces schema 1, `kind=short-headless-baseline-not-mint-acceptance`
with approximately five seconds of Ubuntu/Xvfb process measurements.
It does not report reference hardware, actual Linux Mint, sustained idle
CPU samples or reproducible guest provenance. **Do not turn its green
informational report into a 5-minute acceptance claim.**

```sh
python3 -m tools.qa.perf_evidence_gate /absolute/path/to/qt-resource-baseline.json
# Returns INSUFFICIENT_EVIDENCE, exit code 2, even if figures are low
```

## Future full-length evidence schema (schema 2)

An independently developed Linux Mint guest sampler can emit:

```json
{
  "schema": 2, "kind": "five-minute-idle-linux-qt",
  "environment": "linuxmint",
  "measurement_method": "proc-smaps-rollup-and-stat",
  "source_sha": "<40-lowercase-hex>", "binary_sha256": "<64-lowercase-hex>",
  "backend": "software", "duration_seconds": 305,
  "sample_count": 62, "cpu_ticks_start": 12340,
  "cpu_ticks_end": 12500, "clock_ticks_per_second": 100,
  "pss_kib_start": 55000, "pss_kib_end": 62000,
  "pss_kib_peak": 65000
}
```

**The numbers above are invented for schema illustration only, not
Canopy measurements.**

```sh
python3 -m tools.qa.perf_evidence_gate /absolute/path/to/private/idle.json \
  --expected-source-sha <actual-40-hex-sha> \
  --expected-binary-sha256 <actual-64-hex-sha>
```

The gate bounds input size, disallows symlinks, verifies exact schemas,
requires separately specified source/binary SHA pins, rejects nonfinite
or impossible metrics and recalculates CPU from *raw process tick deltas*
and elapsed seconds rather than trusting a claimed percentage. It rejects
less than 300 seconds or 60 samples; it uses peak PSS, not the final
sample, to check the 200 MiB target. A PASS means **only that submitted
self-reported numeric metrics meet the thresholds**. It explicitly sets
`release_approved=false`, `linux_mint_guest_proven=false` and
`visual_approval=false`. This JSON alone cannot attest the host environment,
that the process stayed idle, or that the sampler wasn't manipulated.

Exit code: 0 for numeric-only PASS, 1 for FAIL/invalid, 2 for
INSUFFICIENT_EVIDENCE. No agent should merge a user-facing desktop or claim
Mint compatibility on this output alone. For production resource acceptance,
pair with independently collected Mint VM details, source/binary hashes,
captured command, sampling log, compositor exclusions, memory growth tests
and a human review of the complete five-minute benchmark protocol.

This gate **never starts a daemon, process, Qt UI, benchmark, sampler or
network connection**; the only work is parsing a local bounded report.
