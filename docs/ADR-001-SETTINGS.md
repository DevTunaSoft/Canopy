# ADR-001: Shared settings and cosmetic performance resolver

Status: PROVISIONALLY ACCEPTED for prototype, pending Linux Mint integration tests.

Decision: Use Python standard-library dataclasses and enums for a small, explicit version-1 configuration schema, supporting Classic and future Modern with a single settings API. JSON persistence uses a same-directory temporary file, fsync and atomic replace, with restrictive file permissions. Invalid configuration is surfaced rather than silently overwritten.

Scope: Cosmetic features only (animations, transparency, dock magnification). Profile levels are prototype policy, not measured thresholds. Auto Mode currently accepts caller-provided battery/memory pressure flags; it does not monitor hardware. Reduced-motion accessibility takes precedence over cosmetic ON overrides.

Rationale: No extra runtime dependencies, no privileged daemon, deterministic behavior, easy testing. Future work: integrate into a Linux desktop UI, determine XDG config path, migration/backups, real metrics and compositor/toolkit decisions.

Security note: Caller must choose a trusted user-owned settings directory; no arbitrary privileged paths.
