"""Non-executing integrity contracts for optional Canopy extensions.

This module is pure data validation. It NEVER imports, loads, evaluates or
executes extension code, and it NEVER opens files, sockets, subprocesses or
network connections. Callers supply artifact bytes and a signer identity that
trusted host code has already obtained; this module only decides whether those
observations match a host-authored, pinned contract.

Trust model:
- A contract is authored by trusted host code via :func:`pin`; an extension
  cannot grant itself trust.
- The signer identity must be in the host's explicit :class:`TrustPolicy`
  allowlist, and must equal the signer pinned in the contract.
- The observed bytes must match the pinned SHA-256 digest (constant-time
  comparison).

Limits, honestly stated:
- Signer identity is an asserted label, NOT a cryptographic signature. Real
  signature verification, provenance review, sandboxing and capability
  enforcement belong to the future Qt Shell Host and are not done here.
- Passing this check is NOT permission to load or run an extension. It only
  says pinned signer and bytes matched a host-approved contract.
"""

from dataclasses import dataclass
from enum import Enum
import hashlib
import hmac
import re
from typing import FrozenSet

CONTRACT_VERSION = 1
MAX_SIGNER_ID_BYTES = 128
MAX_EXTENSION_ID_BYTES = 128
MAX_ARTIFACT_BYTES = 4 * 1024 * 1024

EXTENSION_ID = re.compile(r"[a-z][a-z0-9]*(?:\.[a-z][a-z0-9-]*){2,}", re.ASCII)
SIGNER_ID = re.compile(r"[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*", re.ASCII)
SHA256_HEX = re.compile(r"[0-9a-f]{64}", re.ASCII)


class ContractError(ValueError):
    """A host-authored contract or its inputs are malformed or out of bounds."""


class Decision(Enum):
    """Fail-closed verification outcomes. Only ACCEPTED grants anything."""

    ACCEPTED = "accepted"
    UNKNOWN_SIGNER = "unknown-signer"
    SIGNER_MISMATCH = "signer-mismatch"
    DIGEST_MISMATCH = "digest-mismatch"
    UNSUPPORTED_VERSION = "unsupported-version"
    MALFORMED_CONTRACT = "malformed-contract"
    INVALID_OBSERVATION = "invalid-observation"
    OVERSIZED_ARTIFACT = "oversized-artifact"


@dataclass(frozen=True)
class Verification:
    """Immutable decision. No free text, so no secret can leak through it."""

    decision: Decision

    @property
    def accepted(self):
        return self.decision is Decision.ACCEPTED


def _validate_signer(value, name):
    if (type(value) is not str or not value
            or len(value.encode("utf-8")) > MAX_SIGNER_ID_BYTES
            or not SIGNER_ID.fullmatch(value)):
        raise ContractError(f"{name} must be a clean lowercase signer identity")


@dataclass(frozen=True)
class IntegrityContract:
    """Pinned identity, signer and digest for one optional extension.

    This is inert data. Constructing or holding a contract never reads or runs
    the extension it describes.
    """

    extension_id: str
    signer_id: str
    sha256: str
    version: int = CONTRACT_VERSION

    def __post_init__(self):
        if (type(self.extension_id) is not str
                or len(self.extension_id.encode("utf-8")) > MAX_EXTENSION_ID_BYTES
                or not EXTENSION_ID.fullmatch(self.extension_id)):
            raise ContractError("extension_id must be a reverse-DNS lowercase name")
        _validate_signer(self.signer_id, "signer_id")
        if (type(self.sha256) is not str
                or not SHA256_HEX.fullmatch(self.sha256)):
            raise ContractError("sha256 must be 64 lowercase hex characters")
        if type(self.version) is not int or self.version != CONTRACT_VERSION:
            raise ContractError("unsupported contract version")


@dataclass(frozen=True)
class TrustPolicy:
    """Host-owned signer allowlist. Extensions cannot add entries to it."""

    trusted_signers: FrozenSet[str]

    def __post_init__(self):
        if type(self.trusted_signers) is not frozenset:
            raise ContractError("trusted_signers must be a frozenset")
        for signer in self.trusted_signers:
            _validate_signer(signer, "trusted signer")

    def is_trusted(self, signer):
        return signer in self.trusted_signers


def pin(extension_id, signer_id, data, *, version=CONTRACT_VERSION):
    """Author a contract from trusted bytes. Caller supplies the signer.

    `data` must be plain bytes. Custom objects are refused so no user code can
    run through __len__/__eq__ during hashing or comparison.
    """
    if type(data) is not bytes:
        raise ContractError("artifact data must be bytes")
    if len(data) > MAX_ARTIFACT_BYTES:
        raise ContractError("artifact exceeds the size bound")
    return IntegrityContract(extension_id, signer_id,
                             hashlib.sha256(data).hexdigest(), version)


def verify(contract, policy, observed_signer, observed_data):
    """Return a fail-closed decision. No extension code is loaded or executed.

    Order is deliberate: shape, version, signer, then digest. Unknown or
    mismatched signers are rejected before any bytes are hashed.
    """
    if not isinstance(contract, IntegrityContract) or not isinstance(policy, TrustPolicy):
        return Verification(Decision.MALFORMED_CONTRACT)
    if (type(observed_signer) is not str or type(observed_data) is not bytes):
        return Verification(Decision.INVALID_OBSERVATION)
    if len(observed_data) > MAX_ARTIFACT_BYTES:
        return Verification(Decision.OVERSIZED_ARTIFACT)
    if contract.version != CONTRACT_VERSION:
        return Verification(Decision.UNSUPPORTED_VERSION)
    if not policy.is_trusted(observed_signer):
        return Verification(Decision.UNKNOWN_SIGNER)
    if observed_signer != contract.signer_id:
        return Verification(Decision.SIGNER_MISMATCH)
    if not policy.is_trusted(contract.signer_id):
        return Verification(Decision.UNKNOWN_SIGNER)
    actual = hashlib.sha256(observed_data).hexdigest()
    if not hmac.compare_digest(contract.sha256, actual):
        return Verification(Decision.DIGEST_MISMATCH)
    return Verification(Decision.ACCEPTED)
