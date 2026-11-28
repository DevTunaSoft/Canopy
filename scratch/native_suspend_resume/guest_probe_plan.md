# Read-only host capture plan (NOT RUN)

The commands below are **prospective** and were not executed in this change.
They are the owner's bounded, one-shot way to collect the text consumed by
`tools/session_recovery/probe_readonly.py`. No command suspends or resumes the
host; none starts a daemon or loops. Run each once on the owned disposable
guest, then pass the captured files to the tool.

```sh
# Existing read-only interfaces only; no new service, no polling loop.
loginctl show-session "$XDG_SESSION_ID" -p Active -p LockedHint -p State -p Type > pre_logind.txt
upower -i /org/freedesktop/UPower/devices/battery_BAT0 > pre_upower.txt
# Host-status file produced by the trusted host, not by this tool:
#   state=<active|locked|suspended|unknown>  -> pre_plasma.txt
python tools/session_recovery/probe_readonly.py \
  --logind-file pre_logind.txt \
  --upower-file pre_upower.txt \
  --plasma-file pre_plasma.txt
```

Repeat the same one-shot captures after a real suspend/resume cycle to obtain
post-state text. The tool still labels its own output `STATIC SOURCE ONLY`:
a native runtime verdict requires the trusted host to supply confirmed
suspend/resume, preservation and re-observation facts to
`PlasmaRecoveryIntegration`, and then label that snapshot `NATIVE RUNTIME`.

`BLOCKED_NOT_RUN` remains the verdict for this change: no guest, no real
suspend/resume, no compiled Qt run and no approval were performed.
