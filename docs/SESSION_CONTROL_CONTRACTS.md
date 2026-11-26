# PE-048 session control contracts

Status: **implemented, offline-only**. Base and exact integration tip:
`c6de24153eef0b58f921a8bffdaeaa8033288a75`
(`integration/canopy-classic-20261123`). This change owns only
`canopy_features/system/session_controls.py`,
`tests/test_pe048_session_controls.py` and this document. It changes no
compiled source, QML, approved artwork, workflow, protected path, PR #279 path
or `main`. No VM was contacted and no VM credential was used or required.

## Purpose and safety boundary

`evaluate_native_path()` is a pure decision surface for the two privileged
session actions `logout` and `shutdown`. It produces an inert `NativePath`
description for a trusted host adapter; it does not run a command, open a
socket, call D-Bus, read the environment, poll, wait, change credentials or
alter the session. An allowed decision is **not** execution and **not** an
authorization to execute inside this process.

Existing contracts are reused rather than extended:

- `canopy_core.host_events`: `TOPICS` and `PROTOCOL_VERSION` are imported; the
  existing `session.state.changed` topic is referenced as an observation name,
  with no fifth topic, new field, emit or subscription.
- `canopy_features.system.quick_controls_state`: its reason codes and
  disclosures are reused verbatim. That module already refuses privileged
  host changes; logout and shutdown stay in that class.
- `canopy_features.security.privilege_boundary`: any caller-supplied
  command-shaped candidate is first checked by the existing deny gate and is
  then refused unconditionally. Even a candidate that gate would allow is
  refused here: this contract accepts no executable vector at all.

No raw power command is constructed, stored, emitted or executed. The module
contains no executable name, method name, shell fragment or transport string;
the only `shutdown` text is the abstract action token.

## Inputs and refusals

A path is described only when all of the following explicit facts agree:

1. `action` is exactly `logout` or `shutdown`.
2. `NativeCapability` names an allowlisted abstract interface, the same
   action, an exact `bool` availability and a bounded provenance token.
   `"logind"` supports logout and shutdown; `"session-manager"` supports
   logout only.
3. `Confirmation` names the same action and interface, has `confirmed is True`
   and a bounded provenance token.
4. No `command_candidate` argument is supplied. An explicitly supplied `None`
   counts as a candidate and is refused.

Every absent, unavailable, mismatched, malformed or hostile fact fails closed
with a stable reason and `path=None`:

| Reason | Meaning |
| --- | --- |
| `invalid-action` | action token is not one of the two owned actions |
| `no-host-interface` | interface does not support the requested action |
| `bridge-disabled` | capability was explicitly reported unavailable |
| `invalid-grant` | capability and confirmation disagree on action or interface |
| `unconfirmed` | no explicit affirmative confirmation |
| `raw-command-refused` | a command-shaped candidate was supplied |

Wrong container types, non-string tokens, control characters, oversized
provenance, `1` used as a boolean and direct `NativePath` construction with an
unsupported action all raise the module's `SessionControlsError`. No raw
`TypeError` or `KeyError` escapes to a caller.

`NativePath.to_dict()` and `Decision.to_dict()` return fresh mappings with
`executed: false`, an explicit `execution` token and no `argv`, `command`,
executable path, D-Bus call or credential field.

## Verification (targeted only)

Commands run from the exact worktree at the final head:

```text
python -m unittest tests.test_pe048_session_controls -v
Ran 25 tests
OK
python -m py_compile canopy_features/system/session_controls.py tests/test_pe048_session_controls.py
exit 0, no output
```

RED before the production module existed: `Ran 25 tests`, `FAILED (errors=25)`,
import failure for `session_controls`, captured in
`evidence/session_controls/red.log` (rc 1). GREEN after implementation is in
`green.log` (rc 0). A synthetic scratch mutation removed only the
availability guard; the real module denied with `bridge-disabled` while the
mutant allowed the same unavailable capability with `ok`. Production bytes
were unchanged before and after (`MUTANT_SENSITIVE=PASS`), recorded in
`mutation.log`. Evidence lives at
`scratch/master_directive_20261126/evidence/session_controls/` with a
`.sha256` sidecar; every SHA-256 there is recomputed from on-disk bytes.

Full `unittest discover -s tests` is **NOT_RUN** by this bounded task; only the
owned module's targeted tests were run. No Qt build, CI artifact, compiled
self-test or full-suite comparison is claimed here.

- `SYNTHETIC` — 25 pure-Python tests using only in-memory objects; one scratch
  source mutant; no network, VM, real session, process spawn or host probe.
- `NOT_RUN` — real Mint logout/shutdown, D-Bus/logind handoff, VM session
  proof, Qt wiring, compiled runtime, screen-reader behavior, real PSS/CPU
  profile and owner visual acceptance. No acceptance verdict is claimed for
  any of them. No VM credentials were needed or used.

Resource impact: `SYNTHETIC` bounded work only. The module allocates a few
small frozen records on an explicit call; it has no timer, cache, polling,
background wakeup, retained state, I/O or process. There is no UI, icon,
geometry or announcement surface, so screen-reader behavior is unchanged and
no stability, security, accessibility or approved-visual tradeoff is made for
a resource gain.
