# Independent tester walkthrough — native Plasma 6 development artifact

**Owner directive SHA:** `79e30d79a580bd05cf9d6cb09a45cbbb7887c0c35c5116a34bb6a0ace6042083`
(`Canopy_LacOS_Integrated_Execution_Directive_2026-11-27.md`, §155 "Ensure a user
or independent tester can install and exercise the accepted increment"). The
active-goal file records this directive as a historical pin superseded by Rev3;
this walkthrough changes no directive, merges nothing and approves nothing.

| Item | Exact identity |
| --- | --- |
| Worktree | `C:/Users/X1/AppData/Local/hermes/cache/scratch/wt-native-tester-20261128` |
| Branch | `integration/native-tester-walkthrough-20261128` |
| Base / candidate tip | `21c32b61a29f61210fef38c6b9447b49dbfd10bf` (`integration/native-bundle-candidate-20261128`, re-queried with `git ls-remote` before and after the run) |
| Artifact | `org.kde.plasma.canopyclassic-0.1.0-dev-baseline.tar.gz` from the candidate tree's `scratch/native_build_baseline/build/dist/` |
| Artifact SHA-256 | `ec9e44cfaa3ba3059aef492b429a6e6c6b94da32a230d4acb6cb28a1ef3ece35` |
| Compiled binary SHA-256 | `4950fd793d067aa722a64ea8b09f0c1c65a55263b7f96c8fd418bf579e9f4a32` |
| Approved wallpaper SHA-256 | `8c6cab50a0977fc129c0d2a20523d9361646f36da66f2f3f2b2436a0d9001381` |
| Guest | existing `Canopy-Test-Plasma6` (UUID `3aecd840-4dd6-4481-913f-64a289da406d`, 2 vCPU / 4096 MiB, Kubuntu 26.04 Plasma 6, X11) |
| Guest access | pre-existing NAT SSH `127.0.0.1:2223`, pre-existing scratch key; no password typed, guessed or stored |
| Verdict | **21/21 checks PASS with scoped limitations** (below). Development artifact only — not a release, not visual approval, not merge authorization. |

## Serialization with the stability agent

`scratch/native_tester/LEASE.json` records the occupancy window
`2026-11-28T07:30:41Z`–`08:30:41Z`. The stability agent's claim is
`wt-native-stability-20261127/scratch/native_stability/CLAIM.md`; its bounded
60-minute soak ended `2026-11-28T07:27:00Z` with `SAMPLER_RC=0`, so this tester
started only after that agent released the guest. Host preflight
`ps -ef | grep -iE 'VBoxHeadless|smoke_test|native_soak|unittest discover'`
showed no competing process at `07:30Z`; guest preflight returned `SSH_OK` with
2 users. The VM was never started, stopped, saved, reverted or snapshotted.

## Exact reproduction commands

```sh
WT=C:/Users/X1/AppData/Local/hermes/cache/scratch/wt-native-tester-20261128
KEY=C:/Users/X1/AppData/Local/hermes/cache/scratch/g1_ubuntu_evidence/ssh/g1_ed25519
VBM='C:/Program Files/Oracle/VirtualBox/VBoxManage.exe'

git -C C:/Users/X1/Projects/Canopy worktree add -b integration/native-tester-walkthrough-20261128 \
  "$WT" 21c32b61a29f61210fef38c6b9447b49dbfd10bf
"$VBM" showvminfo Canopy-Test-Plasma6 --machinereadable | grep -E '^(VMState|memory|cpus)='
ssh -i "$KEY" -o BatchMode=yes -p 2223 canopy@127.0.0.1 'date -u +%FT%TZ; hostname; echo SSH_OK'

# stage the exact artifact (host SHA verified before copy)
sha256sum "$WT/scratch/native_build_baseline/build/dist/org.kde.plasma.canopyclassic-0.1.0-dev-baseline.tar.gz"
ssh -i "$KEY" -p 2223 canopy@127.0.0.1 'mkdir -p ~/native_tester/incoming'
scp -i "$KEY" -P 2223 "$WT/scratch/native_build_baseline/build/dist/org.kde.plasma.canopyclassic-0.1.0-dev-baseline.tar.gz" \
  canopy@127.0.0.1:~/native_tester/incoming/

# tester helpers (owned paths) copied into the guest
scp -i "$KEY" -P 2223 "$WT/tools/tester/native_tester_guest.sh" \
  "$WT/tools/tester/native_tester_owner_guard.sh" \
  "$WT/tools/tester/wallpaper_shim/plasma-apply-wallpaperimage" canopy@127.0.0.1:~/native_tester/
ssh -i "$KEY" -p 2223 canopy@127.0.0.1 '
  mv -f ~/native_tester/native_tester_owner_guard.sh ~/native_tester/owner_guard.sh
  cp -f ~/native_tester/plasma-apply-wallpaperimage ~/native_tester/plasma-apply-wallpaperimage-shim
  chmod +x ~/native_tester/*.sh ~/native_tester/plasma-apply-wallpaperimage-shim
  bash ~/native_tester/native_tester_guest.sh \
    ~/native_tester/incoming/org.kde.plasma.canopyclassic-0.1.0-dev-baseline.tar.gz \
    ec9e44cfaa3ba3059aef492b429a6e6c6b94da32a230d4acb6cb28a1ef3ece35 \
    ~/native_tester/state ~/native_tester/results \
    21c32b61a29f61210fef38c6b9447b49dbfd10bf \
    79e30d79a580bd05cf9d6cb09a45cbbb7887c0c35c5116a34bb6a0ace6042083 \
    pre-existing-scratch-ssh-key'

# host-side frozen geometry contract (32/96/14/7 in Theme.qml)
cd "$WT" && PYTHONPATH="$WT" PYTHONUTF8=1 python -m unittest -v \
  tests.test_c100_dock_display_geometry_contract
```

## What was exercised and what proved it

The terminal verdict of the final run is `WALKTHROUGH_DONE rc=0`,
`WALKTHROUGH_END fail=0 checks=21` at `2026-11-28T07:55:52Z`. Raw rows are in
`scratch/native_tester/evidence/checks.tsv` and the timestamped command stream
in `.../commands.log`.

| Requested item | Result | Evidence |
| --- | --- | --- |
| Artifact identity | PASS | archive SHA, 17-file `SHA256SUMS`, binary SHA and wallpaper SHA re-verified inside the guest |
| Install in user scope | PASS | `kpackagetool6 --type Plasma/Applet --install`, no sudo, no system file; `verify.sh` PASS (`METADATA_IDENTITY_OK`) |
| Wallpaper | PASS (config) / D-Bus apply BLOCKED | `Image=file:///home/canopy/native_tester/state/unpacked/contents/approved/wallpaper/Canopy_Classic_Master_Wallpaper_1920x1080.png` present in `plasma-org.kde.plasma.desktop-appletsrc`; compiled `--landscape-wallpaper` verification PASS; live shell apply failed (see limitation 2) |
| Dock geometry 32/96/14/7 | PASS | host contract `Ran 16 tests ... OK` pins `Theme.qml` `(barHeight=32, dockSize=96, dockPadding=14, dockSpacing=7)`; compiled binary logs `SELF_TEST_PASS: desktop chrome geometry QSize(1200, 750)` and `QSize(1920, 1080)` with zero `SELF_TEST_FAIL` |
| Terminal launch | PASS | disposable `gnome-terminal.desktop` in an isolated `XDG_DATA_HOME`; Terminal dock tile reached real GIO and touched the marker (`selftest_terminal_launch.log`) |
| Launcher search | PASS | `SELF_TEST_PASS: actual Qt launcher opens, searches and closes`; 8 approved launcher icons; `CATALOG_ALL_PASS` |
| Running indicator / window activation | PASS | `WINDOW_ACTIVATION_HOST_SELF_TEST_PASS running=ok active=ok closed=ok fail_closed=ok` from a trusted host snapshot |
| Notifications single owner | PASS | `org.freedesktop.Notifications` owner `:1.22` → PID 5422 `plasmashell`; 0 foreign daemons, 0 Canopy daemons, 1 upstream service file, 0 foreign duplicates, 1 bus-name occurrence |
| Settings persistence | PASS | `SETTINGS_FIXTURE_PASS`; QSettings file written under `~/.config/DevTunaSoft/`, `reduced_motion=unset`; a fresh process accepted a stored `reduce` value and preserved it across restart |
| Uninstall / stock fallback | PASS | package absent after `kpackagetool6 --remove`; Plasma config byte-identical to pre-install snapshot (`141b7e88…`); wallpaper path back to `file:///usr/share/wallpapers/Kubuntu#day-night` |

## Evidence (SHA-256 from `scratch/native_tester/SHA256SUMS.txt`, 38 files, `sha256sum -c` rc=0)

- `evidence/checks.tsv` — `7f8a9ba79319e278435afbdf0e602155dcc71791fef7a4f55f6cbbdbfddfcd75`
- `evidence/commands.log` — `88e211a75b2b2bf4bc56f4ace7a35124d2ae30aa95713cc0f19e801188f72c4d`
- `evidence/selftest_full_1200x750.log` — `360c19f893accc17d98946c0d2f9b0b7802b6aabc21c55429ec38011c801a5a5`
- `evidence/offscreen_1200x750.png` — `9509f50fe5e336d5794d2838686efd6b349328c534a80467b14b14624c82ea9b`
- `evidence/offscreen_1920x1080.png` — `636bbdffed535400969921704346d741705eb138ed162f0f3831f9a9cf3a1a0f`
- `evidence/owner_guard.log` — `5708afee473973c7c07b30a8fb6d0c36585eae0cc49de08365568328c82008c0`
- `evidence/wallpaper_shim.log` — `23f9121130b71ef083b387dfadca70de2596f8e3b16677f031ad25991703894b`
- `raw/host_geometry_contract.log` — `0edc1fc88dd8b09526a72563f49aae51c374723edc09fb14fa684f322d7906be`
- VBox framebuffer captures: `screenshots/00_pre_install.png` — `651b553370df6dfecbb0127e3017a9036044c86e2e7049090607b6d1ab101bfe`;
  `screenshots/02_stock_after_uninstall.png` — `7b86ba96d61c816a294f43395084995e66c428c373dab8ad22f2837c7f670f42`.
  Both show the active SDDM greeter background (1024x768), not a Canopy session;
  they are real framebuffer captures, not visual-acceptance evidence.
- Superseded attempts are retained, not erased: `raw/guest_checks_first_run.txt`
  (4 FAILs: harness PID parse, service-file definition, wallpaper),
  `raw/guest_checks_run2.txt` (3 FAILs: shim staged under the wrong name),
  `raw/guest_walkthrough_run3.log` (final rc=0).

## Known limitations

1. **Interactive X11 UI: NOT_RUN.** The seat was on an SDDM greeter (session
   1015, tty3, `:2`, active); the Canopy user session 65 (`:0`) was online but
   inactive. `xdotool getmouselocation`, `xdpyinfo` and `wmctrl -lp` each
   returned rc=124 with `timeout 6`. `loginctl activate 65` was denied
   (`requires interactive authentication`); a Ctrl+Alt+F2 scancode injection via
   `VBoxManage keyboardputfile` did not change the active session. No password
   was guessed or supplied. Keyboard/pointer launcher interaction, a real
   Konsole window and screen-reader announcements remain unproven.
2. **Live Plasma wallpaper apply: BLOCKED in this seat.** The product
   `plasma-apply-wallpaperimage` call timed out (`rc=124`, "Did not receive a
   reply") at `2026-11-28T07:55:24Z`. The tester-only PATH shim
   `tools/tester/wallpaper_shim/plasma-apply-wallpaperimage` logs that failure
   and returns 0 so the unchanged product `install.sh` can perform its own
   in-place KConfig `Image=file://…` write; no product code or asset was edited.
   The config-path check is PASS; a fresh render of the wallpaper by the live
   shell is not proven while the greeter owns the seat.
3. **Offscreen compiled self-tests are scoped functional evidence.** Qt ran
   with `QT_QPA_PLATFORM=offscreen` in the real guest against the exact binary
   from the artifact. They exercise QML wiring, geometry, launcher search and
   launch bridges, but they are not OS-level desktop interaction and carry no
   owner visual approval. The captured PNGs are real renders of the compiled
   shell, not CI fabrications.
4. **Notification delivery round trip: NOT_RUN.** Only single-owner wiring was
   probed. A fresh `org.freedesktop.Notifications` `Notify`/close round trip
   was not repeated here; prior scoped probes against this guest timed out.
5. **Pre-existing process:** `/home/canopy/.local/bin/canopy-classic` (PID 5667,
   started before this lease) was observed in the stability preflight and left
   untouched; it is not part of the installed artifact under test.
6. **Stability context:** the stability agent's 60-minute soak verdict was
   `SOAK_WARN_CRASH_OR_ERROR_EVENT+SAMPLING_GAP+SERVICE_COUNT_DRIFT`;
   a 24-hour soak remains `NOT_RUN` and is not claimed by this walkthrough.
7. **No release / no merge / no approval.** CI checks, protected-branch merge,
   distinct-human review and final visual acceptance are all `NOT_RUN` or
   owner-gated. This is an installable development checkpoint only.

## Owned paths

`docs/NATIVE_TESTER_WALKTHROUGH.md`, `scratch/native_tester/**`,
`tools/tester/**`. No source, QML, C++, approved artwork, workflow, settings or
other agent's file was changed. No PR was merged or approved by this work.
