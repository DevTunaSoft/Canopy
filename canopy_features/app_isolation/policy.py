"""Pure decision layer for bounded app-isolation descriptions.

No function here starts a process, binds a namespace, writes a path, opens a
socket, starts a unit or approves a real-guest launch. A valid synthetic
request yields only an inert description with a REVIEW_REQUIRED final step;
a real-guest request is BLOCKED / NOT_RUN.
"""
from __future__ import annotations

from typing import Any, Tuple

from .contract import (
    ACCESS_EXPLICIT_WRITE,
    ACCESS_READ_ONLY,
    DESCRIBE_ONLY,
    FORBIDDEN_PERMISSIONS,
    GUEST_REAL_NOT_RUN,
    GUEST_SYNTHETIC,
    HOST_CONTEXT_GUEST,
    HOST_CONTEXT_HOST,
    NOT_RUN,
    REFUSE,
    SOURCE_POLICY,
    IsolationDecision,
    IsolationRequest,
    bound_reasons,
)
from .upstream import (
    MECHANISMS_BY_ECOSYSTEM,
    PERMISSIONS_BY_ECOSYSTEM,
    describe,
)

WRITE_PERMISSIONS = frozenset(("downloads_write", "config_write"))
_PRIVILEGED = frozenset((
    "privileged", "host_root", "always_on", "host_socket", "device_access",
    "unrestricted_network", "host_home_write",
))
_DUPLICATE = frozenset((
    "duplicate_sandbox", "duplicate_compositor", "duplicate_service",
))


def _result(action: str, reasons: Any, mechanisms: Tuple[str, ...],
            ecosystem: str, digest: str, steps: Tuple[str, ...] = ()) -> IsolationDecision:
    return IsolationDecision(action, steps, bound_reasons(reasons),
                             tuple(mechanisms), ecosystem, digest)


def evaluate_request(request: Any) -> IsolationDecision:
    """Evaluate one validated request into an inert decision.

    Fail closed on wrong types, untrusted provenance, unsigned or
    host-scoped claims, forbidden permissions, non-upstream mechanisms,
    duplicate services/core mutation claims, and non-FOSS conditions.
    """
    if type(request) is not IsolationRequest:
        return _result(REFUSE, ("REQUEST_TYPE_INVALID",), (), "", "")
    digest = request.digest()
    ecosystem = request.app.ecosystem
    mechanisms = request.mechanisms

    # First-party conditions are mandatory; no account, paid tier or telemetry.
    if not (request.no_paid_tiers and request.no_telemetry and request.no_accounts):
        return _result(REFUSE, ("NON_FOSS_CONDITION",), mechanisms, ecosystem,
                       digest)

    # A real guest is never contacted by this package, even for a description.
    if request.guest_class == GUEST_REAL_NOT_RUN:
        return _result(NOT_RUN, ("REAL_GUEST_BLOCKED", "GUEST_NOT_RUN"),
                       mechanisms, ecosystem, digest)
    if request.guest_class != GUEST_SYNTHETIC:
        return _result(REFUSE, ("GUEST_CLASS_INVALID",), mechanisms,
                       ecosystem, digest)
    if request.host_context == HOST_CONTEXT_HOST:
        return _result(REFUSE, ("HOST_ONLY_NO_GRANT",), mechanisms, ecosystem,
                       digest)
    if request.host_context != HOST_CONTEXT_GUEST:
        return _result(REFUSE, ("HOST_CONTEXT_INVALID",), mechanisms,
                       ecosystem, digest)

    reasons: list = []
    facts = request.facts
    if not request.source.verified or not facts.signature_verified:
        reasons.append("SIGNATURE_NOT_VERIFIED")
    if not facts.source_verified:
        reasons.append("PROVENANCE_NOT_VERIFIED")
    if not facts.upstream_mechanism_available:
        reasons.append("UPSTREAM_MECHANISM_UNAVAILABLE")
    if not facts.no_duplicate_service:
        reasons.append("DUPLICATE_SERVICE_REFUSED")
    if not facts.core_mutation_absent:
        reasons.append("CORE_MUTATION_REFUSED")
    if not facts.isolation_enforced:
        reasons.append("ISOLATION_NOT_ENFORCED")

    policy = SOURCE_POLICY.get(ecosystem)
    if policy is None or request.source.source_id != ecosystem:
        reasons.append("SOURCE_ECOSYSTEM_MISMATCH")
    else:
        if request.source.provenance not in policy["provenance"]:
            reasons.append("PROVENANCE_UNTRUSTED")
        if request.source.signature not in policy["signatures"]:
            reasons.append("SIGNATURE_UNSUPPORTED")

    permissions = set(request.app.permissions)
    forbidden = permissions & FORBIDDEN_PERMISSIONS
    if forbidden:
        reasons.append("FORBIDDEN_PERMISSION")
        if forbidden & _DUPLICATE:
            reasons.append("DUPLICATE_SANDBOX_REFUSED")
        if "core_mutation" in forbidden:
            reasons.append("CORE_MUTATION_REFUSED")
        if forbidden & _PRIVILEGED:
            reasons.append("PRIVILEGED_REFUSED")
    unknown = permissions - PERMISSIONS_BY_ECOSYSTEM.get(ecosystem, frozenset())
    if unknown:
        reasons.append("PERMISSION_NOT_ALLOWED")

    if request.app.access_mode == ACCESS_READ_ONLY and permissions & WRITE_PERMISSIONS:
        reasons.append("ACCESS_MODE_MISMATCH")
    if (request.app.access_mode == ACCESS_EXPLICIT_WRITE
            and not request.review_ack):
        reasons.append("WRITE_NEEDS_REVIEW")
    if request.app.access_mode not in (ACCESS_READ_ONLY, ACCESS_EXPLICIT_WRITE):
        reasons.append("ACCESS_MODE_INVALID")

    allowed_mechanisms = MECHANISMS_BY_ECOSYSTEM.get(ecosystem, frozenset())
    if (not mechanisms or len(mechanisms) > 8
            or any(item not in allowed_mechanisms for item in mechanisms)):
        reasons.append("MECHANISM_NOT_UPSTREAM")

    if reasons:
        return _result(REFUSE, reasons, mechanisms, ecosystem, digest)

    steps = describe(ecosystem, request.app.permissions, mechanisms)
    return _result(DESCRIBE_ONLY, (), mechanisms, ecosystem, digest, steps)
