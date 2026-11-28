# Fedora Kinoite foundation validation for Canopy (M4/LacOS)

**Status: evidence-gated validation, NOT a production foundation decision and NOT a merge request for acceptance.**
Owner directive SHA `79e30d79` (cap 8), supplemental directive file SHA-256
`13839892dc997b86965198ee3bf1eb0315d60427b95c7ef5fd6e30cbdc34a3de`, section 8
("Fedora Kinoite and upstream independence"). Branch
`research/kinoite-foundation-20261127`, exact base `ec910d7a7275296ecbc8b5e5c459d356205165d1`
(`origin/integration/canopy-plasma6-20261127`). Target: **draft PR only, no merge, no self-approval**.
This change owns only `docs/LACOS_KINOITE_VALIDATION.md`, `scratch/kinoite_validation/**`,
`tools/kinoite/**`. No visual assets, shell code, CI config or protected files are touched.

`docs/LACOS_VISION.md` still describes a future Mint-derived distribution and remains
unchanged. This document supplies Kinoite evidence to that decision; it does **not**
permanently select the production foundation, does not build or maintain a custom image,
and does not alter native Plasma/Classic work.

## Evidence labels and verdicts

- **STATIC SOURCE ONLY** — claim is supported by verbatim text retrieved from an
  official upstream URL. It is not a claim that the command was run on Kinoite here.
- **NATIVE RUNTIME** — a command actually executed on a real system. Every such row
  below states which system; none of them is a Kinoite session.
- `PASS` / `FAIL` / `BLOCKED` / `NOT RUN` are used literally. A documentation `PASS`
  never upgrades a `NOT RUN` runtime check.

## Runtime environment probe (NATIVE RUNTIME, Windows host)

Executed by `tools/kinoite/validate_evidence.py`:

- `shutil.which` for `rpm-ostree`, `ostree`, `flatpak`, `podman`, `docker`, `toolbox`:
  all absent.
- `wsl.exe -l -v`: "Windows Subsystem for Linux has no installed distributions."
- `VBoxManage.exe list vms`: `Canopy-Test-Mint`, `Canopy-Test-Plasma6` (an
  **Ubuntu (64-bit)** VM, running and shared with other agents), and one inaccessible
  entry. No Kinoite VM, no disposable Atomic guest.

Therefore all Fedora Kinoite runtime checks are **NOT RUN**, with blocker
**BLOCKED: no disposable Fedora Kinoite environment on this host**. No result below
is laundered into a runtime pass.

## Evidence matrix

| ID | Check | Evidence class | Verdict |
|---|---|---|---|
| E01 | Official Kinoite deployment path (image + verified install media) | STATIC SOURCE ONLY | PASS |
| E02 | Atomic update commands (`rpm-ostree upgrade`, `--check`, `status`) | STATIC SOURCE ONLY | PASS |
| E03 | Rollback, pinning and exact-version deploy | STATIC SOURCE ONLY | PASS |
| E04 | Major Fedora upgrade / rebase between Atomic Desktops | STATIC SOURCE ONLY | PASS |
| E05 | Security, kernel and driver update path | STATIC SOURCE ONLY | PASS |
| E06 | Read-only core behavior (`/`, `/usr`, writable `/etc`, `/var`) | STATIC SOURCE ONLY | PASS |
| E07 | Stock Plasma fallback path | STATIC SOURCE ONLY | PASS (session chooser behavior NOT RUN) |
| E08 | User-level Canopy extension compatibility | STATIC SOURCE ONLY + host planner execution | PASS (Kinoite runtime NOT RUN) |
| E09 | Operation without LacOS-specific infrastructure | NATIVE RUNTIME (Windows host source scan + planner) | PASS (host scope only) |
| E10 | Independent Flatpak/Flathub app updates | STATIC SOURCE ONLY | PASS |
| E11 | Independent DNF path (Toolbx; layering for host-level packages) | STATIC SOURCE ONLY | PASS |
| E12 | No custom image maintenance required for the proposed extension model | STATIC SOURCE ONLY | PASS (custom image NOT RUN / not built) |
| E13 | Native Kinoite update/rollback/read-only/Plasma/Flatpak/DNF execution | NATIVE RUNTIME | NOT RUN (BLOCKED) |

Machine-readable details, including every verbatim quote and artifact digest, are in
`scratch/kinoite_validation/evidence_matrix.json`; `SHA256SUMS.txt` in that directory
covers 47 artifacts and verifies with `sha256sum -c` (47 OK).

## 1. Official deployment path — E01, STATIC SOURCE ONLY, PASS

Official Fedora sources describe Kinoite as "a variant of Fedora KDE Plasma Desktop",
provide an OSTree ISO/qcow2 download page with OpenPGP-signed checksums, and document
installing Atomic Desktops with the same installer as other Fedora variants:

1. Download the official image from <https://fedoraproject.org/atomic-desktops/kinoite/download/>.
   At fetch time the page offered Fedora Kinoite 45; verify with the published
   `CHECKSUM` file and `curl -O https://fedoraproject.org/fedora.pgp` as documented
   there. Do not treat a version number in this doc as a permanent pin.
2. Write bootable media with Fedora Media Writer and install normally:
   <https://docs.fedoraproject.org/en-US/fedora-kinoite/installation/>.
3. Rebase route documented upstream for an already-installed Atomic Desktop:
   `rpm-ostree rebase fedora:fedora/45/x86_64/kinoite` (the upstream guide shows the
   same form with `silverblue`; the branch name must be re-read from
   `ostree remote refs ${ID}` before use).

Upstream text also states that Flatpak apps and `/home` files persist across rebases.
No custom compose, kickstart, image build or fork is proposed here. Native install and
rebase: **NOT RUN**.

## 2. Atomic updates, rollback and major upgrades — E02/E03/E04, STATIC SOURCE ONLY, PASS

Exact upstream commands from
<https://docs.fedoraproject.org/en-US/fedora-kinoite/updates-upgrades-rollbacks/> and
<https://coreos.github.io/rpm-ostree/administrator-handbook/>:

```sh
rpm-ostree status --verbose
rpm-ostree upgrade --check
rpm-ostree upgrade
sudo systemctl reboot                    # apply the staged deployment
rpm-ostree rollback && sudo systemctl reboot
sudo ostree admin pin 0                  # guard a known-good deployment
rpm-ostree deploy 45.YYYYMMDD.N          # exact historical version
rpm-ostree cleanup --rollback
source /etc/os-release && ostree remote refs ${ID} | grep $(arch) | grep ${VARIANT_ID}
rpm-ostree rebase fedora:fedora/<N>/<arch>/kinoite
```

Upstream facts verified verbatim: updates stage offline and take effect on reboot;
the temporary rollback is the previous GRUB entry; `rpm-ostree rollback` permanently
swaps the default deployment; OSTree keeps only the two most recent deployments by
default; updating after a rollback undoes it; pinning protects a deployment from
cleanup; layered packages and `/home` state persist across rebases. Major releases
must be taken one at a time (upstream says skipping releases is untested/unsupported).
Native execution of every command above: **NOT RUN**.

## 3. Read-only core and immutable integrity — E06, STATIC SOURCE ONLY, PASS

Verified from Fedora's technical information page and the rpm-ostree/libostree
handbooks:

- root `/` is mounted read-only; `/usr` and everything below it is read-only;
- `/etc` and `/var` are writable configuration/runtime state;
- `/home → /var/home`, `/opt → /var/opt`, `/usr/local → /var/usrlocal`, etc.;
- libostree creates a read-only bind mount over `/usr`;
- `rpm-ostree install` recomposes a new deployment instead of mutating the booted
  root; `rpm-ostree usroverlay` is explicitly transient and does not survive reboot.

Consequence for Canopy: no Canopy component may require writing `/usr`, installing an
RPM with `dnf install` on the host, or replacing system files. The user-level model
below satisfies that constraint by construction. Native `findmnt -no OPTIONS /usr`
and write-denial probe: **NOT RUN**.

## 4. Stock Plasma fallback — E07, STATIC SOURCE ONLY, PASS (runtime NOT RUN)

Fedora's Kinoite page states it "includes the latest versions of the modern and
modular desktop, built by the KDE community"; the guide identifies Kinoite as the
Atomic variant of Fedora KDE Plasma Desktop. SDDM's upstream theming doc states its
session model parses `.desktop` files in `/usr/share/xsessions` (a read-only path on
Kinoite) and exposes a session selection control. KDE's Autostart documentation
confirms `$HOME/.config/autostart` user entries and user overrides of distribution
autostart files.

The Canopy Phase 1 design in `docs/MINT_SESSION_ARCHITECTURE.md` is deliberately an
**application entry**, not a session replacement: it never replaces the display
manager, compositor or window manager. Therefore the stock Plasma session remains
in the base image and the documented fallback is to log out and choose the stock
Plasma session (or disable the user-level entry/autostart). No custom session file is
installed into `/usr/share/xsessions` by this work.

Honest gap: a *future* user-level Canopy **session** entry
(`~/.local/share/xsessions`) is described in
`canopy_features/installer/session_entry_validation.py`, but the SDDM source above
only documents `/usr/share/xsessions`. Whether SDDM on the exact Kinoite release
enumerates per-user session entries must be proven in the guest; that check is
**NOT RUN**, and no fallback claim is made for that future mode.

## 5. User-level Canopy extension — E08/E09, PASS in static/host scope; Kinoite runtime NOT RUN

Existing repository evidence (unchanged by this PR):

- `docs/CLASSIC_INSTALL_RECOVERY.md`: exactly two managed files under
  `XDG_DATA_HOME` (default `~/.local/share`):
  `$XDG_DATA_HOME/applications/org.canopy.ClassicPreview.desktop` and
  `$XDG_DATA_HOME/canopy/classic-preview/ownership.json`; root/system paths,
  symlinked components and `..` traversal fail closed; uninstall deletes only owned
  files with one-file byte rollback.
- `docs/MINT_SESSION_ARCHITECTURE.md`: no system file, session, compositor or
  display-manager change; no duplicated compositor.
- `canopy_features/xdg_user_paths.py`-style XDG handling and
  `canopy_features/apps/environment_allowlist.py` explicitly include
  `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_CURRENT_DESKTOP` and `DESKTOP_SESSION`.
- systemd upstream `systemd.unit(5)` documents `~/.config/systemd/user/*` and
  `$XDG_DATA_HOME/systemd/user` as valid user-unit locations; Fedora documents
  `/home → /var/home` and writable `/etc`/`/var`. A user-level Canopy extension
  therefore has a standards-defined place to live without writing the immutable core.

Real host commands executed (see `scratch/kinoite_validation/planner_*.json`):

```sh
python3 -m canopy_features.mint.install_recovery_plan --home <scratch>/empty_home --action snapshot
python3 -m canopy_features.mint.install_recovery_plan --home <scratch>/empty_home --action install --binary <scratch>/canopy-classic-demo
```

Observed: `dry_run=true`, `performs_changes=false`, `privileged=false`,
`session_changes=[]`, `system_paths_written=[]`, `guest_execution=NOT_RUN`,
`native_mint_session_acceptance=NOT_RUN`; snapshot `safe=true` with both session
entry probes `ABSENT`. A scan of 248 tracked files under `canopy_features/`, `tools/`
and `prototype/` found **zero** `LacOS` references, i.e. no LacOS daemon/service
dependency in the code surface. These are **NATIVE RUNTIME (Windows host, NOT
Kinoite)** checks of pure-Python planning code, not proof of a running systemd user
manager, compositor or desktop on Kinoite. Those remain **NOT RUN**.

## 6. Independent application updates — E10/E11, STATIC SOURCE ONLY, PASS

Flatpak/Flathub (official Flatpak docs and Fedora Atomic guide):

```sh
flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install flathub <application-id>
flatpak update
flatpak list
```

Fedora states Flatpak is the primary GUI app mechanism and that Flathub works out of
the box on Atomic Desktops; Flatpak documents system-wide and per-user installations,
GPG-verified remotes and fine-grained sandbox permissions. Flatpak apps and runtimes
are installed outside the OSTree deployment, so their update path is separate from
`rpm-ostree upgrade`; exact cross-rollback behavior on Kinoite is **NOT RUN** and is
not claimed here. Native execution: **NOT RUN**.

DNF/RPM path without mutating the immutable host:

```sh
rpm-ostree search <package>             # host-visible Fedora package search
rpm-ostree install <package>            # layered deployment, reboot to apply
sudo rpm-ostree upgrade && sudo systemctl reboot
toolbox create
toolbox enter
sudo dnf upgrade                        # inside the Toolbx container
```

Fedora's DNF page explicitly says DNF applies to standard Fedora editions and that
package management works differently on image-based variants; Fedora's Toolbx page
documents `toolbox create` / `toolbox enter` and DNF inside the container; the Kinoite
FAQ says to use `rpm-ostree install` instead of `dnf install` on the host. Layering
is persisted by rpm-ostree across upgrades but should be sparse. Native execution:
**NOT RUN**.

## 7. Security, kernel and driver updates — E05, STATIC SOURCE ONLY, PASS / runtime NOT RUN

Fedora's Kinoite page states each version is updated for approximately 13 months and
updates take effect on reboot, with a previous version kept. Kernel and driver
updates arrive in composed OSTree commits via `rpm-ostree upgrade` and a reboot. For
out-of-tree drivers Fedora documents the explicit exception path:

```sh
rpm-ostree install kmod-nvidia xorg-x11-drv-nvidia
rpm-ostree kargs --append=rd.driver.blacklist=nouveau,nova-core
```

with Secure Boot signing noted upstream. This is the justified exception class for
layering/kargs, not a reason to fork or maintain a custom image. Actual security,
kernel and driver update verification on a Kinoite guest: **NOT RUN**.

## 8. Custom image policy — E12, STATIC SOURCE ONLY, PASS

Proposed path: stock Fedora Kinoite image + user-level Canopy extension + Flatpak
apps + Toolbx/layering only where the host genuinely needs it. Upstream guidance is
to use layering sparingly and prefer Flatpak/Toolbx. No custom image, compose,
kickstart, fork or maintained overlay is created by this PR. A custom image would
need separate justification (for example a hardware/OEM driver requirement that
cannot be met with documented kargs/layering), owner approval and its own evidence
chain; it is **NOT RUN** here.

## 9. Reproduction

```sh
# from the branch worktree
python3 tools/kinoite/fetch_sources.py --out scratch/kinoite_validation
python3 tools/kinoite/validate_evidence.py --worktree . --out scratch/kinoite_validation
cd scratch/kinoite_validation && sha256sum -c SHA256SUMS.txt
```

Latest executed result: `static_gate=PASS`, `native_runtime=NOT_RUN`,
checks E01–E12 `PASS`, E13 `NOT RUN`; `sha256sum -c SHA256SUMS.txt` returned 47 OK.
The gate is deterministic over the frozen source text in
`scratch/kinoite_validation/sources/`; re-running the fetch against changed upstream
pages legitimately changes digests and must be re-verified.

## 10. Acceptance boundary and resource note

- Foundation evidence classification: `STATIC SOURCE ONLY PASS`, `NATIVE RUNTIME NOT RUN (BLOCKED)`.
- No merge, no self-approval, no CI claim, no production foundation selection, no
  visual change, no compiled code change, no custom image.
- Native Kinoite session behavior, compositor interaction, real update/rollback
  cycle, accessibility/screen-reader behavior, PSS/RSS and CPU measurements: **NOT_RUN**.
- Resource impact: none measurable from this docs/tools-only change; no trade of
  stability, security, accessibility or approved visuals for a resource gain.

## Sources

All sources were fetched with HTTP 200 and stored verbatim. Digests below are of the
generated plain-text projection in `scratch/kinoite_validation/sources/`; full digests
and final URLs are in `sources.json` and `SHA256SUMS.txt`.

1. Fedora Atomic Desktops guide — <https://docs.fedoraproject.org/en-US/atomic-desktops/> — `e826f10acbd3`
2. Getting started — <https://docs.fedoraproject.org/en-US/atomic-desktops/getting-started/> — `e61a088fb29c`
3. Updates, upgrades and rollbacks — <https://docs.fedoraproject.org/en-US/atomic-desktops/updates-upgrades-rollbacks/> — `081f80f3780d`
4. Technical information — <https://docs.fedoraproject.org/en-US/atomic-desktops/technical-information/> — `d6e990c64826`
5. FAQ — <https://docs.fedoraproject.org/en-US/atomic-desktops/faq/> — `56bd7f330245`
6. Installation — <https://docs.fedoraproject.org/en-US/atomic-desktops/installation/> — `3d70f4325332`
7. Tips and tricks — <https://docs.fedoraproject.org/en-US/atomic-desktops/tips-and-tricks/> — `657c12b16cf5`
8. Troubleshooting — <https://docs.fedoraproject.org/en-US/atomic-desktops/troubleshooting/> — `df516deb2d3f`
9. Toolbx — <https://docs.fedoraproject.org/en-US/atomic-desktops/toolbox/> — `e9c57fa576b7`
10. Fedora Kinoite project page — <https://fedoraproject.org/atomic-desktops/kinoite/> — `9816ee44e0da`
11. Fedora Kinoite download — <https://fedoraproject.org/atomic-desktops/kinoite/download/> — `06ae84929a78`
12. Fedora DNF quick doc — <https://docs.fedoraproject.org/en-US/quick-docs/dnf/> — `9ddbb7e281a4`
13. rpm-ostree administrator handbook — <https://coreos.github.io/rpm-ostree/administrator-handbook/> — `76a4ce1cf310`
14. libostree adapting-existing — <https://ostreedev.github.io/ostree/adapting-existing/> — `6dd8a24d8e06`
15. Flatpak: Using Flatpak — <https://docs.flatpak.org/en/latest/using-flatpak.html> — `0f44ecbdd115`
16. Flatpak: Sandbox permissions — <https://docs.flatpak.org/en/latest/sandbox-permissions.html> — `ca25eb478df5`
17. systemd.unit(5) — <https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html> — `111a3d771453`
18. KDE Plasma session management — <https://docs.kde.org/stable_kf6/en/plasma-desktop/kcontrol/kcmsmserver/> — `ed1519b2cc61`
19. SDDM upstream theming/session model — <https://raw.githubusercontent.com/sddm/sddm/develop/docs/THEMING.md> — `83c3c3176f20`
20. KDE Plasma autostart — <https://docs.kde.org/trunk_kf6/en/plasma-workspace/kcontrol/autostart/index.html> — `3b892638bb29`
