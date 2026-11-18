# Track A continuation — process CPU evidence (2026-11-18)

Adds a single-purpose Linux /proc CPU measurement module, separate from the existing RAM sampler, with deterministic unit tests. Samples CPU ticks and process start time before and after a bounded delay; rejects unexpected PID reuse or counter regression. CPU percentages are interpreted as a percentage of **one logical CPU** and may exceed 100% on multithreaded workloads.

On a dedicated Linux Mint VM running an approved Canopy process under the same user:

```bash
python3 scripts/cpu_metrics.py --pid 12345 --interval 2 --output test-results/canopy-cpu.json
```

Replace 12345 with the actual process ID of that test process; never guess PIDs. The tool is unprivileged and reads a single process, doesn't touch the VM or run arbitrary commands. It does not automatically launch Canopy, perform baseline comparison, or measure whole-system CPU, startup latency or graphics performance.

Verification: unit tests in `tests/test_cpu_metrics.py`; live Linux Mint performance measurements **NOT RUN**. Once the VM is available, collect repeated idle and active samples per profile under controlled hardware/settings and compare against documented baselines.
