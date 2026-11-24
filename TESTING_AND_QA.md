# Testing and QA

## Automated tests

Run all tests:

```sh
python -m unittest discover -s tests -v
```

Supervisor tests:

```sh
python -m unittest tests.test_canopy_supervisor -v
```

Qt source tests:

```sh
PYTHONUTF8=1 python -m unittest tests.test_classic_qt_source tests.test_classic_source tests.test_classic_dock_frozen -v
```

## CI

- `.github/workflows/foundation.yml` runs `python tools/check_foundation.py` and
  `python -m unittest discover -s tests -v`.
- `.github/workflows/classic-qt.yml` installs Qt 6.4+, compiles the real
  application, runs approved-art checks, headless startup, captures three real
  screenshots, validates PNGs, and measures five-minute idle CPU/PSS.
- `.github/workflows/review-supervisor.yml` is read-only CI/PR reporting.

## QA requirements

- Real Qt compile and runtime evidence only.
- No synthetic screenshots presented as compiled Qt screenshots.
- No fabricated performance numbers.
- Linux Mint guest acceptance is separate from unit tests.
- Owner visual approval is required before merge.
- Green CI is not merge authorization.
- Preserve approved dock geometry and exact icon hashes.
- Keep PRs draft until all required gates pass.
