"""LacOS P1 application-isolation foundation (bounded, read-only first).

This package is a contract and a decision layer only. It names upstream
mechanisms (Flatpak/bubblewrap portals and systemd user scopes/unit sandboxing)
and evaluates a caller-supplied request. It never launches an application,
starts a service, creates a sandbox, opens a socket, writes a file, or claims
that a real guest was tested.

Real-guest isolation is BLOCKED / NOT_RUN. Synthetic fixtures exercise only
the decision contracts.
"""
from .contract import (  # noqa: F401
    ACCESS_EXPLICIT_WRITE,
    ACCESS_READ_ONLY,
    BLOCKED,
    DESCRIBE_ONLY,
    ECOSYSTEMS,
    FORBIDDEN_PERMISSIONS,
    HOST_CONTEXT_GUEST,
    HOST_CONTEXT_HOST,
    MAX_DOC_BYTES,
    MAX_MECHANISMS,
    MAX_PERMISSIONS,
    MAX_REASONS,
    NOT_RUN,
    REFUSE,
    SCHEMA,
    SOURCE_POLICY,
    TOOL_NAME,
    TOOL_VERSION,
    AppIsolationError,
    AppSpec,
    HostFacts,
    IsolationDecision,
    IsolationRequest,
    SourceClaim,
    bound_reasons,
    canonical_bytes,
    digest_bytes,
    parse_bounded_document,
    parse_request_document,
    valid_app_id,
    valid_digest,
    valid_label,
    valid_permission,
)
from .upstream import (  # noqa: F401
    MECHANISMS,
    MECHANISMS_BY_ECOSYSTEM,
    describe,
    upstream_surface,
    valid_mechanism,
)
from .policy import evaluate_request  # noqa: F401

__all__ = [
    "ACCESS_EXPLICIT_WRITE", "ACCESS_READ_ONLY", "BLOCKED", "DESCRIBE_ONLY",
    "ECOSYSTEMS", "FORBIDDEN_PERMISSIONS", "HOST_CONTEXT_GUEST",
    "HOST_CONTEXT_HOST", "MAX_DOC_BYTES", "MAX_MECHANISMS", "MAX_PERMISSIONS",
    "MAX_REASONS", "NOT_RUN", "REFUSE", "SCHEMA", "SOURCE_POLICY",
    "TOOL_NAME", "TOOL_VERSION", "AppIsolationError", "AppSpec", "HostFacts",
    "IsolationDecision", "IsolationRequest", "SourceClaim", "bound_reasons",
    "canonical_bytes", "digest_bytes", "parse_bounded_document",
    "parse_request_document", "valid_app_id", "valid_digest", "valid_label",
    "valid_permission", "MECHANISMS", "MECHANISMS_BY_ECOSYSTEM", "describe",
    "upstream_surface", "valid_mechanism", "evaluate_request",
]
