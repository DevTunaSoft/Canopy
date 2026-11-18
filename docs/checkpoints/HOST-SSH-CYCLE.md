# Host-initiated approved job transport — 2026-11-18

Track 1, independent of VirtualBox provisioning and Mint guest bootstrap: `scripts/testlab_ssh_cycle.py` supports a **single** bounded host-initiated SSH/SCP job cycle. It requires a dedicated `canopy-test` user, a pre-verified and pinned SSH `known_hosts` file, an SSH identity key, and a *host-approved* immutable commit plan. It uses a loopback endpoint intended for VirtualBox NAT TCP 2222 to guest TCP 22, never a public SSH listener, and executes only the fixed existing `scripts.run_approved_test_plan` command. It reads the guest report regardless of exit and detects host/guest disagreement.

Example, after a secured Mint VM is installed and reachable:
```powershell
py -3 -m scripts.testlab_ssh_cycle --plan C:\CanopyLab\approved.json --run-id 1234567890abcdef1234567890abcdef --identity C:\CanopyLab\keys\id_ed25519 --known-hosts C:\CanopyLab\keys\known_hosts --output C:\CanopyLab\runs\test.json
```

**Before first use**, the operator must confirm the host key fingerprint through an independently trusted channel, install only the approved public key for the non-root guest account, and map VirtualBox NAT localhost:2222 to guest:22. Never accept `StrictHostKeyChecking=no`, auto-trust the first connection, or expose host secrets to the guest. The runtime is **not yet connected to an actual VM**; there is no SSH server, provisioned key, configured NAT or scheduler. Source modules inside a guest may be malicious, so host-observed SSH exit is not a substitute for independent graphical observation.

This track has synthetic mocked SSH/SCP regression tests; real Windows/Mint interaction **NOT RUN**. It does not touch other branches or any existing user's computer.
