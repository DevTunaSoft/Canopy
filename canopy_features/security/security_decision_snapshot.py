"""Pure, immutable composition of offline security decisions.

This module combines the decision outputs of three already-tested pure
validators that live at separate host trust boundaries:

* ``untrusted_uri_schemes`` -- scheme gate for UI launch intents,
* ``privilege_boundary`` -- deny gate for helper argv,
* ``pack_manifest_metadata`` -- data-only projection of untrusted pack metadata.

It records only fixed status tokens and the privilege reason code; no URI,
argument, path or metadata value is copied into the record or an error. The
result is diagnostic evidence of what each validate-only boundary decided. It
is NOT a launch authorization, sandbox, signature check, privilege elevation,
runtime loader or evidence of a wired desktop: those negative claims are
hardcoded in :meth:`SecurityDecisionSnapshot.as_dict`.

Nothing is launched, executed, imported at runtime, read from disk or polled.
The caller supplies every value and an explicit ``euid``; elevation detection
is never performed here. Malformed wrapper shape or an unrecognized component
contract fails closed with :class:`SnapshotError`.
"""
from collections.abc import Mapping
from dataclasses import dataclass

from canopy_features.security import pack_manifest_metadata as metadata_mod
from canopy_features.security import privilege_boundary as priv_mod
from canopy_features.security import untrusted_uri_schemes as uri_mod
from tools.check_shell_pack import CAPABILITIES, PackValidationError

SCHEMA = 1
TOP_KEYS = frozenset({"schema", "uri_intent", "argv", "manifest", "euid"})

URI_STATUSES = frozenset({"PERMITTED", "REJECTED"})
PRIVILEGE_STATUSES = frozenset({"ALLOWED", "DENIED"})
METADATA_STATUSES = frozenset({"SAFE", "REJECTED"})
PRIVILEGE_REASONS = frozenset({
    priv_mod.ALLOWED,
    priv_mod.DENIED_EMPTY_ACTION,
    priv_mod.DENIED_INVALID_ACTION,
    priv_mod.DENIED_OVERSIZED,
    priv_mod.DENIED_INHERITED_ROOT,
    priv_mod.DENIED_ELEVATION,
    priv_mod.DENIED_SYSTEM_COMMAND,
})

# Pre-bound the untrusted top-level mapping so a hostile mapping is refused
# before to_safe_metadata() materializes it with dict(). The owning validator
# still applies its own stricter MAX_FIELDS bound afterwards.
MAX_MANIFEST_FIELDS = 128
MAX_EUID = 2 ** 32 - 1


class SnapshotError(ValueError):
    """Malformed, unbounded or unrecognized decision snapshot input."""


def _bounded_int(value, label, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise SnapshotError("decision snapshot " + label + " is invalid")
    return value


def _uri_status(uri_intent):
    if type(uri_intent) is str and len(uri_intent) > uri_mod.MAX_URI_CHARS:
        return "REJECTED"
    try:
        uri_mod.validate_uri_intent(uri_intent)
    except uri_mod.UntrustedUriError:
        return "REJECTED"
    return "PERMITTED"


def _privilege(argv, euid):
    decision = priv_mod.evaluate(argv, euid=euid)
    if type(decision.allowed) is not bool:
        raise SnapshotError("unsupported privilege decision type")
    reason = decision.reason
    if type(reason) is not str or reason not in PRIVILEGE_REASONS:
        raise SnapshotError("unsupported privilege reason code")
    return ("ALLOWED" if decision.allowed else "DENIED"), reason


def _metadata(manifest):
    if isinstance(manifest, Mapping) and len(manifest) > MAX_MANIFEST_FIELDS:
        return "REJECTED", 0
    try:
        safe = metadata_mod.to_safe_metadata(manifest)
    except PackValidationError:
        return "REJECTED", 0
    count = len(safe.capabilities)
    if type(count) is not int or not 0 <= count <= len(CAPABILITIES):
        raise SnapshotError("unsupported capability count")
    return "SAFE", count


@dataclass(frozen=True)
class SecurityDecisionSnapshot:
    """Frozen, value-free record of three validate-only boundary decisions."""

    schema: int
    uri_status: str
    privilege_status: str
    privilege_reason: str
    metadata_status: str
    metadata_capability_count: int

    def as_dict(self):
        """Return a fresh JSON-friendly copy with fixed negative claims.

        Every claim field is hardcoded here rather than stored on the record,
        so even a directly constructed (forged) record cannot emit a launch
        authorization through the public serialization path.
        """
        _bounded_int(self.schema, "schema", SCHEMA, SCHEMA)
        # Type-check before every frozenset membership: an unhashable wrong
        # type must not leak a raw TypeError past this fail-closed boundary.
        if type(self.uri_status) is not str or self.uri_status not in URI_STATUSES:
            raise SnapshotError("unsupported URI status token")
        if (type(self.privilege_status) is not str
                or self.privilege_status not in PRIVILEGE_STATUSES):
            raise SnapshotError("unsupported privilege status token")
        if (type(self.privilege_reason) is not str
                or self.privilege_reason not in PRIVILEGE_REASONS):
            raise SnapshotError("unsupported privilege reason token")
        # Cross-field contract: the reason code is the ground truth emitted by
        # the privilege validator -- ALLOWED pairs only with its single success
        # code, DENIED only with a denial code. Each field above is a valid
        # token on its own, so a forged record pairing ALLOWED with a denial
        # reason (or DENIED with the success reason) would otherwise emit a
        # self-contradictory allow/deny claim. Fail closed on that mismatch.
        status_allows = self.privilege_status == "ALLOWED"
        reason_allows = self.privilege_reason == priv_mod.ALLOWED
        if status_allows != reason_allows:
            raise SnapshotError("contradictory privilege decision flags")
        if (type(self.metadata_status) is not str
                or self.metadata_status not in METADATA_STATUSES):
            raise SnapshotError("unsupported metadata status token")
        _bounded_int(self.metadata_capability_count, "capability count",
                     0, len(CAPABILITIES))
        # Cross-field contract: the capability count is the durable ground
        # truth emitted by to_safe_metadata -- SAFE is returned only with at
        # least one valid capability, and a rejection always yields zero.
        # Each field is a valid token on its own, so a forged record pairing
        # SAFE with zero (or REJECTED with capabilities) would otherwise emit
        # a false decision-safe claim about the metadata boundary. Fail closed
        # by re-deriving the status from the count before any claim is returned.
        expected_metadata_status = (
            "SAFE" if self.metadata_capability_count > 0 else "REJECTED")
        if self.metadata_status != expected_metadata_status:
            raise SnapshotError("contradictory metadata decision flags")
        return {
            "status": "SNAPSHOT",
            "schema": SCHEMA,
            "uri_status": self.uri_status,
            "privilege_status": self.privilege_status,
            "privilege_reason": self.privilege_reason,
            "metadata_status": self.metadata_status,
            "metadata_capability_count": self.metadata_capability_count,
            "launch_authorized": False,
            "process_launched": False,
            "release_approved": False,
            "linux_mint_acceptance_proven": False,
            "real_hardware_measured": False,
            "owner_visual_approval": False,
            "measurement_performed": False,
        }


def compose_decision(*, uri_intent, argv, manifest, euid):
    """Compose the three validators into one frozen decision snapshot.

    ``euid`` is supplied explicitly by the caller (``None`` means elevation
    detection is unavailable); this module never detects or changes it.
    """
    if euid is not None:
        _bounded_int(euid, "euid", 0, MAX_EUID)
    uri_status = _uri_status(uri_intent)
    privilege_status, privilege_reason = _privilege(argv, euid)
    metadata_status, count = _metadata(manifest)
    return SecurityDecisionSnapshot(
        schema=SCHEMA,
        uri_status=uri_status,
        privilege_status=privilege_status,
        privilege_reason=privilege_reason,
        metadata_status=metadata_status,
        metadata_capability_count=count,
    )


def snapshot(record):
    """Validate the bounded wrapper shape, then compose the decision."""
    if type(record) is not dict or frozenset(record) != TOP_KEYS:
        raise SnapshotError("decision snapshot has an unexpected key set")
    _bounded_int(record["schema"], "schema", SCHEMA, SCHEMA)
    return compose_decision(
        uri_intent=record["uri_intent"],
        argv=record["argv"],
        manifest=record["manifest"],
        euid=record["euid"],
    )
