# Native Plasma accessibility verification (M3/M5)

**Branch:** `product/native-a11y-20261127` · **Base:** `ec910d7a` ·
**Directive:** owner SHA `79e30d79a580bd05cf9d6cb09a45cbbb7887c0c35c5116a34bb6a0ace6042083` (cap 8).
**Scope:** `STATIC/CI-SCOPED`. No guest login, AT-SPI query, key injection or
screen-reader start was performed. Final visual acceptance remains
`AWAITING_OWNER_FINAL_VISUAL_ACCEPTANCE`.

## Exact VM blocker

`VBoxManage list runningvms` reported `"Canopy-Test-Plasma6"` running. The host
artefacts show an active performance-agent VM assignment, and VM use is
serialized behind that agent:

| Artefact | UTC mtime |
| --- | --- |
| `C:/Users/X1/AppData/Local/hermes/cache/scratch/native_perf_vm_info_probe.txt` | `2026-11-28T04:32:41.730309+00:00` |
| `C:/Users/X1/AppData/Local/hermes/cache/scratch/wt-native-perf-baseline-20261127` | `2026-11-28T04:40:20.428975+00:00` |
| `C:/Users/X1/AppData/Local/hermes/cache/scratch/native_build_baseline_vm.lock` | `2026-11-28T04:04:41.680013+00:00` |

Consequence: everything below is a recomputation of previously captured native
evidence bytes plus host-side static/CI checks. It is **not** a fresh native run.

## Recomputed per-check outcomes

Evidence artifact:
`scratch/native_a11y/native_a11y_verification.json`, SHA-256
`a01d4d13d2ba28b4c6a8d26aa4ab44d6a72de7e8a29b9004c572e7dc393f5d8d`.

| Check | Outcome | Evidence |
| --- | --- | --- |
| AT-SPI accessible names | `PASS_SCOPED` | 241/248, 241/248, 221/227 named at 1920x1080, 1200x750, 760x500; recomputed from `a11y_summary.json` in the captured evidence. Scope excludes a fresh AT-SPI query. |
| AT-SPI descriptions | `NOT_CAPTURED` | 0 of 248/248/227 elements carry a `description` field. Presence, content and announcement of descriptions cannot be verified from these bytes. |
| AT-SPI roles | `PASS_SCOPED` after remediation | Observed roles `alert, application, button, check box, filler, frame, label, text`. The owned gate originally rejected 47/47/34 elements (20/20/14 by role class) as unsupported; after the fix, 0 `INVALID_ROLE` issues across 723 records. |
| Unnamed secondary labels | `DEFECT_CONFIRMED_NOT_REMEDIATED_HERE` | 7/7/6 empty-name `label` nodes, the secondary file-detail labels. The fix makes the owned gate report them (20 `EMPTY_NAME` across the three trees); the QML that creates them is outside the owned paths and was not edited. |
| Keyboard Alt+F / Escape | `PASS_SCOPED` | Evidence3 pixel diffs at all three sizes: Alt+F 21423 / 21400 / 15820 changed pixels; Escape 896340 / 797946 / 314026 changed pixels. This is menu open/close, not a focus-order claim. |
| Tab / Shift+Tab focus order | `NOT_RUN` | No traversal log or AT-SPI `state_focused` capture exists in the evidence. |
| Named-but-unreachable menus at 760x500 | `DEFECT_CONFIRMED_NOT_REMEDIATED_HERE` | `Window menu` and `Help menu` are named but absent from the extent records at 760x500 (only 4 menus have extents there). QML is outside owned paths. |
| Dock labels and geometry | `PASS_SCOPED` | All eight tiles (Browser, Mail, Files, Calendar, Photos, Music, Terminal, Settings) are named and extent-bearing at all three sizes. |
| Screen-reader announcements | `NOT_RUN` | 95 evidence text/JSON/log files scanned, 0 announcement/Orca hits. No Orca process, speech backend, caption log or AT-SPI event recording was captured or started. Static name-tree presence is not an announcement claim. |
| Null component extents | `QUALIFIED` | 56/105, 56/105 and 48/92 extent records are `extents: null`; mostly closed overlays and unmapped delegates. Geometry reachability was not demonstrated for them. |
| Full local suite | `INCONCLUSIVE` | `unittest discover -s tests` exceeded 600 s on this host; no failure was emitted before timeout, but no final result is claimed. |
| Targeted/CI-scoped tests | `PASS` | 6 new native-role regression checks, 169 accessibility-pattern tests and 55 focused metadata/keyboard tests all OK. |
| Final visual acceptance | `AWAITING_OWNER_FINAL_VISUAL_ACCEPTANCE` | Owner-gated; no visual/QML/asset change was made. |

## Bounded remediation applied

`canopy_features/accessibility/screen_reader_metadata.py` now accepts the
five native-only AT-SPI role names observed in real trees (`application`,
`check box`, `filler`, `frame`, `text`) in addition to the unchanged Classic
vocabulary, treats native `check box` as an interactive role, and requires
names for native `label`/`text` records. Callers can replace the name
requirement set explicitly with `named_roles=`. The exact Classic
`INFORMATIVE_ROLES`/`NAMED_ROLES` contract and existing call signatures remain
valid. No QML, geometry, colour, icon, wallpaper, animation, VM state or PR
outside this branch was touched.

This is a gate fix, not a runtime fix: it makes native AT-SPI metadata
validatable and surfaces the real unnamed-label defect instead of masking it
behind `INVALID_ROLE`.

## Reproduction

```sh
python -m unittest discover -s scratch/native_a11y -p 'test_*.py'
python -m unittest discover -s tests -p 'test_*accessib*.py'
python scratch/native_a11y/verify_native_a11y.py \
  C:/Users/X1/AppData/Local/hermes/cache/scratch \
  scratch/native_a11y/native_a11y_verification.json
```

The harness only reads evidence bytes and probes host VM state; it does not
connect to the guest.

## Resource impact

`NOT_RUN` for real guest RSS/CPU. `SYNTHETIC` for the Python-only gate checks:
the change adds a constant frozenset union and one bounded frozenset per
validation call, with no service, timer, thread or persistent state. No
stability, security, accessibility or approved-visual trade was made for a
performance gain. Screen-reader behaviour is explicitly `NOT_RUN`.
