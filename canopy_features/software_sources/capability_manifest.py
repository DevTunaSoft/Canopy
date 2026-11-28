"""Bounded source-aware capability manifest evaluation for five LacOS P0 ecosystems.

Pure, offline and read-only. The caller supplies an already-parsed manifest;
this module does not open files, resolve paths, invoke tools or use the
network. It turns a bounded declaration into an immutable decision.

A VALID manifest only means the declaration is internally consistent with the
P0 policy. It is NOT a signature check, installation approval, runtime trust
decision or evidence that a guest was tested. Guest probe facts are evaluated
separately in :mod:`canopy_features.software_sources.source_probe`.
"""

from collections.abc import Mapping
from dataclasses import dataclass
import re
import unicodedata
from typing import Any, FrozenSet, Tuple


# Five fixed P0 ecosystems; no discovery, no extensible registry.
ECOSYSTEMS = {
    "flatpak_flathub": {
        "label": "Flatpak / Flathub",
        "capabilities": frozenset(
            ("search", "install", "update", "remove", "launch", "permissions")),
        "provenance": frozenset(("official-flathub", "distribution-flatpak")),
        "signatures": frozenset(("gpg",)),
        "isolation": (
            "Flatpak sandbox with explicit portal permissions; no host "
            "filesystem, device, socket or privileged-service access by default"),
    },
    "apt_deb": {
        "label": "APT / DEB (Ubuntu and Debian)",
        "capabilities": frozenset(
            ("search", "install", "update", "remove", "launch")),
        "provenance": frozenset(("ubuntu-archive", "debian-archive")),
        "signatures": frozenset(("apt-signed-by",)),
        "isolation": (
            "APT/DEB only in its own compatible environment with its own "
            "database; no foreign host repository or host library overwrite"),
    },
    "pacman": {
        "label": "Pacman (Arch)",
        "capabilities": frozenset(
            ("search", "install", "update", "remove", "launch")),
        "provenance": frozenset(("arch-official",)),
        "signatures": frozenset(("pacman-key",)),
        "isolation": (
            "Pacman only in an isolated Arch-compatible environment with a "
            "separate database; no partial upgrades and no foreign host repos"),
    },
    "dnf_rpm": {
        "label": "DNF / RPM (Fedora)",
        "capabilities": frozenset(
            ("search", "install", "update", "remove", "launch")),
        "provenance": frozenset(("fedora-official",)),
        "signatures": frozenset(("rpm-gpg",)),
        "isolation": (
            "DNF/RPM only in a Fedora-compatible environment; signed official "
            "sources, no foreign host repository or host library overwrite"),
    },
    "rootless_podman_oci": {
        "label": "Rootless Podman / OCI",
        "capabilities": frozenset(
            ("search", "pull", "run", "update", "remove", "permissions")),
        "provenance": frozenset(("official-registry", "verified-image")),
        "signatures": frozenset(("cosign", "sigstore")),
        "isolation": (
            "Rootless Podman is not a complete sandbox: restrict host files, "
            "credentials, devices, sockets, privileged services and network; "
            "no privileged defaults and no always-on runtime"),
    },
}
ECOSYSTEM_IDS = tuple(sorted(ECOSYSTEMS))
CAPABILITIES_BY_ECOSYSTEM = {
    name: spec["capabilities"] for name, spec in ECOSYSTEMS.items()
}

# Never grantable, even if an ecosystem's ordinary capability set changes.
FORBIDDEN_CAPABILITIES = frozenset((
    "core_mutation", "host_repo_mixing", "foreign_repo_mix", "partial_upgrade",
    "privileged", "telemetry", "paid_tier", "always_on",
))

# Bounds keep hostile mappings from growing work or hiding payloads in nesting.
MAX_FIELDS = 40
MAX_ECOSYSTEM_FIELDS = 8
MAX_SOURCES = 4
MAX_CAPABILITIES = 8
MAX_STRING_CHARS = 120
MAX_TOTAL_CHARS = 8192
MAX_DEPTH = 6

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_UNSAFE_UNICODE = frozenset(("Cs", "Co", "Cn", "Zl", "Zp"))
_URI = re.compile(
    r"^(?:[A-Za-z][A-Za-z0-9+.-]*://|(?:file|data|javascript|mailto):)",
    re.IGNORECASE)
_TRAVERSAL = re.compile(r"(?:^|[\\/])\.\.(?:[\\/]|$)")
_ABSOLUTE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|/)")
_EXECUTABLE_KEY = re.compile(
    r"(?:^|_)(?:exec|executable|command|cmd|script|run|hook|callback|spawn|"
    r"launch|process|binary|program|eval|code|module|import|subprocess|payload|"
    r"path|file|url|uri|argv|load|socket|mount)(?:$|_)",
    re.IGNORECASE)
_EXECUTABLE_VALUE = re.compile(
    r"(?:`|\$\(|&&|\|\||\b(?:sudo|rm|curl|wget|chmod|chown|mkfs|nc|ncat)\b|"
    r"\b(?:subprocess|os\.system|os\.popen|eval|exec)\b)",
    re.IGNORECASE)
_SEPARATOR = re.compile(r"[^A-Za-z0-9]+")
_CAMEL_LOWER_UPPER = re.compile(r"([a-z0-9])([A-Z])")
_CAMEL_ACRONYM = re.compile(r"([A-Z])([A-Z][a-z])")
_SOURCE_ID = re.compile(r"[a-z][a-z0-9_-]{2,48}\Z")
_ECOSYSTEM_FIELDS = frozenset((
    "enabled", "on_demand", "runtime_installed_by_default",
    "capabilities", "sources",
))
_SOURCE_FIELDS = frozenset(("id", "provenance", "signature", "verified", "scope"))
_TOP_FIELDS = frozenset((
    "schema_version", "target", "no_core_mutation", "foreign_host_repo_mixing",
    "paid_tiers", "telemetry", "duplicate_always_on_services", "ecosystems",
))


@dataclass(frozen=True)
class EcosystemDecision:
    """Declaration-level decision for one ecosystem. No execution approval."""

    ecosystem: str
    status: str  # DECLARED | DISABLED | NOT_EVALUATED
    capabilities: FrozenSet[str]
    source_ids: Tuple[str, ...]
    isolation: str


@dataclass(frozen=True)
class ManifestReport:
    """Immutable result of one bounded manifest evaluation."""

    status: str  # VALID | INVALID
    target: str
    decisions: Tuple[EcosystemDecision, ...]
    violations: Tuple[str, ...]
    detail: str

    @property
    def ok(self) -> bool:
        return self.status == "VALID"


def ecosystem_decision(ecosystem: str) -> EcosystemDecision:
    """Return the neutral declaration for one ecosystem, without granting it."""
    spec = ECOSYSTEMS[ecosystem]
    return EcosystemDecision(ecosystem, "NOT_EVALUATED", frozenset(), (),
                             spec["isolation"])


def _normalize_key(key: str) -> str:
    folded = _CAMEL_LOWER_UPPER.sub(r"\1_\2", key)
    folded = _CAMEL_ACRONYM.sub(r"\1_\2", folded)
    return _SEPARATOR.sub("_", folded).strip("_").lower()


def _check_string(value: str) -> None:
    if _CONTROL.search(value):
        raise ValueError("control character")
    if any(unicodedata.category(char) in _UNSAFE_UNICODE for char in value):
        raise ValueError("unsafe unicode")
    if _URI.match(value) or _TRAVERSAL.search(value) or _ABSOLUTE.match(value):
        raise ValueError("uri or path")
    if _EXECUTABLE_VALUE.search(value):
        raise ValueError("executable-looking value")


def _scan(value: Any, depth: int, budget: list) -> None:
    if depth > MAX_DEPTH:
        raise ValueError("too deep")
    if isinstance(value, Mapping):
        if len(value) > MAX_FIELDS:
            raise ValueError("too many fields")
        for key, child in value.items():
            if not isinstance(key, str) or _EXECUTABLE_KEY.search(_normalize_key(key)):
                raise ValueError("executable-looking field")
            _scan(child, depth + 1, budget)
        return
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_FIELDS:
            raise ValueError("list too long")
        for child in value:
            _scan(child, depth + 1, budget)
        return
    if isinstance(value, str):
        budget[0] += len(value)
        if len(value) > MAX_STRING_CHARS or budget[0] > MAX_TOTAL_CHARS:
            raise ValueError("string too large")
        _check_string(value)
        return
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int) and abs(value).bit_length() <= 32:
        return
    raise ValueError("unsupported value type")


def _invalid(target: str, violations: Tuple[str, ...], detail: str) -> ManifestReport:
    return ManifestReport("INVALID", target, tuple(
        ecosystem_decision(name) for name in ECOSYSTEM_IDS), violations, detail)


def _check_sources(ecosystem: str, raw: Any, spec: Mapping,
                   violations: list) -> Tuple[str, ...]:
    """Validate bounded source declarations; return source ids on success."""
    if not isinstance(raw, (list, tuple)) or not raw or len(raw) > MAX_SOURCES:
        violations.append(f"{ecosystem}:SOURCE_SET_INVALID")
        return ()
    ids = []
    for source in raw:
        if not isinstance(source, Mapping) or set(source) != _SOURCE_FIELDS:
            violations.append(f"{ecosystem}:SOURCE_FIELDS_INVALID")
            return ()
        source_id = source.get("id")
        if not isinstance(source_id, str) or not _SOURCE_ID.fullmatch(source_id):
            violations.append(f"{ecosystem}:SOURCE_ID_INVALID")
            return ()
        provenance = source.get("provenance")
        if type(provenance) is not str or provenance not in spec["provenance"]:
            violations.append(f"{ecosystem}:SOURCE_PROVENANCE_INVALID")
            return ()
        signature = source.get("signature")
        if type(signature) is not str or signature not in spec["signatures"]:
            violations.append(f"{ecosystem}:SOURCE_SIGNATURE_INVALID")
            return ()
        if source.get("verified") is not True or source.get("scope") != "guest-only":
            violations.append(f"{ecosystem}:SOURCE_SCOPE_INVALID")
            return ()
        if source_id in ids:
            violations.append(f"{ecosystem}:SOURCE_ID_DUPLICATE")
            return ()
        ids.append(source_id)
    return tuple(ids)


def evaluate_manifest(manifest: Mapping[str, Any]) -> ManifestReport:
    """Evaluate one untrusted manifest mapping against the P0 source policy.

    Fail closed on wrong types, unexpected fields, hostile-looking strings,
    oversized input, missing ecosystems, unsigned or non-upstream sources,
    forbidden capabilities and any core/host mutation request. Never reads the
    host and never approves an installation.
    """
    if not isinstance(manifest, Mapping):
        return _invalid("", ("TOP_NOT_MAPPING",), "manifest must be a mapping")
    try:
        field_count = len(manifest)
    except Exception:
        return _invalid("", ("TOP_UNSIZABLE",), "manifest cannot be sized")
    if field_count > MAX_FIELDS:
        return _invalid("", ("TOP_TOO_MANY_FIELDS",), "manifest has too many fields")
    data = dict(manifest)
    if set(data) - _TOP_FIELDS:
        return _invalid("", ("TOP_UNKNOWN_FIELD",), "manifest has an unknown field")
    try:
        _scan(data, 0, [0])
    except ValueError as exc:
        return _invalid("", ("HOSTILE_FIELD", f"unsafe manifest content: {exc}"),
                        "manifest contains unsafe content")

    target = data.get("target")
    if type(target) is not str:
        target = ""
    violations = []
    if data.get("schema_version") != 1:
        violations.append("TOP_SCHEMA_VERSION_INVALID")
    if target != "lacos-guest":
        violations.append("TOP_TARGET_INVALID")
    if data.get("no_core_mutation") is not True:
        violations.append("TOP_NO_CORE_MUTATION_REQUIRED")
    if data.get("foreign_host_repo_mixing") is not False:
        violations.append("TOP_FOREIGN_HOST_REPO_MIXING_REQUIRED")
    if data.get("paid_tiers") is not False:
        violations.append("TOP_PAID_TIERS_REQUIRED")
    if data.get("telemetry") is not False:
        violations.append("TOP_TELEMETRY_REQUIRED")
    if data.get("duplicate_always_on_services") is not False:
        violations.append("TOP_NO_DUPLICATE_SERVICES_REQUIRED")

    raw_ecosystems = data.get("ecosystems")
    if (not isinstance(raw_ecosystems, Mapping)
            or set(raw_ecosystems) != set(ECOSYSTEM_IDS)):
        violations.append("ECOSYSTEM_SET_INVALID")
        return _invalid(target, tuple(violations), "P0 ecosystem set is invalid")

    decisions = []
    for name in ECOSYSTEM_IDS:
        spec = ECOSYSTEMS[name]
        raw = raw_ecosystems[name]
        if (not isinstance(raw, Mapping) or len(raw) > MAX_ECOSYSTEM_FIELDS
                or set(raw) != _ECOSYSTEM_FIELDS):
            violations.append(f"{name}:FIELDS_INVALID")
            decisions.append(ecosystem_decision(name))
            continue
        if raw.get("enabled") is not True:
            violations.append(f"{name}:NOT_ENABLED")
            decisions.append(ecosystem_decision(name))
            continue
        if raw.get("on_demand") is not True:
            violations.append(f"{name}:NOT_ON_DEMAND")
        if raw.get("runtime_installed_by_default") is not False:
            violations.append(f"{name}:DEFAULT_RUNTIME_INSTALLED")

        capabilities = raw.get("capabilities")
        if (not isinstance(capabilities, (list, tuple)) or not capabilities
                or len(capabilities) > MAX_CAPABILITIES
                or any(type(cap) is not str for cap in capabilities)
                or len(set(capabilities)) != len(capabilities)):
            violations.append(f"{name}:CAPABILITIES_INVALID")
            granted = frozenset()
        elif set(capabilities) & FORBIDDEN_CAPABILITIES:
            violations.append(f"{name}:CAPABILITY_FORBIDDEN")
            granted = frozenset()
        elif set(capabilities) - spec["capabilities"]:
            violations.append(f"{name}:CAPABILITY_UNKNOWN")
            granted = frozenset()
        else:
            granted = frozenset(capabilities)

        source_ids = _check_sources(name, raw.get("sources"), spec, violations)
        decisions.append(EcosystemDecision(
            name, "DECLARED" if granted and source_ids else "NOT_EVALUATED",
            granted, source_ids, spec["isolation"]))

    if violations:
        return _invalid(target, tuple(violations), "manifest violates P0 policy")
    return ManifestReport(
        "VALID", target, tuple(decisions), (),
        "declaration only; signature verification and guest acceptance are NOT_RUN",
    )
