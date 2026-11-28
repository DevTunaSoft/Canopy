"""Bounded, read-only vocabulary for the LacOS multi-ecosystem capability map.

This module is pure policy data and validation. It never opens a file, runs a
process, contacts a network, starts a service, or imports an unmerged feature
branch. The upstream P0 artifacts are cited by exact SHA-256, not executed.
"""

from __future__ import annotations

import json
import re
import unicodedata

CANONICAL_ECOSYSTEM_IDS = (
    "apt_deb",
    "dnf_rpm",
    "flatpak_flathub",
    "pacman",
    "rootless_podman_oci",
)

READ_ONLY_CAPABILITIES = frozenset(("search", "permissions"))
MUTATING_CAPABILITIES = frozenset(
    ("install", "update", "remove", "pull", "run", "launch"))
KNOWN_CAPABILITIES = frozenset(READ_ONLY_CAPABILITIES | MUTATING_CAPABILITIES)

FORBIDDEN_CAPABILITIES = frozenset((
    "core_mutation", "host_repo_mixing", "partial_upgrade", "privileged",
    "telemetry", "paid_tier", "always_on", "accounts", "duplicate_service",
    "foreign_repo_mix", "host_root", "host_socket", "device_access",
    "unrestricted_network", "host_home_write", "duplicate_sandbox",
    "duplicate_compositor", "account_required",
))

FORBIDDEN_EVIDENCE_LABELS = frozenset(
    ("NATIVE RUNTIME", "GUEST ACCEPTED", "VERIFIED"))
REQUIRED_EVIDENCE_LABELS = ("STATIC SOURCE ONLY", "SYNTHETIC")

ALLOWED_PROVENANCE = {
    "flatpak_flathub": frozenset(("official-flathub", "distribution-flatpak")),
    "apt_deb": frozenset(("ubuntu-archive", "debian-archive")),
    "pacman": frozenset(("arch-official",)),
    "dnf_rpm": frozenset(("fedora-official",)),
    "rootless_podman_oci": frozenset(("official-registry", "verified-image")),
}
ALLOWED_SIGNATURES = {
    "flatpak_flathub": frozenset(("gpg",)),
    "apt_deb": frozenset(("apt-signed-by",)),
    "pacman": frozenset(("pacman-key",)),
    "dnf_rpm": frozenset(("rpm-gpg",)),
    "rootless_podman_oci": frozenset(("cosign", "sigstore")),
}

# Exact upstream heads consumed read-only from the locally fetched origin refs.
# These are provenance citations only: no upstream module is imported or run.
SOURCE_HEADS = {
    "lacos_sources": "616ce171a7b71f69f19060122f53c97ada346662",
    "lacos_atomic_updates": "d808c6e852a28063a45fa702a8463a65f3d28ae5",
    "lacos_backup_recovery": "43792968d56945a637e27b790e9cefe3ebf7dabd",
    "lacos_app_isolation": "f4ee9975ce49943c4ee1adf47e9648c21beab5ab",
}

# SHA-256 of representative upstream files at those exact heads (read-only).
SOURCE_SHA256 = {
    "lacos_sources:capability_manifest.py":
        "91ca6a8bd677c7a584b6c89ada7bb737b5c3a8bbe9da7b1c4cba21344df4d983",
    "lacos_sources:source_probe.py":
        "66685a317e745cddaf33f7c6d92b7d4fe195bc83716b43c55683ac292d981ade",
    "lacos_sources:manifest_valid.json":
        "f0d656acb162d278a22ad790401e886727e71487df91f0b584314098e1977971",
    "lacos_sources:probe_guest_synthetic.json":
        "b10288558f997c4d729539c39e9993883758e2bdface7424ca254794fbf27524",
    "lacos_atomic_updates:contract.py":
        "65d4b2633e0387d6f87fc76f9087bb349011c2e3a8a2a9caa0c8a877f382ba6a",
    "lacos_atomic_updates:F001-ready-handoff.json":
        "b5c82679ae5f990c8f0baf4717c50a08afbe8984c9a99c8fb12bd28c14da30a4",
    "lacos_backup_recovery:contract.py":
        "2907afd1ce0183a4417fc4562cb3a875ac29c390f6a3e399995867fb54b1799b",
    "lacos_backup_recovery:manifest.json":
        "56d9c543b0ff3662600d0645145c84a768f3d237c58b1131e2cddf02665885cc",
    "lacos_app_isolation:policy.py":
        "2c797e671fa8c305bae02c88ed005985914ea864da472aeec82d26cda9bc18d8",
    "lacos_app_isolation:F001_valid_flatpak.json":
        "c2e48613911d140326cd4c566c28d6288031fcf2b3611da54616b19ad2b1738b",
}

MAX_SNAPSHOT_CHARS = 8192
MAX_STRING_CHARS = 120
MAX_ECOSYSTEMS = 5
MAX_CAPABILITIES = 8
MAX_SOURCES = 4
MAX_DEPTH = 6
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.:-]*\Z")


class MultiEcosystemError(Exception):
    """Fail-closed domain error with a stable machine-readable code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def reject_duplicate_keys(pairs):
    """object_pairs_hook: reject duplicate JSON keys before any evaluation."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise MultiEcosystemError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def canonical_json(value) -> str:
    """Canonical, deterministic serialization of bounded plain JSON values."""
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        raise MultiEcosystemError("CANONICAL_JSON_INVALID") from None


def bounded_text(value, code: str) -> str:
    """Exact, printable, pathless, bounded text only."""
    if type(value) is not str or not value or len(value) > MAX_STRING_CHARS:
        raise MultiEcosystemError(code)
    if "\\" in value or ".." in value or "://" in value:
        raise MultiEcosystemError(code)
    if value.startswith("/") or re.match(r"[A-Za-z]:", value):
        raise MultiEcosystemError(code)
    for character in value:
        if unicodedata.category(character) in ("Cc", "Cf", "Cs", "Co", "Cn"):
            raise MultiEcosystemError(code)
    return value


def exact_bool(value, code: str) -> bool:
    if type(value) is not bool:
        raise MultiEcosystemError(code)
    return value


def exact_int(value, code: str) -> int:
    if type(value) is not int:
        raise MultiEcosystemError(code)
    return value


def exact_keys(mapping, keys, code: str) -> None:
    if type(mapping) is not dict or frozenset(mapping) != frozenset(keys):
        raise MultiEcosystemError(code)


def hex64(value, code: str) -> str:
    if type(value) is not str or not HEX64.fullmatch(value):
        raise MultiEcosystemError(code)
    return value


def hex40(value, code: str) -> str:
    if type(value) is not str or not HEX40.fullmatch(value):
        raise MultiEcosystemError(code)
    return value


def check_bounds(document) -> str:
    """Reject oversized or over-nested documents and return canonical JSON."""
    text = canonical_json(document)
    if len(text) > MAX_SNAPSHOT_CHARS:
        raise MultiEcosystemError("SNAPSHOT_TOO_LARGE")

    stack = [(document, 1)]
    while stack:
        value, depth = stack.pop()
        if depth > MAX_DEPTH:
            raise MultiEcosystemError("SNAPSHOT_TOO_DEEP")
        if isinstance(value, dict):
            for key, item in value.items():
                if type(key) is not str or not _NAME.fullmatch(key):
                    raise MultiEcosystemError("KEY_INVALID")
                stack.append((item, depth + 1))
        elif isinstance(value, (list, tuple)):
            if type(value) is not list:
                raise MultiEcosystemError("UNORDERED_CONTAINER")
            for item in value:
                stack.append((item, depth + 1))
    return text
