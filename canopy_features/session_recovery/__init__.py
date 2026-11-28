"""Read-only-first M4 session recovery contracts.

This package models Plasma/KWin/logind/UPower suspend/resume recovery at a
trusted host boundary. It performs no suspend or resume, opens no bus, starts
no daemon, thread, timer or poll loop, and does no filesystem, process or
network I/O. See ``docs/NATIVE_SUSPEND_RESUME_CONTRACT.md`` for the contract
and non-claims.
"""
