"""LacOS multi-ecosystem support: bounded read-only-first capability mapping.

No module here executes a package manager, contacts a guest, mutates the core,
launches an app, promotes a restore, or grants a capability. Upstream P0
artifacts are cited by exact SHA-256 and consumed as synthetic declarations.
"""

from .capability_map import (
    CapabilityEntry,
    CapabilityMap,
    EcosystemEntry,
    build_capability_map,
    view_dict,
)
from .contract import (
    ALLOWED_PROVENANCE,
    ALLOWED_SIGNATURES,
    CANONICAL_ECOSYSTEM_IDS,
    FORBIDDEN_CAPABILITIES,
    FORBIDDEN_EVIDENCE_LABELS,
    KNOWN_CAPABILITIES,
    MUTATING_CAPABILITIES,
    READ_ONLY_CAPABILITIES,
    REQUIRED_EVIDENCE_LABELS,
    SOURCE_HEADS,
    SOURCE_SHA256,
    MultiEcosystemError,
    reject_duplicate_keys,
)

__all__ = [
    "CapabilityEntry",
    "CapabilityMap",
    "EcosystemEntry",
    "MultiEcosystemError",
    "ALLOWED_PROVENANCE",
    "ALLOWED_SIGNATURES",
    "CANONICAL_ECOSYSTEM_IDS",
    "FORBIDDEN_CAPABILITIES",
    "FORBIDDEN_EVIDENCE_LABELS",
    "KNOWN_CAPABILITIES",
    "MUTATING_CAPABILITIES",
    "READ_ONLY_CAPABILITIES",
    "REQUIRED_EVIDENCE_LABELS",
    "SOURCE_HEADS",
    "SOURCE_SHA256",
    "build_capability_map",
    "reject_duplicate_keys",
    "view_dict",
]
