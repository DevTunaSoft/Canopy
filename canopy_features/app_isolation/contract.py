"""Bounded value types and canonical documents for app-isolation requests.

Pure and offline: validates caller-supplied descriptions, projects them into
canonical JSON, computes digests and parses untrusted documents. It opens no
path, launches no process and grants no capability. The upstream surfaces and
the decision are in :mod:`canopy_features.app_isolation.upstream` and
:mod:`canopy_features.app_isolation.policy`.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

SCHEMA = 1
TOOL_NAME = "lacos_app_isolation"
TOOL_VERSION = "1.0.0"

MAX_LABEL_BYTES = 64
MAX_APP_ID_BYTES = 64
MAX_PATHLESS_TEXT_BYTES = 256
MAX_DOC_BYTES = 1024 * 1024
MAX_PERMISSIONS = 16
MAX_MECHANISMS = 8
MAX_REASONS = 32
MAX_STEPS = 32

ACCESS_READ_ONLY = "read_only"
ACCESS_EXPLICIT_WRITE = "explicit_write"
HOST_CONTEXT_HOST = "host"
HOST_CONTEXT_GUEST = "guest"
GUEST_SYNTHETIC = "SYNTHETIC"
GUEST_REAL_NOT_RUN = "REAL_GUEST_NOT_RUN"

DESCRIBE_ONLY = "DESCRIBE_ONLY"
REFUSE = "REFUSE"
BLOCKED = "BLOCKED"
NOT_RUN = "NOT_RUN"

_LABEL = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_APP_ID = re.compile(r"[a-z][a-z0-9_.-]{2,63}\Z")
_PERMISSION = re.compile(r"[a-z][a-z0-9_]{2,47}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")

ECOSYSTEMS = (
    "flatpak_flathub",
    "apt_deb",
    "pacman",
    "dnf_rpm",
    "rootless_podman_oci",
)

# Mirrors the five signed, upstream-only P0 ecosystems from the LacOS sources
# policy. These values are copied here as bounded plain data rather than
# imported: that sibling module is unmerged at this branch's base.
SOURCE_POLICY: Dict[str, Dict[str, frozenset]] = {
    "flatpak_flathub": {
        "provenance": frozenset(("official-flathub", "distribution-flatpak")),
        "signatures": frozenset(("gpg",)),
    },
    "apt_deb": {
        "provenance": frozenset(("ubuntu-archive", "debian-archive")),
        "signatures": frozenset(("apt-signed-by",)),
    },
    "pacman": {
        "provenance": frozenset(("arch-official",)),
        "signatures": frozenset(("pacman-key",)),
    },
    "dnf_rpm": {
        "provenance": frozenset(("fedora-official",)),
        "signatures": frozenset(("rpm-gpg",)),
    },
    "rootless_podman_oci": {
        "provenance": frozenset(("official-registry", "verified-image")),
        "signatures": frozenset(("cosign", "sigstore")),
    },
}

# Never grantable: no core mutation, no second sandbox/compositor/service, no
# paid tier, telemetry or mandatory account. Rootless OCI is not treated as a
# complete sandbox either.
FORBIDDEN_PERMISSIONS = frozenset((
    "core_mutation", "host_root", "privileged", "always_on", "telemetry",
    "paid_tier", "account_required", "duplicate_sandbox",
    "duplicate_compositor", "duplicate_service", "host_socket",
    "device_access", "unrestricted_network", "host_home_write",
))


class AppIsolationError(ValueError):
    """A bound, schema or type was violated; fail closed."""


class _DuplicateKey(ValueError):
    """Internal sentinel for a JSON object that repeats a key."""


def _pairs(pairs: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey("duplicate JSON key")
        result[key] = value
    return result


def canonical_bytes(document: Any) -> bytes:
    """Deterministic bounded UTF-8 JSON used for digests and evidence."""
    try:
        payload = json.dumps(document, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise AppIsolationError("document is not JSON serializable") from exc
    if len(payload) > MAX_DOC_BYTES:
        raise AppIsolationError("document exceeds canonical byte bound")
    return payload


def digest_bytes(payload: bytes) -> str:
    """SHA-256 of bounded bytes, lowercase hex."""
    if type(payload) is not bytes or len(payload) > MAX_DOC_BYTES:
        raise AppIsolationError("digest input must be bounded bytes")
    return hashlib.sha256(payload).hexdigest()


def parse_bounded_document(raw: bytes) -> Any:
    """Parse one bounded JSON document, rejecting hostile structures.

    Duplicate keys, non-finite constants, CPython's huge-integer ValueError,
    invalid UTF-8 and oversize bytes all raise :class:`AppIsolationError`.
    """
    if type(raw) is not bytes or not raw or len(raw) > MAX_DOC_BYTES:
        raise AppIsolationError("document bytes exceed their bound")
    try:
        return json.loads(
            raw.decode("utf-8"), object_pairs_hook=_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (_DuplicateKey, UnicodeError, ValueError, TypeError) as exc:
        raise AppIsolationError("document is not valid canonical JSON") from exc


def valid_label(value: Any) -> bool:
    """True only for an exact lowercase bounded ``str`` identifier."""
    return (type(value) is str
            and len(value.encode("utf-8")) <= MAX_LABEL_BYTES
            and _LABEL.fullmatch(value) is not None)


def valid_app_id(value: Any) -> bool:
    return (type(value) is str
            and len(value.encode("utf-8")) <= MAX_APP_ID_BYTES
            and _APP_ID.fullmatch(value) is not None)


def valid_permission(value: Any) -> bool:
    return (type(value) is str
            and len(value.encode("utf-8")) <= MAX_LABEL_BYTES
            and _PERMISSION.fullmatch(value) is not None)


def valid_digest(value: Any) -> bool:
    return type(value) is str and _DIGEST.fullmatch(value) is not None


def _bounded_text(value: Any) -> bool:
    return (type(value) is str
            and len(value.encode("utf-8")) <= MAX_PATHLESS_TEXT_BYTES)


_REASON = re.compile(r"[A-Z][A-Z0-9_]{1,63}\Z")


def bound_reasons(reasons: Any) -> Tuple[str, ...]:
    """Project at most MAX_REASONS distinct bounded reason codes in order."""
    if type(reasons) not in (tuple, list):
        raise AppIsolationError("reasons must be a finite tuple or list")
    result: list = []
    for reason in reasons:
        if type(reason) is not str or _REASON.fullmatch(reason) is None:
            raise AppIsolationError("reason code must be uppercase bounded")
        if reason not in result:
            result.append(reason)
        if len(result) == MAX_REASONS:
            break
    return tuple(result)


@dataclass(frozen=True)
class SourceClaim:
    """A caller's bounded provenance/signature claim, never a verification."""

    source_id: str
    provenance: str
    signature: str
    verified: bool
    scope: str

    def to_document(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "provenance": self.provenance,
            "signature": self.signature,
            "verified": self.verified,
            "scope": self.scope,
        }

    @classmethod
    def from_document(cls, document: Any) -> "SourceClaim":
        fields = {"source_id", "provenance", "signature", "verified", "scope"}
        if type(document) is not dict or set(document) != fields:
            raise AppIsolationError("source claim schema mismatch")
        if not valid_label(document["source_id"]):
            raise AppIsolationError("invalid source id")
        if (not valid_label(document["provenance"])
                or not valid_label(document["signature"])):
            raise AppIsolationError("invalid provenance or signature label")
        if type(document["verified"]) is not bool:
            raise AppIsolationError("verified must be an exact bool")
        if document["scope"] != "guest-only":
            raise AppIsolationError("source scope must be guest-only")
        return cls(document["source_id"], document["provenance"],
                   document["signature"], document["verified"],
                   document["scope"])


@dataclass(frozen=True)
class AppSpec:
    """One application's bounded, pathless isolation description."""

    app_id: str
    ecosystem: str
    access_mode: str
    permissions: Tuple[str, ...]

    def to_document(self) -> Dict[str, Any]:
        return {
            "app_id": self.app_id,
            "ecosystem": self.ecosystem,
            "access_mode": self.access_mode,
            "permissions": list(self.permissions),
        }

    @classmethod
    def from_document(cls, document: Any) -> "AppSpec":
        fields = {"app_id", "ecosystem", "access_mode", "permissions"}
        if type(document) is not dict or set(document) != fields:
            raise AppIsolationError("app spec schema mismatch")
        if not valid_app_id(document["app_id"]):
            raise AppIsolationError("invalid app id")
        if document["ecosystem"] not in SOURCE_POLICY:
            raise AppIsolationError("ecosystem is outside the P0 set")
        if document["access_mode"] not in (ACCESS_READ_ONLY,
                                           ACCESS_EXPLICIT_WRITE):
            raise AppIsolationError("invalid access mode")
        raw = document["permissions"]
        if type(raw) not in (list, tuple) or not 1 <= len(raw) <= MAX_PERMISSIONS:
            raise AppIsolationError("permission set is out of bounds")
        if any(not valid_permission(item) for item in raw):
            raise AppIsolationError("invalid permission label")
        if len(set(raw)) != len(raw):
            raise AppIsolationError("duplicate permission")
        return cls(document["app_id"], document["ecosystem"],
                   document["access_mode"], tuple(sorted(raw)))


@dataclass(frozen=True)
class HostFacts:
    """Synthetic facts supplied by a caller; no probe is run by this package."""

    signature_verified: bool
    source_verified: bool
    upstream_mechanism_available: bool
    no_duplicate_service: bool
    core_mutation_absent: bool
    isolation_enforced: bool

    def to_document(self) -> Dict[str, bool]:
        return {
            "signature_verified": self.signature_verified,
            "source_verified": self.source_verified,
            "upstream_mechanism_available": self.upstream_mechanism_available,
            "no_duplicate_service": self.no_duplicate_service,
            "core_mutation_absent": self.core_mutation_absent,
            "isolation_enforced": self.isolation_enforced,
        }

    @classmethod
    def from_document(cls, document: Any) -> "HostFacts":
        fields = frozenset((
            "signature_verified", "source_verified",
            "upstream_mechanism_available", "no_duplicate_service",
            "core_mutation_absent", "isolation_enforced"))
        if type(document) is not dict or set(document) != fields:
            raise AppIsolationError("host facts schema mismatch")
        if any(type(document[name]) is not bool for name in fields):
            raise AppIsolationError("host facts must be exact bools")
        return cls(
            document["signature_verified"], document["source_verified"],
            document["upstream_mechanism_available"],
            document["no_duplicate_service"], document["core_mutation_absent"],
            document["isolation_enforced"],
        )


@dataclass(frozen=True)
class IsolationRequest:
    """One bounded request to *describe*, never to run, an isolated app."""

    request_id: str
    app: AppSpec
    source: SourceClaim
    host_context: str
    facts: HostFacts
    guest_class: str
    deployment_id: str
    mechanisms: Tuple[str, ...]
    no_paid_tiers: bool
    no_telemetry: bool
    no_accounts: bool
    review_ack: bool

    def to_document(self) -> Dict[str, Any]:
        return {
            "schema": SCHEMA,
            "tool": TOOL_NAME,
            "tool_version": TOOL_VERSION,
            "request_id": self.request_id,
            "app": self.app.to_document(),
            "source": self.source.to_document(),
            "host_context": self.host_context,
            "facts": self.facts.to_document(),
            "guest_class": self.guest_class,
            "deployment_id": self.deployment_id,
            "mechanisms": list(self.mechanisms),
            "no_paid_tiers": self.no_paid_tiers,
            "no_telemetry": self.no_telemetry,
            "no_accounts": self.no_accounts,
            "review_ack": self.review_ack,
        }

    def digest(self) -> str:
        return digest_bytes(canonical_bytes(self.to_document()))

    @classmethod
    def from_document(cls, document: Any) -> "IsolationRequest":
        fields = {"schema", "tool", "tool_version", "request_id", "app",
                  "source", "host_context", "facts", "guest_class",
                  "deployment_id", "mechanisms", "no_paid_tiers",
                  "no_telemetry", "no_accounts", "review_ack"}
        if type(document) is not dict or set(document) != fields:
            raise AppIsolationError("request schema mismatch")
        if (type(document["schema"]) is not int
                or document["schema"] != SCHEMA
                or document["tool"] != TOOL_NAME
                or document["tool_version"] != TOOL_VERSION):
            raise AppIsolationError("unsupported request schema or tool version")
        if not valid_label(document["request_id"]) or not valid_label(
                document["deployment_id"]):
            raise AppIsolationError("invalid request or deployment label")
        if document["host_context"] not in (HOST_CONTEXT_HOST,
                                            HOST_CONTEXT_GUEST):
            raise AppIsolationError("invalid host context")
        if document["guest_class"] not in (GUEST_SYNTHETIC,
                                           GUEST_REAL_NOT_RUN):
            raise AppIsolationError("invalid guest class")
        mechanisms = document["mechanisms"]
        if (type(mechanisms) not in (list, tuple)
                or not 1 <= len(mechanisms) <= MAX_MECHANISMS
                or any(not valid_label(item) for item in mechanisms)
                or len(set(mechanisms)) != len(mechanisms)):
            raise AppIsolationError("invalid mechanism set")
        flags = ("no_paid_tiers", "no_telemetry", "no_accounts", "review_ack")
        if any(type(document[name]) is not bool for name in flags):
            raise AppIsolationError("request flags must be exact bools")
        if not _bounded_text(document["deployment_id"]):
            raise AppIsolationError("deployment label is not bounded text")
        return cls(
            document["request_id"],
            AppSpec.from_document(document["app"]),
            SourceClaim.from_document(document["source"]),
            document["host_context"],
            HostFacts.from_document(document["facts"]),
            document["guest_class"],
            document["deployment_id"],
            tuple(sorted(mechanisms)),
            *(document[name] for name in flags),
        )


def parse_request_document(raw: bytes) -> IsolationRequest:
    """Parse and validate one untrusted request document, fail closed."""
    return IsolationRequest.from_document(parse_bounded_document(raw))


@dataclass(frozen=True)
class IsolationDecision:
    """An inert decision: a description, or a refusal. Never a launch grant."""

    action: str
    steps: Tuple[str, ...]
    reasons: Tuple[str, ...]
    mechanisms: Tuple[str, ...]
    ecosystem: str
    request_digest: str

    @property
    def safe_to_describe(self) -> bool:
        """Derived from durable fields, not an overridable subclass flag."""
        return (self.action == DESCRIBE_ONLY and bool(self.steps)
                and len(self.steps) <= MAX_STEPS
                and all(step.startswith("UPSTREAM ")
                        or step.startswith("REVIEW_REQUIRED")
                        for step in self.steps)
                and self.steps[-1].startswith("REVIEW_REQUIRED")
                and not self.reasons)

    @property
    def launch_permitted(self) -> bool:
        # No launch is implemented or authorized by this package.
        return False

    def to_document(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "steps": list(self.steps),
            "reasons": list(self.reasons),
            "mechanisms": list(self.mechanisms),
            "ecosystem": self.ecosystem,
            "request_digest": self.request_digest,
            "safe_to_describe": self.safe_to_describe,
            "launch_permitted": self.launch_permitted,
            "guest_acceptance": NOT_RUN,
        }
