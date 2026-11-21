# Linux Mint guest acceptance attempt 1

- Task: `mint-guest-acceptance-attempt-1`
- Branch: `feat/canopy-supervisor-mint-guest-acceptance-attempt-1`
- Date: 2026-11-21
- Host: Windows (PowerShell 5.1)

## Objective

Check for VirtualBox/VBoxManage, a prepared Mint VM and the existing guest
preflight. If all exist, run only the documented read-only preflight and report
exact output. Do not install a distribution, change the host desktop or
fabricate guest results.

## Prerequisite checks

### 1. VirtualBox / VBoxManage — PRESENT

`where.exe VBoxManage` (exit 1, not on PATH):

```
INFO: Could not find files for the given pattern(s).
```

Full-path checks and version:

```
C:\Program Files\Oracle\VirtualBox\VBoxManage.exe => True
C:\Program Files (x86)\Oracle\VirtualBox\VBoxManage.exe => False

& 'C:\Program Files\Oracle\VirtualBox\VBoxManage.exe' --version
7.2.22r175245
```

### 2. Prepared Mint VM — PRESENT (powered off)

```
& 'C:\Program Files\Oracle\VirtualBox\VBoxManage.exe' list vms
"Canopy-Test-Mint" {fbf69438-6729-47d4-897f-2ff1473b02a3}

& 'C:\Program Files\Oracle\VirtualBox\VBoxManage.exe' list runningvms
(no output)
```

`showvminfo "Canopy-Test-Mint" --machinereadable` excerpts:

```
name="Canopy-Test-Mint"
ostype="Ubuntu (64-bit)"
memory=4096
cpus=2
VMState="poweroff"
graphicscontroller="vmsvga"
```

### 3. Existing guest preflight — PRESENT

`tools/mint_guest_preflight.py` exists; documented command in
`docs/MINT_GUEST_PREFLIGHT.md` line 14:

```
python3 tools/mint_guest_preflight.py --json > mint-guest-preflight.json
```

`python3` is a broken Store alias on this host (exit 9009); `python` is
Python 3.12.10 and was used to execute the same script.

## Guest-access feasibility (in-guest run)

The documented preflight is specified to run **inside** an existing disposable
Linux Mint VM (doc step 1: boot with Cinnamon; step 2: run from a Canopy
checkout). From this host no in-guest execution path exists:

- VM is `poweroff` (booting it would change VM state).
- `VBoxManage guestproperty enumerate` shows no Guest Additions property:
  only `/VirtualBox/HostInfo/GUI/LanguageID = 'en_US' ... RDONLYGUEST`.
- `showvminfo` shows no shared folders configured.
- No guest username/password, guestcontrol method or in-guest Canopy checkout
  is documented in the repository.

Therefore the **in-guest preflight run is BLOCKED**. No VM was booted, no
distribution was installed, no host desktop setting was changed and no guest
result was fabricated.

## Documented read-only preflight — executed on host (NOT guest evidence)

Exact command run (read-only, installs nothing):

```
& python tools/mint_guest_preflight.py --json
```

Exact output (exit code 1):

```json
{
  "blockers": [
    "guest is not verified as Linux Mint",
    "no graphical display for declared session",
    "desktop session identity not provided",
    "session type not provided",
    "required build/smoke tool not found: cmake",
    "required build/smoke tool not found: pkg-config",
    "required build/smoke tool not found: ninja",
    "required build/smoke tool not found: xvfb-run",
    "Qt6Core pkg-config metadata not available"
  ],
  "cinnamon_identified": false,
  "commands_present": {
    "cmake": false,
    "ninja": false,
    "pkg-config": false,
    "xvfb-run": false
  },
  "desktop_session_present": false,
  "graphical_display_present": false,
  "mint_guest_acceptance": "NOT_RUN",
  "mint_identified": false,
  "probe_only": true,
  "qt6_core_version": null,
  "runtime_functional_test": "NOT_RUN",
  "status": "BLOCKED",
  "version_id": "unknown",
  "session_type": "other-or-unknown",
  "visual_acceptance": "NOT_RUN",
  "schema_version": 1
}
```

This output is from the Windows host, not a Linux Mint guest. It is recorded
for completeness only. `mint_guest_acceptance`, `runtime_functional_test` and
`visual_acceptance` all remain `NOT_RUN`. No guest pass is claimed.

## Tests for touched/related area

```
python -m unittest tests.test_mint_guest_preflight -v
Ran 16 tests in 0.314s
OK
EXIT=0
```

Result: PASS. The preflight tool is intact; its tests include explicit
negative controls (non-Mint and Ubuntu never pass as Mint). No source files
were modified.

## Blocked state and next step

BLOCKED for real Mint guest acceptance. To proceed, a documented in-guest
access path is required: boot the prepared VM with Cinnamon, install/enable
Guest Additions or provide a guestcontrol credential and an in-guest Canopy
checkout, then run `python3 tools/mint_guest_preflight.py --json` inside the
guest and attach the real JSON. Separate Qt build, runtime smoke, resource and
visual signoff gates remain outstanding per `docs/MINT_GUEST_PREFLIGHT.md`.

Summary: All three prerequisites exist; in-guest preflight is BLOCKED (no guest access), host-only probe is BLOCKED as expected, related tests PASS (16), guest acceptance NOT_RUN.
