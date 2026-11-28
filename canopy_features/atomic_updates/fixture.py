"""Strict parser for synthetic-only atomic-update fixtures.

Pure text in, immutable records out: no file, process, socket, environment or
host I/O. Duplicate JSON keys, unknown keys, hostile key names and real-guest
claims are rejected with :class:`AtomicUpdatesError` before any transaction
decision is made.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, TypeVar

from .contract import (
    AtomicUpdatesError,
    Checkpoint,
    DeploymentObservation,
    GUEST_BLOCKED,
    GUEST_NOT_RUN,
    SCHEMA_VERSION,
    STATUSES,
    SYNTHETIC_LABEL,
    TransactionDecision,
    UpdateCandidate,
    VerificationGates,
    _text,
    plan_update,
)

__all__ = ["Fixture", "parse_fixture", "evaluate_fixture"]

_ROOT_KEYS = frozenset(
    {
        "schema",
        "name",
        "label",
        "guest_status",
        "expect",
        "observation",
        "candidate",
        "checkpoint",
        "gates",
        "confirm_ok",
    }
)
_OBSERVATION_KEYS = frozenset(
    {
        "deployment_id",
        "commit_digest",
        "staged_digest",
        "version",
        "booted",
        "signature_state",
        "core_writable",
        "retained",
        "observed_at",
    }
)
_CANDIDATE_KEYS = frozenset(
    {"target_digest", "version", "signature_state", "origin", "size_bytes"}
)
_CHECKPOINT_KEYS = frozenset({"deployment_id", "commit_digest", "pinned", "created_at"})
_GATES_KEYS = frozenset(
    {
        "signature_ok",
        "digest_match",
        "checkpoint_retained",
        "core_immutable",
        "no_layered_mutation",
        "within_bounds",
        "activation_deferred",
        "stock_plasma_fallback",
    }
)

# A fixture describes observations and decisions. Command/payload-shaped input
# is never accepted, even inside an otherwise valid-looking fixture.
_FORBIDDEN_KEY_TOKENS = (
    "command",
    "argv",
    "shell",
    "credential",
    "password",
    "secret",
    "token",
    "url",
    "endpoint",
    "path",
    "payload",
)

_T = TypeVar("_T")


@dataclass(frozen=True)
class Fixture:
    """Synthetic input bundle with its expected decision status."""

    name: str
    label: str
    guest_status: str
    expect: str
    observation: DeploymentObservation
    candidate: UpdateCandidate
    checkpoint: Checkpoint
    gates: VerificationGates
    confirm_ok: bool

    def __post_init__(self) -> None:
        if self.label != SYNTHETIC_LABEL:
            raise AtomicUpdatesError("label: synthetic fixture required")
        if self.guest_status not in (GUEST_BLOCKED, GUEST_NOT_RUN):
            raise AtomicUpdatesError("guest_status: real-guest result not representable")
        if self.expect not in STATUSES:
            raise AtomicUpdatesError("expect: unsupported decision status")
        if type(self.confirm_ok) is not bool:
            raise AtomicUpdatesError("confirm_ok: expected bool")
        for name, expected in (
            ("observation", DeploymentObservation),
            ("candidate", UpdateCandidate),
            ("checkpoint", Checkpoint),
            ("gates", VerificationGates),
        ):
            if type(getattr(self, name)) is not expected:
                raise AtomicUpdatesError(f"{name}: expected {expected.__name__}")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise AtomicUpdatesError("duplicate fixture key rejected")
        result[key] = value
    return result


def _mapping(value: object, field: str) -> dict[str, object]:
    if type(value) is not dict:
        raise AtomicUpdatesError(f"{field}: expected object")
    return value


def _exact_keys(mapping: dict[str, object], expected: frozenset[str], field: str) -> None:
    actual = frozenset(mapping)
    missing = expected - actual
    extra = actual - expected
    if missing or extra:
        raise AtomicUpdatesError(f"{field}: key set mismatch")
    for key in actual:
        lowered = key.casefold()
        if any(bad in lowered for bad in _FORBIDDEN_KEY_TOKENS):
            raise AtomicUpdatesError(f"{field}: command-shaped key rejected")


def _record(
    mapping: dict[str, object],
    expected: frozenset[str],
    field: str,
    factory: Callable[..., _T],
) -> _T:
    section = _mapping(mapping[field], field)
    _exact_keys(section, expected, field)
    try:
        return factory(**section)
    except AtomicUpdatesError:
        raise
    except (TypeError, ValueError) as exc:
        raise AtomicUpdatesError(f"{field}: invalid record") from exc


def parse_fixture(text: object) -> Fixture:
    """Parse and validate one synthetic fixture from a JSON string."""
    if type(text) is not str:
        raise AtomicUpdatesError("fixture: expected JSON text")
    try:
        data = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except AtomicUpdatesError:
        raise
    except (ValueError, TypeError, RecursionError) as exc:
        # CPython's integer-digit limit raises plain ValueError, not
        # JSONDecodeError; both must become the domain error.
        raise AtomicUpdatesError("fixture: invalid JSON") from exc
    root = _mapping(data, "fixture")
    _exact_keys(root, _ROOT_KEYS, "fixture")
    if root["schema"] != SCHEMA_VERSION:
        raise AtomicUpdatesError("schema: unsupported fixture schema")
    if root["label"] != SYNTHETIC_LABEL:
        raise AtomicUpdatesError("label: synthetic fixture required")
    if root["guest_status"] not in (GUEST_BLOCKED, GUEST_NOT_RUN):
        raise AtomicUpdatesError("guest_status: real-guest result not representable")
    if root["expect"] not in STATUSES:
        raise AtomicUpdatesError("expect: unsupported decision status")

    observation = _record(root, _OBSERVATION_KEYS, "observation", DeploymentObservation)
    candidate = _record(root, _CANDIDATE_KEYS, "candidate", UpdateCandidate)
    checkpoint = _record(root, _CHECKPOINT_KEYS, "checkpoint", Checkpoint)
    gates = _record(root, _GATES_KEYS, "gates", VerificationGates)
    return Fixture(
        name=_text(root["name"], "name", 64),
        label=str(root["label"]),
        guest_status=str(root["guest_status"]),
        expect=str(root["expect"]),
        observation=observation,
        candidate=candidate,
        checkpoint=checkpoint,
        gates=gates,
        confirm_ok=root["confirm_ok"],  # type: ignore[arg-type]
    )


def evaluate_fixture(fixture: Fixture) -> TransactionDecision:
    """Run one validated synthetic fixture through the transaction contract."""
    if type(fixture) is not Fixture:
        raise AtomicUpdatesError("fixture: expected Fixture")
    return plan_update(
        fixture.observation,
        fixture.candidate,
        fixture.checkpoint,
        fixture.gates,
        confirm_ok=fixture.confirm_ok,
    )
