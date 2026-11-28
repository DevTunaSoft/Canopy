"""Immutable, bounded recovery records for native suspend/resume.

This is a *contract* layer. It consumes only facts already collected by a
trusted host boundary and returns immutable, read-only verdicts. It never
suspends, resumes, locks, unlocks, starts a service, opens D-Bus, reads a
file, spawns a process, sleeps, polls or emits an event.

Existing contracts are reused, never redefined:

* ``canopy_features.reliability.suspend_resume_contracts`` supplies the
  evidence-label and outcome vocabularies and the fail-closed phase model;
* ``canopy_features.quick_controls.host_status_producer.TRUSTED_SOURCES``
  supplies the only accepted capture sources;
* ``canopy_core.host_events.HostEventError`` is the parent domain error.

No protocol version, topic, payload field or daemon is added.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from canopy_core.host_events import HostEventError
from canopy_features.quick_controls.host_status_producer import TRUSTED_SOURCES

__all__ = [
    "EVIDENCE_LABELS", "OUTCOMES", "SOURCES", "INTERFACES", "STAGES",
    "FACT_ORDER", "FACTS", "CHECKPOINTS", "CHECKPOINT_SET",
    "CHECKPOINT_STATES", "FALLBACK_REASONS", "VERDICT_REASONS",
    "NATIVE_RUNTIME", "SYNTHETIC", "STATIC_SOURCE_ONLY", "CI_SCOPED",
    "SESSION_RECOVERY_ERROR_SENTINEL", "SessionRecoveryError",
    "StateCapture", "Preservation", "Checkpoint", "Fallback",
    "Verdict", "RecoverySnapshot",
]

# Rev3 section 11 vocabulary. The base integration branch does not yet carry
# these constants in the protected reliability module, and that path is owned
# by a sibling change; this module mirrors the directive vocabulary locally
# and never mutates the shared contract.
EVIDENCE_LABELS = frozenset(
    {"STATIC SOURCE ONLY", "SYNTHETIC", "CI-SCOPED", "NATIVE RUNTIME"})
OUTCOMES = frozenset({"PASS", "FAIL", "BLOCKED", "NOT RUN"})

NATIVE_RUNTIME = "NATIVE RUNTIME"
SYNTHETIC = "SYNTHETIC"
STATIC_SOURCE_ONLY = "STATIC SOURCE ONLY"
CI_SCOPED = "CI-SCOPED"

# The only trusted capture sources are the existing host-status sources. The
# interface names describe which *already-existing* read-only system tool
# produced the text; they are provenance, not new services.
SOURCES = frozenset(TRUSTED_SOURCES)
INTERFACES = frozenset({"logind", "upower", "plasma", "host-events"})

STAGES = ("pre", "suspend", "resume", "post")
FACT_ORDER = (
    "shell_active", "dock_visible", "launcher_visible", "window_visible",
    "session_present", "workspace_stable",
)
FACTS = frozenset(FACT_ORDER)

PRE_CAPTURED = "pre-state-captured"
SESSION_PRESERVED = "session-preserved"
WORK_PRESERVED = "work-preserved"
SUSPEND_CONFIRMED = "suspend-confirmed"
RESUME_CONFIRMED = "resume-confirmed"
POST_CAPTURED = "post-state-captured"
DESKTOP_REOBSERVED = "desktop-reobserved"
FALLBACK_READY = "fallback-ready"
CHECKPOINTS = (
    PRE_CAPTURED, SESSION_PRESERVED, WORK_PRESERVED, SUSPEND_CONFIRMED,
    RESUME_CONFIRMED, POST_CAPTURED, DESKTOP_REOBSERVED, FALLBACK_READY,
)
CHECKPOINT_SET = frozenset(CHECKPOINTS)
MAX_CHECKPOINTS = len(CHECKPOINTS)

OBSERVED = "observed"
MISSING = "missing"
NOT_RUN = "not-run"
FALLBACK = "fallback"
CHECKPOINT_STATES = frozenset({OBSERVED, MISSING, NOT_RUN, FALLBACK})

FALLBACK_REASONS = frozenset({
    "host-unavailable", "capture-incomplete", "preservation-unconfirmed",
    "resume-unobserved", "native-evidence-absent", "path-closed",
})
VERDICT_REASONS = frozenset({
    "native-evidence-absent", "suspend-not-observed", "resume-not-observed",
    "desktop-not-reobserved", "pre-post-state-missing",
    "pre-post-facts-incomplete", "desktop-state-not-restored",
    "preservation-incomplete", "session-or-work-not-preserved",
    "native-suspend-resume-recovery-verified",
})

# Stable marker used by static scans to find the fail-closed contract without
# reading prose. It is data only; no runtime action is attached to it.
SESSION_RECOVERY_ERROR_SENTINEL = "session-recovery-contract-error"


class SessionRecoveryError(HostEventError):
    """Invalid caller input or misuse of the read-only recovery contract."""


def _check_label(label):
    if type(label) is not str or label not in EVIDENCE_LABELS:
        raise SessionRecoveryError("invalid evidence label")


def _check_source(source):
    if type(source) is not str or source not in SOURCES:
        raise SessionRecoveryError("capture source is not trusted")


def _check_interface(interface):
    if type(interface) is not str or interface not in INTERFACES:
        raise SessionRecoveryError("unsupported read-only interface")


def _check_optional_bool(value):
    if value is not None and type(value) is not bool:
        raise SessionRecoveryError("fact must be boolean or null")


def _canonical_facts(record, allowed):
    if isinstance(record, (str, bytes, bytearray)) or not isinstance(record, Mapping):
        raise SessionRecoveryError("facts must be a mapping")
    if frozenset(record) != allowed:
        raise SessionRecoveryError("unexpected fact set")
    ordered = {key: record[key] for key in FACT_ORDER if key in allowed}
    for value in ordered.values():
        _check_optional_bool(value)
    return MappingProxyType(ordered)


@dataclass(frozen=True)
class StateCapture:
    """One bounded, caller-supplied pre/post desktop state observation.

    ``None`` means *not observed*, never *observed absent*. Only an explicit
    ``True`` can contribute to a recovery verdict.
    """

    stage: str
    source: str
    interface: str
    facts: Mapping

    def __post_init__(self):
        if type(self.stage) is not str or self.stage not in STAGES:
            raise SessionRecoveryError("invalid capture stage")
        _check_source(self.source)
        _check_interface(self.interface)
        object.__setattr__(self, "facts", _canonical_facts(self.facts, FACTS))

    @property
    def missing(self):
        return tuple(key for key in FACT_ORDER if self.facts[key] is None)

    @property
    def complete(self):
        return all(self.facts[key] is not None for key in FACT_ORDER)

    @property
    def confirmed(self):
        return all(self.facts[key] is True for key in FACT_ORDER)

    def to_dict(self):
        return {
            "stage": self.stage,
            "source": self.source,
            "interface": self.interface,
            "facts": dict(self.facts),
            "missing": self.missing,
        }


@dataclass(frozen=True)
class Preservation:
    """Whether the existing session and its work survived the cycle."""

    session_id_stable: object
    work_area_stable: object
    windows_restored: object
    source: str

    def __post_init__(self):
        for name in ("session_id_stable", "work_area_stable", "windows_restored"):
            _check_optional_bool(getattr(self, name))
        _check_source(self.source)

    @property
    def missing(self):
        return tuple(name for name in (
            "session_id_stable", "work_area_stable", "windows_restored")
            if getattr(self, name) is None)

    @property
    def complete(self):
        return not self.missing

    @property
    def confirmed(self):
        return (self.session_id_stable is True and self.work_area_stable is True
                and self.windows_restored is True)

    def to_dict(self):
        return {
            "session_id_stable": self.session_id_stable,
            "work_area_stable": self.work_area_stable,
            "windows_restored": self.windows_restored,
            "source": self.source,
            "missing": self.missing,
        }


@dataclass(frozen=True)
class Checkpoint:
    """One named recovery checkpoint; it records facts and performs nothing."""

    name: str
    state: str
    evidence_label: str = STATIC_SOURCE_ONLY

    def __post_init__(self):
        if type(self.name) is not str or self.name not in CHECKPOINT_SET:
            raise SessionRecoveryError("unknown recovery checkpoint")
        if type(self.state) is not str or self.state not in CHECKPOINT_STATES:
            raise SessionRecoveryError("invalid checkpoint state")
        _check_label(self.evidence_label)

    def to_dict(self):
        return {"name": self.name, "state": self.state,
                "evidence_label": self.evidence_label}


@dataclass(frozen=True)
class Fallback:
    """Honest safe fallback declaration: stock Plasma, no action performed."""

    reason: str
    target: str = "stock-plasma"
    action: str = "none"
    executed: bool = False

    def __post_init__(self):
        if type(self.reason) is not str or self.reason not in FALLBACK_REASONS:
            raise SessionRecoveryError("invalid fallback reason")
        if self.target != "stock-plasma" or self.action != "none":
            raise SessionRecoveryError("fallback may not name an action")
        if self.executed is not False:
            raise SessionRecoveryError("fallback is declaration only")

    def to_dict(self):
        return {"reason": self.reason, "target": self.target,
                "action": self.action, "executed": self.executed}


@dataclass(frozen=True)
class Verdict:
    """Fail-closed M4 conclusion for one complete observation set."""

    outcome: str
    reason: str
    evidence_label: str

    def __post_init__(self):
        if type(self.outcome) is not str or self.outcome not in OUTCOMES:
            raise SessionRecoveryError("invalid verdict outcome")
        if type(self.reason) is not str or self.reason not in VERDICT_REASONS:
            raise SessionRecoveryError("invalid verdict reason")
        _check_label(self.evidence_label)
        if self.outcome == "PASS" and self.evidence_label != NATIVE_RUNTIME:
            raise SessionRecoveryError("non-native evidence cannot earn PASS")

    def to_dict(self):
        return {"outcome": self.outcome, "reason": self.reason,
                "evidence_label": self.evidence_label}


@dataclass(frozen=True)
class RecoverySnapshot:
    """Bounded, immutable projection of one suspend/resume recovery cycle."""

    evidence_label: str = STATIC_SOURCE_ONLY
    pre: StateCapture | None = None
    post: StateCapture | None = None
    suspend: Checkpoint | None = None
    resume: Checkpoint | None = None
    preservation: Preservation | None = None
    reobserved: object = None
    checkpoints: tuple = ()
    fallback: Fallback | None = None

    def __post_init__(self):
        _check_label(self.evidence_label)
        for name, expected in (("pre", StateCapture), ("post", StateCapture),
                               ("suspend", Checkpoint), ("resume", Checkpoint),
                               ("preservation", Preservation),
                               ("fallback", Fallback)):
            value = getattr(self, name)
            if value is not None and type(value) is not expected:
                raise SessionRecoveryError("invalid recovery snapshot field")
        _check_optional_bool(self.reobserved)
        if type(self.checkpoints) is not tuple or len(self.checkpoints) > MAX_CHECKPOINTS:
            raise SessionRecoveryError("checkpoint history exceeds its bound")
        for checkpoint in self.checkpoints:
            if type(checkpoint) is not Checkpoint:
                raise SessionRecoveryError("invalid checkpoint record")

    def verdict(self):
        """Derive the conclusion from durable facts only; never execute."""
        deny = lambda outcome, reason: Verdict(outcome, reason, self.evidence_label)
        if self.evidence_label != NATIVE_RUNTIME:
            return deny("BLOCKED", "native-evidence-absent")
        if self.suspend is None or self.suspend.state != OBSERVED:
            return deny("NOT RUN", "suspend-not-observed")
        if self.resume is None or self.resume.state != OBSERVED:
            return deny("NOT RUN", "resume-not-observed")
        if self.reobserved is not True:
            return deny("NOT RUN", "desktop-not-reobserved")
        if self.pre is None or self.post is None:
            return deny("NOT RUN", "pre-post-state-missing")
        if not self.pre.complete or not self.post.complete:
            return deny("NOT RUN", "pre-post-facts-incomplete")
        if not self.pre.confirmed or not self.post.confirmed:
            return deny("FAIL", "desktop-state-not-restored")
        if self.preservation is None or not self.preservation.complete:
            return deny("NOT RUN", "preservation-incomplete")
        if not self.preservation.confirmed:
            return deny("FAIL", "session-or-work-not-preserved")
        observed = {item.name for item in self.checkpoints
                    if item.state == OBSERVED}
        required = CHECKPOINT_SET - {FALLBACK_READY}
        if not required <= observed:
            return deny("NOT RUN", "pre-post-facts-incomplete")
        return deny("PASS", "native-suspend-resume-recovery-verified")

    def view(self):
        return MappingProxyType({
            "evidence_label": self.evidence_label,
            "pre": self.pre.to_dict() if self.pre is not None else None,
            "post": self.post.to_dict() if self.post is not None else None,
            "suspend": self.suspend.to_dict() if self.suspend is not None else None,
            "resume": self.resume.to_dict() if self.resume is not None else None,
            "preservation": (self.preservation.to_dict()
                             if self.preservation is not None else None),
            "reobserved": self.reobserved,
            "checkpoints": tuple(item.to_dict() for item in self.checkpoints),
            "fallback": self.fallback.to_dict() if self.fallback is not None else None,
            "verdict": self.verdict().to_dict(),
        })

    def to_dict(self):
        snapshot = self.view()
        return {
            "evidence_label": snapshot["evidence_label"],
            "pre": snapshot["pre"],
            "post": snapshot["post"],
            "suspend": snapshot["suspend"],
            "resume": snapshot["resume"],
            "preservation": snapshot["preservation"],
            "reobserved": snapshot["reobserved"],
            "checkpoints": list(snapshot["checkpoints"]),
            "fallback": snapshot["fallback"],
            "verdict": snapshot["verdict"],
        }
