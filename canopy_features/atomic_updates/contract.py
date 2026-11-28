"""Bounded, read-only-first update transaction contract for LacOS / Kinoite.

Compatibility boundary (engineering mapping, not a Fedora claim): an immutable
base image, a content-addressed target commit, signature verification, a
retained previous deployment as rollback checkpoint, and activation only at
the host's reboot boundary are the properties this contract models. It does
not implement or invoke rpm-ostree, OSTree, D-Bus, package managers or a
bootloader.

Hard rules:

* All phases are read-only. Outputs are immutable *descriptions* for a
  trusted host adapter, never commands; ``HandoffStep.executed`` is always
  False.
* No core mutation is representable: a mutable-core observation, a layered
  core-mutation claim, or immediate activation fails closed with a stable
  reason.
* Only synthetic fixtures are accepted. Real-guest state is BLOCKED/NOT_RUN;
  no claim of a real update, boot, rollback or verification is made here.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from types import MappingProxyType
from typing import Optional

__all__ = [
    "AtomicUpdatesError",
    "CONTRACT_VERSION",
    "SCHEMA_VERSION",
    "SYNTHETIC_LABEL",
    "GUEST_BLOCKED",
    "GUEST_NOT_RUN",
    "GUEST_STATUS",
    "PHASES",
    "PHASE_PRECHECK",
    "PHASE_CHECKPOINT",
    "PHASE_PREPARE",
    "PHASE_VERIFY",
    "PHASE_HANDOFF",
    "PHASE_CONFIRM",
    "PHASE_ROLLBACK",
    "INTERFACES",
    "STATUSES",
    "STATUS_READY",
    "STATUS_BLOCKED",
    "STATUS_ROLLBACK",
    "SIGNATURE_STATES",
    "MAX_TEXT_LENGTH",
    "MAX_CANDIDATE_BYTES",
    "MAX_DEPLOYMENTS",
    "REASONS",
    "REASON_OK",
    "REASON_UNSIGNED",
    "REASON_DIGEST_MISMATCH",
    "REASON_CHECKPOINT_MISSING",
    "REASON_CHECKPOINT_DIGEST_MISMATCH",
    "REASON_CORE_MUTATION",
    "REASON_LAYERED_MUTATION",
    "REASON_UNBOUNDED",
    "REASON_ACTIVATION_NOT_DEFERRED",
    "REASON_NO_FALLBACK",
    "REASON_CONFIRM_FAILED",
    "REASON_SYNTHETIC_REQUIRED",
    "DeploymentObservation",
    "UpdateCandidate",
    "Checkpoint",
    "VerificationGates",
    "HandoffStep",
    "TransactionDecision",
    "plan_update",
    "plan_rollback",
]


class AtomicUpdatesError(ValueError):
    """Domain error for malformed, hostile or out-of-bounds contract input."""


CONTRACT_VERSION = "1"
SCHEMA_VERSION = "lacos-atomic-updates-fixture/1"
SYNTHETIC_LABEL = "SYNTHETIC"
GUEST_BLOCKED = "BLOCKED"
GUEST_NOT_RUN = "NOT_RUN"
GUEST_STATUS = "BLOCKED/NOT_RUN"

PHASE_PRECHECK = "precheck"
PHASE_CHECKPOINT = "checkpoint"
PHASE_PREPARE = "prepare"
PHASE_VERIFY = "verify"
PHASE_HANDOFF = "handoff"
PHASE_CONFIRM = "confirm"
PHASE_ROLLBACK = "rollback"
PHASES = (
    PHASE_PRECHECK,
    PHASE_CHECKPOINT,
    PHASE_PREPARE,
    PHASE_VERIFY,
    PHASE_HANDOFF,
    PHASE_CONFIRM,
    PHASE_ROLLBACK,
)

# Abstract handoff tokens only: no executable, method name, path, URL, shell
# fragment or D-Bus call is stored anywhere in this module.
INTERFACES = MappingProxyType(
    {
        "status": "rpm-ostree-status-readonly",
        "checkpoint": "deployment-checkpoint-readonly",
        "deploy": "rpm-ostree-deploy-handoff",
        "confirm": "post-reboot-status-readonly",
        "rollback": "rpm-ostree-rollback-handoff",
        "reboot": "reboot-required-handoff",
    }
)

STATUS_READY = "READY_FOR_HANDOFF"
STATUS_BLOCKED = "BLOCKED"
STATUS_ROLLBACK = "ROLLBACK_HANDOFF"
STATUSES = frozenset({STATUS_READY, STATUS_BLOCKED, STATUS_ROLLBACK})

SIGNATURE_STATES = frozenset({"VERIFIED", "UNVERIFIED", "MISSING"})
MAX_TEXT_LENGTH = 96
MAX_CANDIDATE_BYTES = 2 * 1024 * 1024 * 1024
MAX_DEPLOYMENTS = 8

REASON_OK = "ok"
REASON_UNSIGNED = "candidate-signature-not-verified"
REASON_DIGEST_MISMATCH = "staged-target-digest-mismatch"
REASON_CHECKPOINT_MISSING = "rollback-checkpoint-missing"
REASON_CHECKPOINT_DIGEST_MISMATCH = "checkpoint-digest-mismatch"
REASON_CORE_MUTATION = "core-mutation-forbidden"
REASON_LAYERED_MUTATION = "layered-core-mutation-forbidden"
REASON_UNBOUNDED = "input-out-of-bounds"
REASON_ACTIVATION_NOT_DEFERRED = "activation-not-deferred-to-reboot"
REASON_NO_FALLBACK = "stock-plasma-fallback-missing"
REASON_CONFIRM_FAILED = "post-reboot-confirmation-failed"
REASON_SYNTHETIC_REQUIRED = "synthetic-fixture-required"
REASONS = frozenset(
    {
        REASON_OK,
        REASON_UNSIGNED,
        REASON_DIGEST_MISMATCH,
        REASON_CHECKPOINT_MISSING,
        REASON_CHECKPOINT_DIGEST_MISMATCH,
        REASON_CORE_MUTATION,
        REASON_LAYERED_MUTATION,
        REASON_UNBOUNDED,
        REASON_ACTIVATION_NOT_DEFERRED,
        REASON_NO_FALLBACK,
        REASON_CONFIRM_FAILED,
        REASON_SYNTHETIC_REQUIRED,
    }
)

_DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
_TIMESTAMP_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
_UNSAFE_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})
_INTERFACE_VALUES = frozenset(INTERFACES.values())


def _text(value: object, field: str, limit: int = MAX_TEXT_LENGTH) -> str:
    if type(value) is not str:
        raise AtomicUpdatesError(f"{field}: expected str")
    if not value or len(value) > limit:
        raise AtomicUpdatesError(f"{field}: empty or over {limit} characters")
    if any(unicodedata.category(char) in _UNSAFE_CATEGORIES for char in value):
        raise AtomicUpdatesError(f"{field}: control or format character rejected")
    return value


def _digest(value: object, field: str) -> str:
    text = _text(value, field, 64)
    if not _DIGEST_RE.fullmatch(text):
        raise AtomicUpdatesError(f"{field}: expected 64 lowercase hex characters")
    return text


def _optional_digest(value: object, field: str) -> Optional[str]:
    if value is None:
        return None
    return _digest(value, field)


def _flag(value: object, field: str) -> bool:
    if type(value) is not bool:
        raise AtomicUpdatesError(f"{field}: expected bool")
    return value


def _bounded_int(value: object, field: str, low: int, high: int) -> int:
    if type(value) is not int:
        raise AtomicUpdatesError(f"{field}: expected int")
    if not low <= value <= high:
        raise AtomicUpdatesError(f"{field}: out of bounds")
    return value


def _timestamp(value: object, field: str) -> str:
    text = _text(value, field, 32)
    if not _TIMESTAMP_RE.fullmatch(text):
        raise AtomicUpdatesError(f"{field}: expected UTC ISO-8601 Z timestamp")
    return text


def _state(value: object, field: str, allowed: frozenset[str]) -> str:
    text = _text(value, field, 40)
    if text not in allowed:
        raise AtomicUpdatesError(f"{field}: unsupported token")
    return text


@dataclass(frozen=True)
class DeploymentObservation:
    """Bounded, trusted read-only view of one synthetic deployment."""

    deployment_id: str
    commit_digest: str
    staged_digest: Optional[str]
    version: str
    booted: bool
    signature_state: str
    core_writable: bool
    retained: bool
    observed_at: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "deployment_id", _text(self.deployment_id, "deployment_id", 48))
        object.__setattr__(self, "commit_digest", _digest(self.commit_digest, "commit_digest"))
        object.__setattr__(self, "staged_digest", _optional_digest(self.staged_digest, "staged_digest"))
        object.__setattr__(self, "version", _text(self.version, "version", 40))
        object.__setattr__(self, "booted", _flag(self.booted, "booted"))
        object.__setattr__(
            self, "signature_state", _state(self.signature_state, "signature_state", SIGNATURE_STATES)
        )
        object.__setattr__(self, "core_writable", _flag(self.core_writable, "core_writable"))
        object.__setattr__(self, "retained", _flag(self.retained, "retained"))
        object.__setattr__(self, "observed_at", _timestamp(self.observed_at, "observed_at"))


@dataclass(frozen=True)
class UpdateCandidate:
    """Synthetic image candidate; a digest and metadata, never a payload."""

    target_digest: str
    version: str
    signature_state: str
    origin: str
    size_bytes: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_digest", _digest(self.target_digest, "target_digest"))
        object.__setattr__(self, "version", _text(self.version, "version", 40))
        object.__setattr__(
            self, "signature_state", _state(self.signature_state, "signature_state", SIGNATURE_STATES)
        )
        object.__setattr__(self, "origin", _text(self.origin, "origin", 48))
        object.__setattr__(
            self,
            "size_bytes",
            _bounded_int(self.size_bytes, "size_bytes", 1, MAX_CANDIDATE_BYTES + 1),
        )


@dataclass(frozen=True)
class Checkpoint:
    """Description of the retained previous deployment used for rollback."""

    deployment_id: str
    commit_digest: str
    pinned: bool
    created_at: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "deployment_id", _text(self.deployment_id, "deployment_id", 48))
        object.__setattr__(self, "commit_digest", _digest(self.commit_digest, "commit_digest"))
        object.__setattr__(self, "pinned", _flag(self.pinned, "pinned"))
        object.__setattr__(self, "created_at", _timestamp(self.created_at, "created_at"))


@dataclass(frozen=True)
class VerificationGates:
    """Trusted read-only probe results; all must be true for a handoff."""

    signature_ok: bool
    digest_match: bool
    checkpoint_retained: bool
    core_immutable: bool
    no_layered_mutation: bool
    within_bounds: bool
    activation_deferred: bool
    stock_plasma_fallback: bool

    def __post_init__(self) -> None:
        for name in (
            "signature_ok",
            "digest_match",
            "checkpoint_retained",
            "core_immutable",
            "no_layered_mutation",
            "within_bounds",
            "activation_deferred",
            "stock_plasma_fallback",
        ):
            object.__setattr__(self, name, _flag(getattr(self, name), name))


@dataclass(frozen=True)
class HandoffStep:
    """An inert description for a trusted adapter, never an executed action."""

    phase: str
    interface: str
    detail: str
    requires_reboot: bool = False
    executed: bool = False

    def __post_init__(self) -> None:
        if self.phase not in PHASES:
            raise AtomicUpdatesError("phase: unsupported token")
        if self.interface not in _INTERFACE_VALUES:
            raise AtomicUpdatesError("interface: unsupported abstract token")
        object.__setattr__(self, "detail", _text(self.detail, "detail", 120))
        object.__setattr__(self, "requires_reboot", _flag(self.requires_reboot, "requires_reboot"))
        if _flag(self.executed, "executed"):
            raise AtomicUpdatesError("executed: contract never executes a step")
        object.__setattr__(self, "executed", False)


@dataclass(frozen=True)
class TransactionDecision:
    """Immutable outcome: reason codes plus inert handoff descriptions."""

    phase: str
    status: str
    reasons: tuple[str, ...]
    steps: tuple[HandoffStep, ...]
    contract_version: str = CONTRACT_VERSION
    synthetic_label: str = SYNTHETIC_LABEL
    guest_status: str = GUEST_NOT_RUN

    def __post_init__(self) -> None:
        if self.phase not in PHASES:
            raise AtomicUpdatesError("phase: unsupported token")
        if self.status not in STATUSES:
            raise AtomicUpdatesError("status: unsupported token")
        if type(self.reasons) not in (tuple, list):
            raise AtomicUpdatesError("reasons: expected sequence")
        reasons = tuple(self.reasons)
        if len(reasons) > len(REASONS) or any(reason not in REASONS for reason in reasons):
            raise AtomicUpdatesError("reasons: unsupported token")
        if type(self.steps) not in (tuple, list):
            raise AtomicUpdatesError("steps: expected sequence")
        steps = tuple(self.steps)
        if len(steps) > MAX_DEPLOYMENTS or any(type(step) is not HandoffStep for step in steps):
            raise AtomicUpdatesError("steps: invalid handoff description")
        object.__setattr__(self, "reasons", reasons)
        object.__setattr__(self, "steps", steps)
        if self.contract_version != CONTRACT_VERSION:
            raise AtomicUpdatesError("contract_version: unsupported version")
        if self.synthetic_label != SYNTHETIC_LABEL:
            raise AtomicUpdatesError(REASON_SYNTHETIC_REQUIRED)
        if self.guest_status not in (GUEST_BLOCKED, GUEST_NOT_RUN):
            raise AtomicUpdatesError("guest_status: real-guest result not representable")


def _gate_failures(
    observation: DeploymentObservation,
    candidate: UpdateCandidate,
    checkpoint: Checkpoint,
    gates: VerificationGates,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if candidate.signature_state != "VERIFIED" or not gates.signature_ok:
        reasons.append(REASON_UNSIGNED)
    if observation.staged_digest != candidate.target_digest or not gates.digest_match:
        reasons.append(REASON_DIGEST_MISMATCH)
    if not checkpoint.pinned or not gates.checkpoint_retained or not observation.retained:
        reasons.append(REASON_CHECKPOINT_MISSING)
    if checkpoint.commit_digest != observation.commit_digest:
        reasons.append(REASON_CHECKPOINT_DIGEST_MISMATCH)
    if observation.core_writable or not gates.core_immutable:
        reasons.append(REASON_CORE_MUTATION)
    if not gates.no_layered_mutation:
        reasons.append(REASON_LAYERED_MUTATION)
    if candidate.size_bytes > MAX_CANDIDATE_BYTES or not gates.within_bounds:
        reasons.append(REASON_UNBOUNDED)
    if not gates.activation_deferred:
        reasons.append(REASON_ACTIVATION_NOT_DEFERRED)
    if not gates.stock_plasma_fallback:
        reasons.append(REASON_NO_FALLBACK)
    return tuple(dict.fromkeys(reasons))


def _require_records(
    observation: object,
    candidate: object,
    checkpoint: object,
    gates: object,
) -> None:
    for name, value, expected in (
        ("observation", observation, DeploymentObservation),
        ("candidate", candidate, UpdateCandidate),
        ("checkpoint", checkpoint, Checkpoint),
        ("gates", gates, VerificationGates),
    ):
        if type(value) is not expected:
            raise AtomicUpdatesError(f"{name}: expected {expected.__name__}")


def plan_update(
    observation: DeploymentObservation,
    candidate: UpdateCandidate,
    checkpoint: Checkpoint,
    gates: VerificationGates,
    *,
    confirm_ok: bool,
) -> TransactionDecision:
    """Evaluate a synthetic update transaction without executing anything.

    A failed gate yields BLOCKED with stable reasons and zero handoff steps.
    A failed post-reboot confirmation yields a rollback *description* after
    all preconditions pass. Only a fully gated, confirmed plan is
    READY_FOR_HANDOFF, and even then every step remains unexecuted.
    """
    _require_records(observation, candidate, checkpoint, gates)
    confirm_ok = _flag(confirm_ok, "confirm_ok")

    failures = _gate_failures(observation, candidate, checkpoint, gates)
    if failures:
        return TransactionDecision(
            phase=PHASE_VERIFY,
            status=STATUS_BLOCKED,
            reasons=failures,
            steps=(),
        )

    if not confirm_ok:
        return plan_rollback(observation, checkpoint)

    steps = (
        HandoffStep(
            PHASE_PRECHECK,
            INTERFACES["status"],
            "read-only deployment snapshot; no host mutation",
        ),
        HandoffStep(
            PHASE_CHECKPOINT,
            INTERFACES["checkpoint"],
            "previous deployment already retained; no pin or write performed",
        ),
        HandoffStep(
            PHASE_PREPARE,
            INTERFACES["status"],
            "synthetic staged digest observed; immutable core unchanged",
        ),
        HandoffStep(
            PHASE_VERIFY,
            INTERFACES["status"],
            "signature, digest, checkpoint and fallback gates satisfied",
        ),
        HandoffStep(
            PHASE_HANDOFF,
            INTERFACES["deploy"],
            "description only for a trusted adapter; not executed here",
            requires_reboot=True,
        ),
        HandoffStep(
            PHASE_CONFIRM,
            INTERFACES["confirm"],
            "read-only post-reboot confirmation; rollback if confirmation fails",
            requires_reboot=True,
        ),
    )
    return TransactionDecision(
        phase=PHASE_HANDOFF,
        status=STATUS_READY,
        reasons=(REASON_OK,),
        steps=steps,
    )


def plan_rollback(
    observation: DeploymentObservation,
    checkpoint: Checkpoint,
) -> TransactionDecision:
    """Describe a rollback handoff to the retained deployment; never execute."""
    if type(observation) is not DeploymentObservation:
        raise AtomicUpdatesError("observation: expected DeploymentObservation")
    if type(checkpoint) is not Checkpoint:
        raise AtomicUpdatesError("checkpoint: expected Checkpoint")
    reasons: tuple[str, ...] = ()
    if not checkpoint.pinned:
        reasons = (REASON_CHECKPOINT_MISSING,)
    elif checkpoint.commit_digest != observation.commit_digest:
        reasons = (REASON_CHECKPOINT_DIGEST_MISMATCH,)
    if reasons:
        return TransactionDecision(
            phase=PHASE_ROLLBACK,
            status=STATUS_BLOCKED,
            reasons=reasons,
            steps=(),
        )
    step = HandoffStep(
        PHASE_ROLLBACK,
        INTERFACES["rollback"],
        "description only: select retained checkpoint at the reboot boundary",
        requires_reboot=True,
    )
    return TransactionDecision(
        phase=PHASE_ROLLBACK,
        status=STATUS_ROLLBACK,
        reasons=(REASON_CONFIRM_FAILED,),
        steps=(step,),
    )
