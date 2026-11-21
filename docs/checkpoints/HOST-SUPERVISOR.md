# Windows host-side bounded supervisor — 2026-11-18

`scripts/testlab_host_supervisor.py` is a **one-shot** coordinator for an approved immutable test plan (not a daemon). It validates dedicated host file paths, exact VirtualBox VM UUID, host-owned evidence storage and SSH key/known_hosts; uses a process-crash-released OS file lock, checks/starts the dedicated VM if powered off, creates a unique run ID, executes the existing pinned-key SSH test cycle, independently checks the saved guest report for contradictions, records SHA256 evidence and saves the host state atomically. It does not regard a passing guest suite as a Canopy release PASS, returning `PASS_TEST_SUITE_NOT_RELEASE` and `release_certified=false`.

Repeated execution with the same approved plan **skips already-green results**. Failed/inconclusive plans are limited to three runs; after that the host records `BLOCKED_ATTEMPT_LIMIT` until a new approved plan arrives. The current supervisor does not automatically reset a running VM or loop forever. It must not have a public GitHub PR trigger or access to private host folders from the guest. Host state and keys remain outside VM shares.

Configuration JSON example (place outside repository and guest; replace files and VM UUID):
```json
{
  "vboxmanage": "C:\\Program Files\\Oracle\\VirtualBox\\VBoxManage.exe",
  "expected_vm_uuid": "11111111-2222-3333-4444-555555555555",
  "ssh_key": "C:\\CanopyLab\\secrets\\id_ed25519",
  "known_hosts": "C:\\CanopyLab\\secrets\\known_hosts",
  "plan": "C:\\CanopyLab\\approved-plan.json",
  "evidence_directory": "C:\\CanopyLab\\evidence",
  "ssh_port": 2222
}
```

```powershell
py -3 -m scripts.testlab_host_supervisor --config C:\CanopyLab\host-config.json
```

Requires Python, VirtualBox, installed Linux Mint guest, pinned SSH and approved clean source checkout; none are yet connected. Mocked unit tests cover host start, evidence hashing, duplicate avoidance, retry limits, false-green and wrong VM identity. A Windows scheduled task or startup service can call the one-shot command after explicitly authorized setup, but **no scheduled task is installed** by this branch. Real VM, Cinnamon graphics and independent trusted physical host observation NOT RUN.
