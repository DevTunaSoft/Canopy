"""LacOS atomic-update foundation (read-only-first contract, P1).

This package defines a bounded transaction *contract* for an
rpm-ostree/Kinoite-style immutable update. It is pure, in-process policy:
no process spawn, no D-Bus, no filesystem or network I/O, no host
observation, no command strings, no privileges and no core mutation.

Every decision is a description for a trusted host adapter. Nothing here
executes an update or a rollback; activation is always deferred to the
host's reboot boundary. Real-guest behavior is explicitly BLOCKED/NOT_RUN.
"""
from __future__ import annotations

from .contract import CONTRACT_VERSION

__all__ = ["CONTRACT_VERSION"]
