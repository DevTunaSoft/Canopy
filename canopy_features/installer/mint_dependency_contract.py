"""Offline installer check of installed packages against Canopy's constraints.

The caller supplies the installed package versions and the target Linux Mint
release. This module performs a pure, bounded evaluation: it never queries the
host, runs a process, uses the network, polls, or needs privileges. Recognizing
a release here is a policy lookup, not evidence that a real Mint guest or the
compiled Qt prototype was tested.
"""

from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Tuple


# Stable releases this contract knows how to evaluate. Adding a release is an
# explicit installer-policy change, not an automatic discovery.
STABLE_MINT_RELEASES = frozenset(("21.3", "22", "22.3"))

# Minimums come from the Classic Qt build contract: cmake_minimum_required
# (VERSION 3.21) and find_package(Qt6 6.4 REQUIRED) in prototype/classic.
# Package names identify the constraint, not a verified distro package map.
CANOPY_CONSTRAINTS = (
    ("cmake", "3.21"),
    ("qt6-core", "6.4"),
    ("qt6-declarative", "6.4"),
)

# This module iterates only its own bounded constraint list, never the whole
# installed mapping, so a large caller-supplied mapping cannot grow its work.
MAX_CONSTRAINTS = 64


@dataclass(frozen=True)
class Finding:
    """One package's evaluation result. Contains no host paths or secrets."""

    package: str
    status: str  # ok | below_minimum | not_installed | invalid_version | invalid_constraint
    installed: Optional[str]
    required: str
    detail: str


@dataclass(frozen=True)
class ContractReport:
    """Result of one evaluation. Immutable so callers cannot rewrite evidence."""

    mint_version: str
    stable_release: bool
    status: str  # SATISFIED | UNSATISFIED | UNSUPPORTED_RELEASE
    findings: Tuple[Finding, ...]
    detail: str

    @property
    def ok(self) -> bool:
        return self.status == "SATISFIED"


def parse_version(text) -> Optional[Tuple[int, ...]]:
    """Parse a dotted numeric prefix into a comparable tuple, else None.

    Packaging suffixes such as '6.4.2-0ubuntu1' are ignored after the numeric
    prefix. Malformed or empty values fail closed as None.
    """
    if not isinstance(text, str) or not text:
        return None
    head = text.split("-", 1)[0].split("+", 1)[0]
    parts = head.split(".")
    if not parts or any(not part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def _compare(left: Tuple[int, ...], right: Tuple[int, ...]) -> int:
    """Compare versions with zero padding: 6.4 == 6.4.0, 6.10 > 6.9."""
    width = max(len(left), len(right))
    a = left + (0,) * (width - len(left))
    b = right + (0,) * (width - len(right))
    return (a > b) - (a < b)


def evaluate(installed: Mapping[str, str], mint_version: str,
             constraints: Iterable[Tuple[str, str]] = CANOPY_CONSTRAINTS
             ) -> ContractReport:
    """Check installed versions against constraints for a stable Mint release.

    `installed` maps a constraint name to its installed version string. Extra
    installed packages are ignored. Unknown releases return a fail-closed
    UNSUPPORTED_RELEASE report without inspecting any package data.
    """
    if not isinstance(mint_version, str) or mint_version not in STABLE_MINT_RELEASES:
        return ContractReport(
            mint_version=mint_version if isinstance(mint_version, str) else "",
            stable_release=False,
            status="UNSUPPORTED_RELEASE",
            findings=(),
            detail="target Mint release is not a recognized stable release",
        )

    findings = []
    for name, minimum_text in tuple(constraints)[:MAX_CONSTRAINTS]:
        minimum = parse_version(minimum_text)
        if minimum is None:
            findings.append(Finding(name, "invalid_constraint", None,
                                    str(minimum_text), "declared minimum is not a version"))
            continue
        installed_text = installed.get(name)
        if installed_text is None:
            findings.append(Finding(name, "not_installed", None,
                                    minimum_text, "package is absent from installed set"))
            continue
        actual = parse_version(installed_text)
        if actual is None:
            findings.append(Finding(name, "invalid_version", installed_text,
                                    minimum_text, "installed version is not a dotted number"))
            continue
        if _compare(actual, minimum) < 0:
            findings.append(Finding(name, "below_minimum", installed_text,
                                    minimum_text, "installed version is below required minimum"))
            continue
        findings.append(Finding(name, "ok", installed_text, minimum_text,
                                "installed version meets minimum"))

    ok = bool(findings) and all(item.status == "ok" for item in findings)
    return ContractReport(
        mint_version=mint_version,
        stable_release=True,
        status="SATISFIED" if ok else "UNSATISFIED",
        findings=tuple(findings),
        detail="all constraints satisfied" if ok else "one or more constraints unsatisfied",
    )
