"""Pure, bounded, read-only Software Center presentation for five LacOS P0 ecosystems.

This module is the presentation half of a source-aware unified Software Center.
It never imports, mutates or duplicates the unmerged source-policy PR #753: it
validates a pinned, read-only snapshot projected from that PR's real evaluator
output. A valid view is a declaration-only presentation. It is NOT a signature
verification, an installation grant, a guest test or a running Software Center.

Contract of a consumed snapshot (all fields mandatory, no extras)::

    schema_version, source, policy, ecosystems, evidence_labels,
    guest_acceptance, runtime

Hostile or malformed input fails closed with :class:`SoftwareCenterError`.
"""

from collections.abc import Mapping
from dataclasses import dataclass
import re
from types import MappingProxyType
import unicodedata
from typing import Any, FrozenSet, Tuple


class SoftwareCenterError(ValueError):
    """Domain error raised for an invalid or hostile snapshot.

    ``code`` is a stable, short reason code used by the bounded verifier and by
    negative controls. The message is the same code; no host path is included.
    """

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# Fixed five P0 ecosystems; canonical order, no discovery, no registry.
ECOSYSTEM_IDS: Tuple[str, ...] = (
    "apt_deb", "dnf_rpm", "flatpak_flathub", "pacman", "rootless_podman_oci",
)

# Pinned read-only projection of PR #753 (head 616ce171) source policy. These
# values are presentation pins, not executable policy and not a runtime grant.
_ECOSYSTEM_SPEC = {
    "apt_deb": {
        "label": "APT / DEB (Ubuntu and Debian)",
        "capabilities": frozenset(("search", "install", "update", "remove", "launch")),
        "provenance": frozenset(("ubuntu-archive", "debian-archive")),
        "signatures": frozenset(("apt-signed-by",)),
        "isolation": (
            "APT/DEB only in its own compatible environment with its own "
            "database; no foreign host repository or host library overwrite"),
    },
    "dnf_rpm": {
        "label": "DNF / RPM (Fedora)",
        "capabilities": frozenset(("search", "install", "update", "remove", "launch")),
        "provenance": frozenset(("fedora-official",)),
        "signatures": frozenset(("rpm-gpg",)),
        "isolation": (
            "DNF/RPM only in a Fedora-compatible environment; signed official "
            "sources, no foreign host repository or host library overwrite"),
    },
    "flatpak_flathub": {
        "label": "Flatpak / Flathub",
        "capabilities": frozenset((
            "search", "install", "update", "remove", "launch", "permissions")),
        "provenance": frozenset(("official-flathub", "distribution-flatpak")),
        "signatures": frozenset(("gpg",)),
        "isolation": (
            "Flatpak sandbox with explicit portal permissions; no host "
            "filesystem, device, socket or privileged-service access by default"),
    },
    "pacman": {
        "label": "Pacman (Arch)",
        "capabilities": frozenset(("search", "install", "update", "remove", "launch")),
        "provenance": frozenset(("arch-official",)),
        "signatures": frozenset(("pacman-key",)),
        "isolation": (
            "Pacman only in an isolated Arch-compatible environment with a "
            "separate database; no partial upgrades and no foreign host repos"),
    },
    "rootless_podman_oci": {
        "label": "Rootless Podman / OCI",
        "capabilities": frozenset((
            "search", "pull", "run", "update", "remove", "permissions")),
        "provenance": frozenset(("official-registry", "verified-image")),
        "signatures": frozenset(("cosign", "sigstore")),
        "isolation": (
            "Rootless Podman is not a complete sandbox: restrict host files, "
            "credentials, devices, sockets, privileged services and network; "
            "no privileged defaults and no always-on runtime"),
    },
}

# Never presentable, including PR #753's denials and account/paid access.
FORBIDDEN_CAPABILITIES: FrozenSet[str] = frozenset((
    "core_mutation", "host_repo_mixing", "foreign_repo_mix", "partial_upgrade",
    "privileged", "telemetry", "paid_tier", "paid", "account", "accounts",
    "always_on", "duplicate_service",
))

_TOP_FIELDS = frozenset((
    "schema_version", "source", "policy", "ecosystems", "evidence_labels",
    "guest_acceptance", "runtime",
))
_SOURCE_FIELDS = frozenset((
    "pr", "head_sha", "base_sha", "consumption", "sha256",
))
_POLICY_FIELDS = frozenset((
    "no_core_mutation", "foreign_host_repo_mixing", "paid_tiers", "telemetry",
    "duplicate_always_on_services", "accounts",
))
_CARD_FIELDS = frozenset((
    "id", "label", "status", "capabilities", "source_ids", "provenance",
    "signature_schemes", "signature_status", "isolation", "core_mutation",
    "probe_status", "guest_acceptance",
))
_SOURCE_HASH_FIELDS = frozenset(("capability_manifest.py", "source_probe.py"))
_REQUIRED_LABELS = frozenset(("STATIC SOURCE ONLY", "SYNTHETIC"))
_FORBIDDEN_LABELS = frozenset(("NATIVE RUNTIME", "GUEST ACCEPTED", "VERIFIED"))
_PR753_HEAD = "616ce171a7b71f69f19060122f53c97ada346662"
_PR753_BASE = "ec910d7a7275296ecbc8b5e5c459d356205165d1"
_SOURCE_HASH_PINS = {
    "capability_manifest.py": "91ca6a8bd677c7a584b6c89ada7bb737b5c3a8bbe9da7b1c4cba21344df4d983",
    "source_probe.py": "66685a317e745cddaf33f7c6d92b7d4fe195bc83716b43c55683ac292d981ade",
}

MAX_FIELDS = 24
MAX_CARDS = 5
MAX_STRING_CHARS = 240
MAX_LIST_ITEMS = 8
MAX_TOTAL_CHARS = 8192

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_UNSAFE_UNICODE = frozenset(("Cs", "Co", "Cn", "Zl", "Zp"))
_URI = re.compile(r"^(?:[A-Za-z][A-Za-z0-9+.-]*://|(?:file|data|javascript|mailto):)", re.I)
_TRAVERSAL = re.compile(r"(?:^|[\\/])\.\.(?:[\\/]|$)")
_ABSOLUTE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|/)")
_EXECUTABLE = re.compile(
    r"(?:`|\$\(|&&|\|\||\b(?:sudo|rm|curl|wget|chmod|chown|mkfs|nc|ncat)\b|"
    r"\b(?:subprocess|os\.system|os\.popen|eval|exec)\b)", re.I)
_HEX40 = re.compile(r"[0-9a-f]{40}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[a-z][a-z0-9_-]{2,48}\Z")


def _fail(code: str) -> None:
    raise SoftwareCenterError(code)


def _mapping(value: Any, code: str) -> Mapping:
    if not isinstance(value, Mapping):
        _fail(code)
    return value


def _fields(value: Mapping, expected: frozenset, code: str) -> None:
    try:
        actual = set(value)
    except TypeError:
        _fail(code)
    if actual != expected:
        _fail(code)


def _text(value: Any, code: str, max_chars: int = MAX_STRING_CHARS,
          *, allow_empty: bool = False) -> str:
    if type(value) is not str:
        _fail(code)
    if not value and not allow_empty:
        _fail(code)
    if len(value) > max_chars:
        _fail(code)
    if _CONTROL.search(value):
        _fail(code)
    if any(unicodedata.category(ch) in _UNSAFE_UNICODE for ch in value):
        _fail(code)
    if _URI.match(value) or _TRAVERSAL.search(value) or _ABSOLUTE.match(value):
        _fail(code)
    if _EXECUTABLE.search(value):
        _fail(code)
    return value


def _ordered(value: Any, code: str, max_items: int = MAX_LIST_ITEMS) -> Tuple[Any, ...]:
    # Unordered containers can never satisfy an ordered snapshot promise.
    if isinstance(value, (set, frozenset)) or hasattr(value, "isdisjoint"):
        _fail("UNORDERED_CONTAINER")
    if not isinstance(value, (list, tuple)) or isinstance(value, (str, bytes)):
        _fail(code)
    if not value or len(value) > max_items:
        _fail(code)
    return tuple(value)


def _flag(mapping_value: Mapping, key: str, expected: bool, code: str) -> None:
    value = mapping_value.get(key)
    if type(value) is not bool or value is not expected:
        _fail(code)


def _hex_text(value: Any, pattern: re.Pattern, code: str) -> str:
    if type(value) is not str or not pattern.fullmatch(value):
        _fail(code)
    return value


@dataclass(frozen=True)
class EcosystemCard:
    """One immutable, declaration-only Software Center card."""

    id: str
    label: str
    status: str
    capabilities: Tuple[str, ...]
    source_ids: Tuple[str, ...]
    provenance: Tuple[str, ...]
    signature_schemes: Tuple[str, ...]
    signature_status: str
    isolation: str
    core_mutation: str
    probe_status: str
    guest_acceptance: str


@dataclass(frozen=True)
class SoftwareCenterView:
    """Immutable, declaration-only view of the five P0 ecosystems."""

    status: str
    source_pr: int
    source_head_sha: str
    source_base_sha: str
    consumption: str
    source_sha256: Mapping[str, str]
    policy: Mapping[str, bool]
    cards: Tuple[EcosystemCard, ...]
    evidence_labels: Tuple[str, ...]
    guest_acceptance: str
    runtime: str

    @property
    def ok(self) -> bool:
        return self.status == "DECLARED_ONLY"


def _validate_source(raw: Any) -> tuple:
    source = _mapping(raw, "SOURCE_FIELDS_INVALID")
    _fields(source, _SOURCE_FIELDS, "SOURCE_FIELDS_INVALID")
    if type(source.get("pr")) is not int or source["pr"] != 753:
        _fail("SOURCE_PR_INVALID")
    head = _hex_text(source.get("head_sha"), _HEX40, "SOURCE_HEAD_SHA_INVALID")
    if head != _PR753_HEAD:
        _fail("SOURCE_HEAD_SHA_INVALID")
    base = _hex_text(source.get("base_sha"), _HEX40, "SOURCE_BASE_SHA_INVALID")
    if base != _PR753_BASE:
        _fail("SOURCE_BASE_SHA_INVALID")
    if source.get("consumption") != "read-only":
        _fail("SOURCE_CONSUMPTION_INVALID")
    hashes = _mapping(source.get("sha256"), "SOURCE_SHA256_INVALID")
    _fields(hashes, _SOURCE_HASH_FIELDS, "SOURCE_SHA256_INVALID")
    pins = {}
    for name in sorted(_SOURCE_HASH_FIELDS):
        if _hex_text(hashes[name], _HEX64, "SOURCE_SHA256_INVALID") != _SOURCE_HASH_PINS[name]:
            _fail("SOURCE_SHA256_INVALID")
        pins[name] = hashes[name]
    return source["pr"], head, base, "read-only", MappingProxyType(pins)


def _validate_policy(raw: Any) -> Mapping[str, bool]:
    policy = _mapping(raw, "POLICY_FIELDS_INVALID")
    _fields(policy, _POLICY_FIELDS, "POLICY_FIELDS_INVALID")
    _flag(policy, "no_core_mutation", True, "POLICY_NO_CORE_MUTATION_REQUIRED")
    _flag(policy, "foreign_host_repo_mixing", False, "POLICY_FOREIGN_REPO_MIXING_REQUIRED")
    _flag(policy, "paid_tiers", False, "POLICY_PAID_TIERS_REQUIRED")
    _flag(policy, "telemetry", False, "POLICY_TELEMETRY_REQUIRED")
    _flag(policy, "duplicate_always_on_services", False, "POLICY_DUPLICATE_SERVICES_REQUIRED")
    _flag(policy, "accounts", False, "POLICY_ACCOUNTS_REQUIRED")
    return MappingProxyType({key: policy[key] for key in sorted(_POLICY_FIELDS)})


def _validate_card(raw: Any, expected_id: str) -> EcosystemCard:
    card = _mapping(raw, "ECOSYSTEM_FIELDS_INVALID")
    _fields(card, _CARD_FIELDS, "ECOSYSTEM_FIELDS_INVALID")
    if type(card.get("id")) is not str or card["id"] != expected_id:
        _fail("ECOSYSTEM_ID_INVALID")
    spec = _ECOSYSTEM_SPEC[expected_id]
    label = _text(card.get("label"), "ECOSYSTEM_LABEL_INVALID")
    if label != spec["label"]:
        _fail("ECOSYSTEM_LABEL_INVALID")
    if card.get("status") != "DECLARED":
        _fail("ECOSYSTEM_STATUS_INVALID")

    capabilities = _ordered(card.get("capabilities"), "CAPABILITIES_INVALID")
    if any(type(item) is not str for item in capabilities):
        _fail("CAPABILITIES_INVALID")
    if len(set(capabilities)) != len(capabilities):
        _fail("CAPABILITIES_INVALID")
    if set(capabilities) & FORBIDDEN_CAPABILITIES:
        _fail("CAPABILITY_FORBIDDEN")
    if set(capabilities) - spec["capabilities"]:
        _fail("CAPABILITY_UNKNOWN")

    source_ids = _ordered(card.get("source_ids"), "SOURCE_IDS_INVALID")
    if any(type(item) is not str or not _ID.fullmatch(item) for item in source_ids):
        _fail("SOURCE_IDS_INVALID")
    if len(set(source_ids)) != len(source_ids):
        _fail("SOURCE_IDS_INVALID")

    provenance = _ordered(card.get("provenance"), "PROVENANCE_INVALID")
    if (any(type(item) is not str for item in provenance)
            or not set(provenance) <= spec["provenance"]
            or len(set(provenance)) != len(provenance)):
        _fail("PROVENANCE_INVALID")

    signatures = _ordered(card.get("signature_schemes"), "SIGNATURE_INVALID")
    if (any(type(item) is not str for item in signatures)
            or not set(signatures) <= spec["signatures"]
            or len(set(signatures)) != len(signatures)):
        _fail("SIGNATURE_INVALID")

    if card.get("signature_status") != "DECLARED_NOT_VERIFIED":
        _fail("SIGNATURE_STATUS_INVALID")
    if _text(card.get("isolation"), "ISOLATION_INVALID") != spec["isolation"]:
        _fail("ISOLATION_INVALID")
    if card.get("core_mutation") != "ABSENT_DECLARED":
        _fail("CORE_MUTATION_INVALID")
    if card.get("probe_status") != "NOT_RUN":
        _fail("PROBE_STATUS_INVALID")
    if card.get("guest_acceptance") != "NOT_RUN":
        _fail("GUEST_ACCEPTANCE_INVALID")

    return EcosystemCard(
        id=expected_id,
        label=label,
        status="DECLARED",
        capabilities=tuple(sorted(capabilities)),
        source_ids=source_ids,
        provenance=tuple(sorted(provenance)),
        signature_schemes=tuple(sorted(signatures)),
        signature_status="DECLARED_NOT_VERIFIED",
        isolation=spec["isolation"],
        core_mutation="ABSENT_DECLARED",
        probe_status="NOT_RUN",
        guest_acceptance="NOT_RUN",
    )


def build_center_view(snapshot: Any) -> SoftwareCenterView:
    """Validate a snapshot and return an immutable declaration-only view.

    Fails closed with :class:`SoftwareCenterError` on wrong types, unexpected
    fields, unordered containers, oversized input, missing or unknown
    ecosystems, forbidden capabilities, any paid/account/telemetry/duplicate
    service claim, a core-mutation claim, or any real-runtime acceptance claim.
    """
    outer = _mapping(snapshot, "TOP_NOT_MAPPING")
    _fields(outer, _TOP_FIELDS, "TOP_FIELDS_INVALID")
    budget = [0]

    def scan(value: Any, depth: int) -> None:
        if isinstance(value, (set, frozenset)) or hasattr(value, "isdisjoint"):
            _fail("UNORDERED_CONTAINER")
        if depth > 6:
            _fail("TOP_UNSAFE_FIELD")
        if isinstance(value, Mapping):
            if len(value) > MAX_FIELDS:
                _fail("TOP_UNSAFE_FIELD")
            for key, child in value.items():
                if type(key) is not str or _EXECUTABLE.search(key):
                    _fail("TOP_UNSAFE_FIELD")
                scan(child, depth + 1)
            return
        if isinstance(value, (list, tuple)):
            if len(value) > MAX_LIST_ITEMS:
                _fail("TOP_UNSAFE_FIELD")
            for child in value:
                scan(child, depth + 1)
            return
        if type(value) is str:
            budget[0] += len(value)
            if len(value) > MAX_STRING_CHARS or budget[0] > MAX_TOTAL_CHARS:
                _fail("TOP_UNSAFE_FIELD")
            _text(value, "TOP_UNSAFE_FIELD")
            return
        if type(value) is bool or value is None:
            return
        if type(value) is int and abs(value).bit_length() <= 32:
            return
        _fail("TOP_UNSAFE_FIELD")

    scan(outer, 0)
    if outer.get("schema_version") != 1 or type(outer.get("schema_version")) is not int:
        _fail("SCHEMA_VERSION_INVALID")

    pr, head, base, consumption, hashes = _validate_source(outer.get("source"))
    policy = _validate_policy(outer.get("policy"))

    raw_cards = outer.get("ecosystems")
    if isinstance(raw_cards, (set, frozenset)) or hasattr(raw_cards, "isdisjoint"):
        _fail("UNORDERED_CONTAINER")
    if not isinstance(raw_cards, (list, tuple)) or len(raw_cards) != MAX_CARDS:
        _fail("ECOSYSTEM_SET_INVALID")
    cards = tuple(
        _validate_card(raw_cards[index], name)
        for index, name in enumerate(ECOSYSTEM_IDS))
    if tuple(card.id for card in cards) != ECOSYSTEM_IDS:
        _fail("ECOSYSTEM_SET_INVALID")

    labels = _ordered(outer.get("evidence_labels"), "EVIDENCE_LABELS_INVALID")
    if (any(type(item) is not str for item in labels)
            or not _REQUIRED_LABELS <= set(labels)
            or set(labels) & _FORBIDDEN_LABELS):
        _fail("EVIDENCE_LABELS_INVALID")
    if outer.get("guest_acceptance") != "NOT_RUN":
        _fail("GUEST_ACCEPTANCE_INVALID")
    if outer.get("runtime") != "BLOCKED_NOT_RUN":
        _fail("RUNTIME_INVALID")
    if any(card.guest_acceptance != "NOT_RUN" or card.probe_status != "NOT_RUN"
           for card in cards):
        _fail("GUEST_ACCEPTANCE_INVALID")

    return SoftwareCenterView(
        status="DECLARED_ONLY",
        source_pr=pr,
        source_head_sha=head,
        source_base_sha=base,
        consumption=consumption,
        source_sha256=hashes,
        policy=policy,
        cards=cards,
        evidence_labels=tuple(sorted(set(labels))),
        guest_acceptance="NOT_RUN",
        runtime="BLOCKED_NOT_RUN",
    )


def view_dict(view: SoftwareCenterView) -> dict:
    """Return a JSON-serialisable, deterministic projection of a view."""
    if not isinstance(view, SoftwareCenterView):
        _fail("VIEW_TYPE_INVALID")
    return {
        "status": view.status,
        "source": {
            "pr": view.source_pr,
            "head_sha": view.source_head_sha,
            "base_sha": view.source_base_sha,
            "consumption": view.consumption,
            "sha256": dict(view.source_sha256),
        },
        "policy": dict(view.policy),
        "ecosystems": [
            {
                "id": card.id,
                "label": card.label,
                "status": card.status,
                "capabilities": list(card.capabilities),
                "source_ids": list(card.source_ids),
                "provenance": list(card.provenance),
                "signature_schemes": list(card.signature_schemes),
                "signature_status": card.signature_status,
                "isolation": card.isolation,
                "core_mutation": card.core_mutation,
                "probe_status": card.probe_status,
                "guest_acceptance": card.guest_acceptance,
            }
            for card in view.cards
        ],
        "evidence_labels": list(view.evidence_labels),
        "guest_acceptance": view.guest_acceptance,
        "runtime": view.runtime,
    }


def presentation_lines(view: SoftwareCenterView) -> Tuple[str, ...]:
    """Return bounded human-readable lines; no host state, no runtime claim."""
    if not isinstance(view, SoftwareCenterView):
        _fail("VIEW_TYPE_INVALID")
    lines = [
        f"SOFTWARE_CENTER: status={view.status} runtime={view.runtime} "
        f"guest_acceptance={view.guest_acceptance}",
        f"SOURCE: pr={view.source_pr} head={view.source_head_sha} "
        f"consumption={view.consumption}",
        "POLICY: no_core_mutation=true paid_tiers=false accounts=false "
        "telemetry=false duplicate_always_on_services=false "
        "foreign_host_repo_mixing=false",
    ]
    for card in view.cards:
        lines.append(
            f"CARD\t{card.id}\t{card.label}\tstatus={card.status}\t"
            f"provenance={','.join(card.provenance)}\t"
            f"signature={','.join(card.signature_schemes)} "
            f"({card.signature_status})\t"
            f"core_mutation={card.core_mutation}\tprobe={card.probe_status}")
        lines.append(f"ISOLATION\t{card.id}\t{card.isolation}")
    return tuple(lines)
