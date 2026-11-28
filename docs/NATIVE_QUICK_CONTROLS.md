# Native quick controls — bounded brightness, network and power (M3)

Status: **implemented planner + real host probe mapping; no control executed by
Canopy, no merge, draft PR only.** Owner directive SHA: `79e30d79` (cap 8).
Base: `ec910d7a7275296ecbc8b5e5c459d356205165d1`
(exact tip of `origin/integration/canopy-plasma6-20261127` at task start).
Branch: `product/native-quick-controls-20261127`. Worktree:
`C:/Users/X1/AppData/Local/hermes/cache/scratch/wt-native-quick-controls-20261127`.

## Owned paths

| Path | Change |
| --- | --- |
| `canopy_features/quick_controls/native_controls.py` | new bounded planner/verdict module |
| `canopy_features/quick_controls/__init__.py` | re-export the new module's public values |
| `canopy_features/system/quick_controls_state.py` | additive execution labels and capability reason codes |
| `canopy_features/system/session_controls_native.py` | additive `NOT_RUN` execution label on privileged decisions |
| `docs/NATIVE_QUICK_CONTROLS.md` | this contract |
| `scratch/native_quick_controls/**` | read-only probe script, evidence and synthetic tests |

Nothing else was touched: no compiled source, QML, artwork, CI/workflow,
protected instruction file, PR, approval or merge. No daemon, service file or
second notification owner was created. Upstream KDE/FreeDesktop services are
reused only.

## What the code does

`native_controls.py` is a pure, fail-closed planner. It never opens a bus,
socket or process; never reads a device, credential, clock or environment; and
never executes a command. A trusted host supplies small, normalised
`ProbeFacts`; the planner returns immutable `CommandPlan` + `ControlVerdict`
records. Only the trusted host may execute the exact returned plan.

Upstream facilities and bounded plans:

| Domain | Facility | Plan | Gate |
| --- | --- | --- | --- |
| brightness | KDE PowerDevil `org.kde.Solid.PowerManagement` → `/org/kde/Solid/PowerManagement/Actions/BrightnessControl` | `setBrightness(uint)` with a target computed from a caller-supplied relative step, clamped to `0..brightnessMax` (≤ 65535) | `isActionSupported("BrightnessControl")`, object present, backlight device present, trusted current value/max |
| network | `org.freedesktop.NetworkManager` | `CheckConnectivity()` with zero arguments | `GetPermissions[network-control] == "yes"` and `ConnectivityCheckAvailable == true` |
| power | `org.freedesktop.login1.Manager` | `CanSuspend()` read-only query | capability token and logind manager access are not denied |
| power/session transitions | existing `session_controls_native` decisions | **no plan at all** | suspend, hibernate, power-off, reboot, lock and logout are permanently refused |

A step is a signed integer within `[-100, 100]`; the caller cannot supply an
absolute brightness target, object path, service name, interface, method, shell
fragment or executable. `CommandPlan` derives all D-Bus fields from a fixed key
allowlist and holds only bounded integer arguments. `to_dict()` records
`executed: false` and contains no argv/command field. Wrong types, hostile
tokens, oversized values and contradictory facts raise `NativeControlsError`.

### Truthful execution labels

`AVAILABLE`/`UNAVAILABLE` (existing vocabulary) says whether a plan may be
offered. Execution labelling is independent and uses the additive tokens in
`quick_controls_state`:

- `NOT_RUN` — no host command was performed (missing probe, absent capability
  or device, privileged refusal).
- `BLOCKED` — an explicit host policy/permission denial was observed before any
  state change.
- `PASS` — only `NativeControls.host_result(..., succeeded=True)` can promote
  an already-available plan after a trusted host reports completion. The
  planner never awards itself `PASS`.

Existing disclosures and status labels are reused. New reason codes
(`capability-absent`, `capability-denied`, `no-capability-probe`,
`no-bounded-change`) use fixed text with no interpolation of host error strings.
`session_controls_native.NativeDecision` now also carries `execution_label =
"NOT_RUN"` in its decision dict; its approval semantics are unchanged.

## Real Plasma host verification

Host: Windows 11. Guest: `Canopy-Test-Plasma6` (Kubuntu 26.04 / Plasma 6,
`canopy` uid 1000), SSH forward `127.0.0.1:2223`, key from the pre-existing
local artifact `g1_ubuntu_evidence/ssh/g1_ed25519`. The probe script is piped
to `sh -s SECTION` over SSH, so **nothing is written in the guest**. Every
command is an introspect/get/list/read; no toggle, elevation, sysfs write,
activation, inhibition or power transition was performed. No shell password
was used or recorded.

Exact probe command (host side, `KEY`/`PROBE`/`OUT` as above):

```sh
for sec in env brightness network power; do
  ssh -i "$KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes -p 2223 canopy@127.0.0.1 \
    "export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus XDG_RUNTIME_DIR=/run/user/1000 DISPLAY=:0 XDG_SESSION_TYPE=x11 XDG_CURRENT_DESKTOP=KDE; sh -s $sec" \
    < "$PROBE" > "$OUT/$sec.txt" 2>&1
done
```

Guest reboot context: the fresh probe found SDDM greeter and an SSH session but
no graphical user shell in that moment (`env.txt`: no `plasmashell`, `kwin_x11`
or `org_kde_powerdevil` process). The earlier logged-in-Plasma evidence with
notification PASS, volume PASS and duplicate-owner check PASS is preserved in
`C:/Users/X1/AppData/Local/hermes/cache/scratch/native_notification_controls_runtime.json`
and `native_controls_readonly_addendum.md`. Device and permission blockers were
re-observed fresh in this pass, and the VM was left running.

| Control | Probe outcome | Planner verdict | Exact observed blocker |
| --- | --- | --- | --- |
| brightness | capability inspection performed; no object, no backlight | `NOT_RUN` / `capability-absent` | `NameHasOwner(org.kde.Solid.PowerManagement) == (false,)`; `isActionSupported BrightnessControl` → `ServiceUnknown`; `/sys/class/backlight/` has no entries; `ScreenBrightness DisplaysDBusNames` → `ServiceUnknown` |
| network | status readable (State=70, Connectivity=4, `ConnectivityCheckAvailable=false`); recheck denied | `BLOCKED` / `capability-denied` | `org.freedesktop.NetworkManager.PermissionDenied: Not authorized to recheck connectivity`; `GetPermissions[network-control] == 'auth'`, `enable-disable-wifi == 'no'` |
| power | `CanSuspend='challenge'`, `CanHibernate='na'`, `CanPowerOff='challenge'`; manager job list denied | `BLOCKED` / `capability-denied` | `org.freedesktop.DBus.Error.AccessDenied: Rejected send message ... member="ListJobs" ... destination="org.freedesktop.login1"` |
| suspend/poweroff/reboot/hibernate | no call attempted | `NOT_RUN` / `privileged-host-change` | permanent contract refusal, independent of probe |

Guest state was not changed: `nmcli` still reports `connected/full`, the two
active connections are unchanged, no brightness device exists, and no logind
job was created. `scratch/native_quick_controls/evidence/runtime_verdicts.json`
is the machine-readable mapping from the fresh probe bytes to the verdicts.
It is a label-mapping artifact, **not** a claim that a control ran successfully.

## Verification (targeted, with exact commands)

All commands were run from the exact worktree.

| Check | Command | Result | Log SHA-256 |
| --- | --- | --- | --- |
| Synthetic targeted tests | `PYTHONPATH=. python -m unittest discover -s scratch/native_quick_controls/tests -p 'test_*.py'` | 21 tests, OK | `1db62e1e28460fd0d1acc0e8b7045317cfebb8cd0d77de230b70e37f1d6619a4` |
| Existing quick-controls regression | `PYTHONPATH=. python -m unittest discover -s tests -p '*quick_controls*.py'` | 110 tests, OK | `84cc1ceb436ddf7808b68e621ee37a16aaf5740c6ebbe1cf30b6594e93f001aa` |
| Existing session-control regression | `PYTHONPATH=. python -m unittest tests.test_pe083_session_controls_native tests.test_pe048_session_controls` | 74 tests, OK | `6c5b2085653644f0410673787e3f0e407b0aa11f15f3586eb04e75fd859e8bed` |
| Real probe → verdict mapping | `PYTHONPATH=. python scratch/native_quick_controls/verify_runtime.py` | rc=0; `NOT_RUN`, `BLOCKED`, `BLOCKED`, `NOT_RUN` as above | `6d22340b055cf8278114cc23b9bb13a27aae9d30d35fadb531c07955f511ba38` |
| Foundation check | `python tools/check_foundation.py` | PASS | `cd7ce3ea44ff12d436ec0af5e64de94b552f5bdfd4b210f14372c29537f937ad` |
| Byte compilation | `python -m py_compile` on all six changed/added Python files | rc=0 | not logged (no output) |

Full `unittest discover -s tests`, Qt compilation, CI, compiled-shell wiring
and full-suite baseline comparison are **NOT_RUN** for this bounded task.
`SHA256SUMS` in `scratch/native_quick_controls/evidence/` covers the probe
logs, verdict JSON and command logs.

## Resource impact

- Measured: `SYNTHETIC` pure-Python tests and four read-only SSH probe batches;
  no sustained idle PSS/CPU sampling, no timing win claimed.
- `NOT_RUN`: real desktop idle PSS/CPU, compositor wakeups, compiled Qt
  runtime, screen-reader output and owner visual acceptance.
- Screen-reader behavior is unchanged: the planner emits no UI, announcement
  or accessibility metadata; it returns immutable values only.
- Bounded by construction: no retained mutable state, no polling, no thread,
  no cache, no daemon. At most one plan per call, at most two small integer
  arguments, a 64-byte provenance token and fixed-string disclosures. Nothing
  trades stability, security, accessibility or approved visuals for a minor
  performance gain.

## Honest limits

- This change does not wire the compiled QML overlay and does not perform a
  control. A trusted host must execute plans and report results for `PASS`.
- No notification change is claimed; the prior notification PASS belongs to
  the earlier native-runtime task and was not re-exercised here.
- The current guest had no graphical user shell during the fresh probe; the
  hardware/permission blockers are real, but a full logged-in interactive
  control exercise remains unproven on this host.
- No owner approval, merge, release readiness or visual acceptance is claimed.
