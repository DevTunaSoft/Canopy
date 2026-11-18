# Host-to-Mint SSH cycle and replay safeguards

The host starts only fixed, approved test commands over key-only SSH to localhost NAT forwarding. The guest report is untrusted until independent host verification. The host requires a pinned SSH host key and an approved commit, refuses a pre-existing host report, and checks that the guest report path for the new run ID does not already exist before starting a test.

Negative-control tests confirm stale host/guest report detection. A guest could still race the remote-file check or fabricate its own report. A future atomic guest-side claim protocol, authenticated provenance, and independent visual observation are required for release acceptance.

Actual Mint VM, SSH transport and Cinnamon runtime execution remain NOT RUN.
