# Fake-GIO SystemAppLauncher fixture (synthetic QA tool)

Additive CI tooling under `tools/qa/`. It compiles the **unmodified**
`prototype/classic/SystemAppLauncher.{h,cpp}` from a git object against a
deterministic fake GIO static library and asserts exact desktop-ID mapping and
refusal behaviour. No GLib/GIO dev package, desktop database, X server, real
application process, production source, QML, asset or visual change is involved.

The separate workflow `.github/workflows/classic-launch-fixture.yml` runs this
on `ubuntu-24.04` with `build-essential cmake ninja-build qt6-base-dev`. It
never touches `classic-qt.yml` or the active icon-gate fix.

## Files

| Path | Purpose |
| --- | --- |
| `CMakeLists.txt` | Qt6::Core + AUTOMOC build of two binaries from an exported source dir |
| `run_fixture.sh` | Export → SHA-256 verify → configure → build → run → gate |
| `expected-source-sha256.txt` | Pinned unmodified production source hashes |
| `fake_gio/` | Minimal fake GIO declarations and call-logging shim |
| `harness/system_app_launcher_fixture.cpp` | 11 mapping/refusal cases + 1 no-GIO case |
| `../fake_gio_evidence_gate.py` | Text-level evidence gate; emits labelled JSON |
| `../../../tests/test_fake_gio_evidence_gate.py` | Deterministic gate tests |

## Case contract

Positive mapping (one enabled desktop ID per case; exact call sequence checked):

| Dock label | Desktop ID |
| --- | --- |
| Browser | `firefox.desktop` |
| Terminal | `gnome-terminal.desktop` |
| Calendar | `org.gnome.Calendar.desktop` |
| Photos | `pix.desktop` |
| Mail | `thunderbird.desktop` |
| Files | `nemo.desktop` |

Plus Browser fallback order (`firefox.desktop` → `org.mozilla.firefox.desktop`)
and refusals: opt-in disabled (zero GIO calls), unknown free-form action
(`CANOPY_APP_LAUNCH_REJECTED`, zero GIO calls), no desktop entry
(`CANOPY_APP_LAUNCH_UNAVAILABLE`, zero `should_show`/`launch` calls), launch
failure (`CANOPY_APP_LAUNCH_FAILED`, one `launch` call, no fallback) and a
second binary compiled without `CANOPY_HAVE_GIO` where all seven probed labels
return false from both `canLaunch` and `launch`.

## Evidence labels

- `SYNTHETIC`: real Qt6 Core objects and the real production C++ are compiled,
  but GIO is a logging shim; no process is launched.
- `NOT_MINT`: no Linux Mint guest, real desktop session, real GIO desktop
  database or application launch is exercised here.
- `NOT_RUN`: real-GIO launch, Mint acceptance, visual approval and
  screen-reader behaviour. See `classic-qt.yml` for the separate real-GIO
  XDG fixtures; neither gate substitutes for Mint acceptance.

## Local invocation (off-host)

```bash
REPO=<repo> TIP=HEAD OUTPUT_DIR=<scratch-out> \
  bash tools/qa/fake_gio_launch_fixture/run_fixture.sh
python3 tools/qa/fake_gio_evidence_gate.py \
  --log-dir "$OUTPUT_DIR" --output <scratch-out>/evidence.json
```
