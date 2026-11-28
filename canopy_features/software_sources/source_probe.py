"""Read-only host/guest probe facts for the five LacOS P0 software ecosystems.

Host collection uses only a bounded tool-presence lookup. It never runs a
package manager, opens a repository configuration, writes a file, opens a
socket or reports a trust decision. Guest facts must be supplied by a caller
running the same read-only collector inside a disposable guest; this task did
not execute that probe, so every guest-acceptance field stays NOT_RUN.

A synthetic guest fact set can exercise the evaluator, but its result is a
policy decision only: it never becomes a real installation or runtime grant.
"""

from collections.abc import Mapping
from dataclasses import dataclass
import shutil
from typing import Any, FrozenSet, Tuple

from .capability_manifest import ECOSYSTEMS, ECOSYSTEM_IDS, ManifestReport


# Read-only tool discovery only. No command is executed and no path is logged.
TOOL_COMMANDS = {
    "flatpak_flathub": "flatpak",
    "apt_deb": "apt",
    "pacman": "pacman",
    "dnf_rpm": "dnf",
    "rootless_podman_oci": "podman",
}

REQUIRED_FACT_KEYS = frozenset((
    "tool_present", "signature_verified", "source_verified",
    "environment_isolated", "core_mutation_absent", "foreign_repo_absent",
    "no_always_on_service", "privileged_absent",
))
FACT_RULES = (
    ("tool_present", "TOOL_MISSING"),
    ("signature_verified", "SIGNATURE_UNVERIFIED"),
    ("source_verified", "PROVENANCE_UNVERIFIED"),
    ("environment_isolated", "ENVIRONMENT_NOT_ISOLATED"),
    ("core_mutation_absent", "CORE_MUTATION_OBSERVED"),
    ("foreign_repo_absent", "FOREIGN_REPO_MIXED"),
    ("no_always_on_service", "ALWAYS_ON_SERVICE"),
    ("privileged_absent", "PRIVILEGED_DEFAULT"),
)


@dataclass(frozen=True)
class ProbeDecision:
    """One ecosystem's bounded probe evaluation; no execution approval."""

    ecosystem: str
    status: str  # NOT_RUN | HOST_ONLY | READY | BLOCKED | NOT_EVALUATED
    reasons: Tuple[str, ...]
    capabilities: FrozenSet[str]


@dataclass(frozen=True)
class ProbeReport:
    """Immutable result of one probe evaluation."""

    status: str  # VALID | INVALID | MANIFEST_INVALID
    context: str
    evidence_class: str
    guest_acceptance: str  # always NOT_RUN unless a real guest supplied facts
    decisions: Tuple[ProbeDecision, ...]
    grants: Mapping[str, Tuple[str, ...]]
    reasons: Tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.status == "VALID"


def _empty(reasons: Tuple[str, ...], context: str = "",
           evidence_class: str = "") -> ProbeReport:
    return ProbeReport(
        "INVALID", context, evidence_class, "NOT_RUN", tuple(
            ProbeDecision(name, "NOT_RUN", (), frozenset())
            for name in ECOSYSTEM_IDS),
        {}, reasons)


def collect_host_facts(context: str = "host") -> dict:
    """Return read-only, category-only probe facts for the five ecosystems.

    ``shutil.which`` is the only host interaction. The returned mapping holds
    booleans, not paths, and every verification field is False: binary
    presence is never evidence of signature verification, provenance,
    isolation or guest acceptance.
    """
    if context not in ("host", "guest"):
        raise ValueError("context must be host or guest")
    facts = {
        "schema_version": 1,
        "context": context,
        "evidence_class": "host-readonly" if context == "host" else "guest-readonly",
        "guest_executed": False,
        "ecosystems": {},
    }
    for name in ECOSYSTEM_IDS:
        facts["ecosystems"][name] = {
            "tool_present": shutil.which(TOOL_COMMANDS[name]) is not None,
            "signature_verified": False,
            "source_verified": False,
            "environment_isolated": False,
            "core_mutation_absent": False,
            "foreign_repo_absent": False,
            "no_always_on_service": False,
            "privileged_absent": False,
            "provenance": "",
        }
    return facts


def evaluate_probe(manifest: ManifestReport, facts: Mapping[str, Any]) -> ProbeReport:
    """Evaluate bounded guest/host facts against a validated manifest.

    Grants are only produced for context='guest'. A synthetic evidence class
    still reports ``guest_acceptance='NOT_RUN'``; it can demonstrate evaluator
    behaviour but is not operational trust or a real guest test.
    """
    if not isinstance(manifest, ManifestReport) or not manifest.ok:
        return _empty(("MANIFEST_INVALID",))
    if not isinstance(facts, Mapping):
        return _empty(("FACTS_NOT_MAPPING",))
    try:
        count = len(facts)
    except Exception:
        return _empty(("FACTS_UNSIZABLE",))
    if count > 16:
        return _empty(("FACTS_TOO_LARGE",))
    if facts.get("schema_version") != 1:
        return _empty(("FACTS_SCHEMA_INVALID",))
    context = facts.get("context")
    if context not in ("host", "guest"):
        return _empty(("FACTS_CONTEXT_INVALID",))
    # A caller cannot promote a probe to guest acceptance by declaring it so.
    # This contract has no channel for real guest evidence: it is always NOT_RUN.
    if facts.get("guest_executed") is not False:
        return _empty(("FACTS_GUEST_FLAG_INVALID",))
    evidence_class = facts.get("evidence_class")
    if evidence_class not in ("host-readonly", "guest-readonly", "synthetic"):
        return _empty(("FACTS_EVIDENCE_CLASS_INVALID",))
    guest_acceptance = "NOT_RUN"

    raw = facts.get("ecosystems")
    if (not isinstance(raw, Mapping)
            or set(raw) != set(ECOSYSTEM_IDS)):
        return ProbeReport(
            "INVALID", context, evidence_class, guest_acceptance, tuple(
                ProbeDecision(name, "NOT_RUN", ("ECOSYSTEM_SET_INVALID",),
                              frozenset()) for name in ECOSYSTEM_IDS),
            {}, ("ECOSYSTEM_SET_INVALID",))

    decisions = []
    grants = {}
    top_reasons = []
    for declared in manifest.decisions:
        name = declared.ecosystem
        if declared.status != "DECLARED":
            decisions.append(ProbeDecision(
                name, "NOT_EVALUATED", ("MANIFEST_NOT_DECLARED",), frozenset()))
            continue
        item = raw[name]
        if not isinstance(item, Mapping) or set(item) != REQUIRED_FACT_KEYS | {"provenance"}:
            decisions.append(ProbeDecision(
                name, "BLOCKED", ("FACT_FIELDS_INVALID",), frozenset()))
            top_reasons.append(f"{name}:FACT_FIELDS_INVALID")
            continue
        if context == "host":
            # Binary presence is a hint only. Host facts carry no signature or
            # provenance evidence, so never evaluate them as a trust decision.
            decisions.append(ProbeDecision(
                name, "HOST_ONLY", ("GUEST_EVIDENCE_REQUIRED",), frozenset()))
            continue
        provenance = item.get("provenance")
        if type(provenance) is not str or provenance not in ECOSYSTEMS[name]["provenance"]:
            decisions.append(ProbeDecision(
                name, "BLOCKED", ("PROVENANCE_UNKNOWN",), frozenset()))
            top_reasons.append(f"{name}:PROVENANCE_UNKNOWN")
            continue
        # privileged_absent is required for every ecosystem; it is what keeps
        # rootless Podman from receiving a privileged-default grant.
        bad = [code for key, code in FACT_RULES if item.get(key) is not True]
        if bad:
            decisions.append(ProbeDecision(
                name, "BLOCKED", tuple(bad), frozenset()))
            top_reasons.extend(f"{name}:{code}" for code in bad)
            continue
        granted = frozenset(sorted(declared.capabilities))
        decisions.append(ProbeDecision(name, "READY", (), granted))
        grants[name] = tuple(sorted(granted))

    status = "VALID" if not top_reasons else "INVALID"
    return ProbeReport(
        status, context, evidence_class, guest_acceptance, tuple(decisions),
        grants, tuple(top_reasons))
