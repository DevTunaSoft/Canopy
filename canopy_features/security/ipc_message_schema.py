"""Versioned, bounded validation of trusted Shell Host IPC message envelopes.

Pure offline validator: trusted host code calls this before dispatch. It opens
no socket, starts no service, polls nothing and executes no payload. Scalar
field rules are reused from :mod:`canopy_core.host_events`; this module adds
only the envelope shape, a sequence bound and a small target collection.

A valid envelope is a versioned dict with a host topic, a non-negative
sequence, a scalar payload and an optional bounded list of target ids. This is
not authentication, signature verification, sandboxing or proof of a working
desktop. No Qt or Linux Mint integration is claimed.
"""
from dataclasses import dataclass
from types import MappingProxyType
import re

from canopy_core.host_events import (
    HostEventError, PROTOCOL_VERSION, TOPICS, _encode_fields,
)

SCHEMA_VERSION = PROTOCOL_VERSION
MAX_SEQUENCE = 1_000_000_000
MAX_TARGETS = 8
TARGET = re.compile(r"[a-z][a-z0-9_.]{0,63}\Z")
MESSAGE_KEYS = frozenset({"version", "topic", "sequence", "payload", "targets"})
REQUIRED_KEYS = MESSAGE_KEYS - {"targets"}


class IpcSchemaError(ValueError):
    """Malformed, unsupported or oversized IPC message envelope."""


@dataclass(frozen=True)
class IpcMessage:
    """Immutable canonical form of an accepted envelope."""

    version: int
    topic: str
    sequence: int
    fields: tuple
    targets: tuple

    @property
    def payload(self):
        """Read-only mapping; callers cannot mutate the validated payload."""
        return MappingProxyType(dict(self.fields))


def _valid_targets(raw):
    if type(raw) not in (list, tuple):
        raise IpcSchemaError("IPC targets must be a list or tuple")
    if len(raw) > MAX_TARGETS:  # checked before iteration, so giants are cheap
        raise IpcSchemaError("IPC target collection exceeds bound")
    result = []
    for target in raw:
        if type(target) is not str or not TARGET.fullmatch(target):
            raise IpcSchemaError("unsupported IPC target id")
        result.append(target)
    return tuple(sorted(set(result)))


def validate_ipc_message(message):
    """Return an immutable IpcMessage or raise IpcSchemaError.

    The caller's dict is never mutated. No work is proportional to a giant
    payload or target collection: bounds are checked before traversal.
    """
    if type(message) is not dict or not MESSAGE_KEYS.issuperset(message):
        raise IpcSchemaError("unsupported IPC message envelope")
    if not REQUIRED_KEYS.issubset(message):
        raise IpcSchemaError("incomplete IPC message envelope")
    version = message["version"]
    if type(version) is not int or version != SCHEMA_VERSION:
        raise IpcSchemaError("unsupported IPC schema version")
    topic = message["topic"]
    if type(topic) is not str or topic not in TOPICS:
        raise IpcSchemaError("unsupported IPC topic")
    sequence = message["sequence"]
    if type(sequence) is not int or not 0 <= sequence <= MAX_SEQUENCE:
        raise IpcSchemaError("invalid IPC sequence number")
    try:
        fields = _encode_fields(message["payload"])
    except HostEventError as exc:
        raise IpcSchemaError("invalid or oversized IPC payload") from exc
    targets = _valid_targets(message["targets"]) if "targets" in message else ()
    return IpcMessage(version, topic, sequence, fields, targets)
