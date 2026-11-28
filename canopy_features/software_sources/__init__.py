"""Bounded, read-only LacOS P0 software-source policy helpers.

This package never installs software, changes a package database, touches the
booted core, starts a background service or uses the network. It evaluates
declarations and probe facts supplied by a caller; a green result is a policy
decision, not proof that a real guest accepted an application.
"""

from .capability_manifest import (
    CAPABILITIES_BY_ECOSYSTEM,
    ECOSYSTEMS,
    ECOSYSTEM_IDS,
    FORBIDDEN_CAPABILITIES,
    ManifestReport,
    ecosystem_decision,
    evaluate_manifest,
)
from .source_probe import (
    ProbeDecision,
    ProbeReport,
    collect_host_facts,
    evaluate_probe,
)

__all__ = (
    "CAPABILITIES_BY_ECOSYSTEM",
    "ECOSYSTEMS",
    "ECOSYSTEM_IDS",
    "FORBIDDEN_CAPABILITIES",
    "ManifestReport",
    "ProbeDecision",
    "ProbeReport",
    "collect_host_facts",
    "ecosystem_decision",
    "evaluate_manifest",
    "evaluate_probe",
)
