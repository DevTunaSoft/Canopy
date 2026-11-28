# Native Plasma display verification blocker (exact, `NOT_RUN`)

This task wired a compiled host adapter; it did **not** run a real Plasma
session. Nothing below is a product PASS or FAIL claim.

## Host and guest facts observed

| Check | Exact command | Artifact | Observed |
| --- | --- | --- | --- |
| Running VMs | `VBoxManage list runningvms` | `blocker_vbox_runningvms.txt` | `Canopy-Test-Plasma6` is running (UUID `3aecd840-...`). |
| VM configuration | `VBoxManage showvminfo Canopy-Test-Plasma6 --machinereadable` | `blocker_vbox_vminfo.txt` | `VMState="running"`, `nic1="nat"`, forwarding `guestssh,tcp,127.0.0.1,2223,,22`, `GuestAdditionsRunLevel=1`. |
| Guest properties | `VBoxManage guestproperty enumerate Canopy-Test-Plasma6` | `blocker_vbox_guestprops.txt` | Only host-provided properties; no guest channel properties. |
| Guest execution | `VBoxManage guestcontrol Canopy-Test-Plasma6 run --exe /bin/uname --wait-stdout` | `blocker_guestcontrol_attempt.txt` | rc=1, `VBOX_E_IPRT_ERROR`: "The guest execution service is not ready (yet)". No credentials were guessed or used. |
| SSH material | `ls -la C:/Users/X1/.ssh` | `blocker_ssh_material.txt` | `known_hosts`, `known_hosts.old` only; no private key and no supplied guest login was given to this task. NAT port 2223 answers, but no authenticated session was opened. |
| Compiled artifact format | Python byte-prefix read of the built binary | `blocker_binary_format.txt` | `b'MZ'`, `.exe`: a Windows PE, not a Linux executable. |

## Why the real response was not run

1. A real Plasma display-change test needs a Linux-built binary of this exact
   head inside the guest. The only binary compiled here is a Windows UCRT64
   `.exe`; no in-guest build was performed.
2. The guest execution service reports not ready, and this session has no
   authorized guest login material. Guessing credentials is not permitted,
   and no interactive VM session was taken over from another worker.
3. No real monitor add/remove or 150%/200% scale change was injected into the
   guest; doing so would need exclusive session ownership plus a reversible
   display-configuration step, neither of which was granted here.
4. Consequently there is no in-guest adapter JSON, no compositor observation,
   no screenshot at any resolution and no accessibility announcement.

## Next action to close (not performed)

1. Serialize an owned guest lease and provision an authorized login/guest
   additions channel.
2. Build this exact head natively in the guest; record its SHA-256.
3. Run the compiled adapter once with `--native-display-json` and a real
   screen-change injection, capture the probe JSON, compositor logs and
   screenshots at 1920x1080, 1200x750 and 760x500 plus 150%/200% scale.
4. Only then assign `NATIVE_RUNTIME PASS`/`FAIL` after independent review.
   A compiled self-test or Python parity gate cannot substitute for it.
