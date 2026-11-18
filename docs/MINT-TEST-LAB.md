# Canopy Mint Test Lab — unattended runner prototype

## Purpose

Prepare a reproducible, **unprivileged** test command for a future isolated Linux Mint Cinnamon VM. The VM, remote control and self-hosted runner are **not installed** by this PR. The controller performs only fixed, allowlisted checks and writes a JSON report. It cannot provision VirtualBox, alter the display manager, drive an interactive Cinnamon session, restore VM snapshots, or give a chat assistant direct remote-desktop access.

## Execute on the future Mint VM

On a trusted checkout of an approved commit, from the repository root:

```bash
python3 scripts/mint_testlab.py --output test-results/mint-testlab.json
```

Checks: `unit` (standard Python unit suite), `syntax` (Python compileall), and `gtk` (system Python GTK tests under Xvfb). Optional flags: `--checks unit syntax`, `--timeout 120`, `--root /path/to/Canopy`. Each check is timed out separately; maximum configured timeout is 900 seconds. Failed or missing prerequisites result in FAIL or BLOCKED, never a fabricated PASS. JSON includes command status, capped output and runtime. Missing `xvfb-run` causes BLOCKED. Exit 0 only when all selected checks pass.

**Required Mint prerequisites:** `python3`, `python3-gi`, `gir1.2-gtk-3.0`, `xvfb` and `xauth`, installed separately by the machine owner or an explicitly approved setup process. These commands do not install software or require root.

## Security, collection and limitations

Use only a disposable, dedicated Mint VM and dedicated, least-privilege testing account. Do not register a public PR-triggered self-hosted GitHub Actions runner on a personal computer: PR code may be untrusted. Prefer a separate private repository with manually approved commit IDs and restricted artifact upload. VM startup, login, cloning approved refs, artifact upload and snapshot reset must be designed and authorized separately.

The output report may contain application logs and machine metadata. Review/strip secrets and personal information before publishing artifacts. Reports are written to `test-results/` (gitignored). The script does not collect screenshots or control GUI application windows. The GTK smoke tests run inside Xvfb, not a live Cinnamon session.

## Verification

New runner's pure Python tests pass in the development container. CI and Mint results must be checked independently after committing. Linux Mint desktop, graphics, power-state tests and autonomous remediation: **NOT RUN**.

## Next acceptance gates

1. Stand up isolated Mint Cinnamon VM and snapshot a pristine install.
2. Configure approved-commit-only command execution and bounded logs with no access to host secrets.
3. Execute this runner as an ordinary Mint user, verify JSON report and artifact retention.
4. Add Cinnamon-session GUI automation and screenshots using explicit display/session setup.
5. Validate recovery of the VM from disposable snapshots; prohibit untrusted code from controlling the host or installing system services.

## Automated visual-evidence capture (new prototype)

`scripts/capture_classic.py` launches the existing Classic preview with in-memory defaults inside an **isolated Xvfb display** and saves **only the two Canopy preview windows** (`top-bar.png` and `dock.png`) plus `captures.json`. It does not capture a full personal desktop, inspect other windows or change persistent preferences. It refuses to start without `CANOPY_ISOLATED_DISPLAY=1` and an X11 `DISPLAY` argument; this is a guard against accidental use, **not** a security sandbox. Run this only in a dedicated disposable VM or GitHub-hosted test process.

To capture after approved dependencies are installed:

```bash
CANOPY_ISOLATED_DISPLAY=1 PYTHONPATH=. xvfb-run -a /usr/bin/python3 scripts/capture_classic.py --output-dir test-results/visual
```

The existing GitHub-hosted GTK workflow now attempts this capture and uploads a short-lived three-day artifact, alongside running the existing smoke tests. The generated directory is gitignored. Before connecting to a future Mint VM, restrict the test worker to approved commits, provide an isolated display and verify captures contain no sensitive host content. GTK screenshots are **visual evidence**, not proof of correct interaction, accessibility, session recovery or responsiveness. Real Cinnamon desktop capture/interaction has **not** been implemented.

GitHub workflow capture must pass before considering this increment verified. Check the job logs and verify the artifact actually contains two readable PNG images. Graphical acceptance on Mint remains NOT RUN.

## 2026-11-18 — Fail-closed graphical readiness

The GTK check now launches an explicit `xvfb-run` graphical initialization probe with `/usr/bin/python3` and GTK3 introspection **before** running the test suite. Previously, a unittest suite with skipped graphical tests could still exit zero and be marked PASS. Missing `xauth`, system Python/GTK, Xvfb, or a nonfunctional GTK virtual display now returns **BLOCKED** instead. The readiness probe runs with a separate 15-second maximum timeout, and tests cover both blocked and successful paths. This doesn't establish that tests perform real Cinnamon integration: they still use an isolated Xvfb display. Do not treat a PASS as Mint visual acceptance.
