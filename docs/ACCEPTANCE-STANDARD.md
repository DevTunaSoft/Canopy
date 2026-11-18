# Canopy Linux Mint Acceptance Standard (v1)

## Release decision

**No desktop-release PASS from GitHub unit tests or one VM process.** Canopy must run against a real Linux Mint Cinnamon X11 login session. Every **mandatory** requirement in `qa/mint-acceptance-v1.json` needs same-run evidence from at least two **genuinely independent** collection paths, tied to exact approved commit, boot identity, host snapshot and run ID. If evidence conflicts, is absent, is stale, is tampered with, or tests were skipped, mark **FAIL, BLOCKED, INCONCLUSIVE or NOT_RUN**, never PASS.

The contract includes Cinnamon boot, Classic startup, launcher keyboard actions, dock sizing, settings corruption recovery, installer rollback, VM snapshot restoration, performance, accessibility, multiple displays, security/privileges, and endurance. GPU physical-hardware and genuine suspend-resume are separate explicit hardware follow-up gates; VirtualBox alone cannot establish those.

## Rigorous autonomous test cycle

1. **Host trust boundary:** isolated VirtualBox VM `Canopy-Test-Mint`, dedicated test account, host-controlled snapshot `Canopy-Clean`. No host secret mounts, clipboard sharing or automatic public PR execution. Keep authorization and approval outside the guest. A Windows host controller reads VM identity/boot state independently.
2. **Before each approved test:** fetch and verify exact immutable Git SHA; ensure a clean checkout; issue a unique run/challenge ID and record known snapshot, observed VM UUID, Mint version and boot ID. Never reuse old result files. First ensure a positive and a deliberately failing negative control are correctly classified.
3. **Run independent pathways:** Python unit/integration tests, real GTK UI action/keyboard tests, external window enumeration and screenshot/geometry checks, user-level filesystem state checks, host-side VM/process/boot monitors, security permission checks, memory/CPU baselines. Distinct observers must use separately controlled collection processes and independently inspect actual state.
4. **Adversarial experiments:** intentionally corrupt settings, attempt root launch, request nonexistent app, simulate crash/timeouts, remove dependencies, change screen size, interrupt install (on resettable VM only), supply fake PASS and stale reports, and induce resource pressure. Record expected vs observed failure and recovery.
5. **After each test:** copy hashed reports outside VM first; independently validate report integrity, artifact bytes and actual host-observed process exit/state; compare per-case evidence by run ID and approved SHA. Mark any inconsistency as INCONCLUSIVE; no green release result.
6. **Reset and retest:** return disposable VM to a known snapshot between destructive scenarios, verify fresh guest boot identity and recover Cinnamon. Keep resets explicitly authorized only for the named test VM; snapshot restore destroys guest writes.
7. **Repeated execution:** test cold/warm startup, randomized action sequences with deterministic seeds, many app entries, 320px and HiDPI/multimonitor sizes, prolonged idle/resource stress and repeated start/stop. Record repeat count, seed, environment and flakiness.
8. **Ship only after:** a human reviews representative captured images, accessibility issues are addressed, rollback works, true Mint tests pass, and physical-hardware limitations are explicitly disclosed.

## Non-goals and security boundaries

An arbitrary code runner inside the guest is not secure merely because it validates its own input. Signed or externally approved plans, external hash verification, host-observed results and a disposable VM are required. No background chat agent can directly operate a PC without user-provisioned authorized host software. The initial controller performs limited VM operations and is **not** an unattended orchestration service yet.

Never install a self-hosted public PR runner with access to the Windows host. Keep the Windows host controller small, explicit and reviewable. CI may validate logic on Windows/Ubuntu while target Linux Mint support remains **NOT RUN**.

## Evidence statuses

- **PASS:** full mandatory conditions satisfied by independent, matching, current evidence
- **FAIL:** a confirmed incorrect behavior or negative control not detected
- **BLOCKED:** infrastructure or prerequisite unavailable
- **INCONCLUSIVE:** observations conflict or cannot be authenticated
- **NOT_RUN:** scenario has not been executed

Update this contract, roadmap, handoff, traceability, actual test records and release notes together. Do not silently weaken mandatory checks or remove previously documented requirements.
