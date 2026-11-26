"""One immutable, no-echo application launch preview for a trusted host.

Pure data only: this composes the already-tested
``launcher_intent_summary.summarize_launcher_intent`` and
``apps.launch_policy_snapshot.compose_launch_policy_snapshot`` into one bounded
preview record. It never starts a process, opens a shell, walks files, polls or
touches a desktop.

The record carries counts and fixed negative claims only. No selected app id,
title, environment name/value or argv token is copied into it or its ``to_dict``
bridge, so untrusted strings cannot reach a host UI or log through this
preview. The two source decisions must agree on argv shape before READY is
returned; every other outcome is a terse denial with no source material.
"""
from dataclasses import dataclass
from typing import Tuple

from canopy_features.apps.launch_policy_snapshot import (
    STATUS_APPROVED as POLICY_APPROVED,
    compose_launch_policy_snapshot,
)
from canopy_features.apps.launch_argv import DESKTOP_ID, SHELL_METACHARACTERS
from canopy_features.catalog.missing_app_availability import AppAvailability
from canopy_features.launcher.launcher_intent_summary import (
    STATUS_NOT_APPROVED as INTENT_NOT_APPROVED,
    STATUS_NO_MATCH as INTENT_NO_MATCH,
    STATUS_READY as INTENT_READY,
    summarize_launcher_intent,
)

STATUS_READY = "READY"
STATUS_NO_MATCH = "NO_MATCH"
STATUS_NOT_APPROVED = "NOT_APPROVED"
STATUS_DENIED = "DENIED"

REASON_OK = "ok"
REASON_APP_UNAVAILABLE = "app_unavailable"
REASON_NO_MATCH = "no_match"
REASON_NOT_APPROVED = "not_approved"
REASON_POLICY_DENIED = "policy_denied"
REASON_AGREEMENT_MISMATCH = "agreement_mismatch"
REASON_INVALID_INPUT = "invalid_input"

CLAIM_NO_PROCESS_LAUNCHED = "no_process_launched"
CLAIM_NO_VALUE_ECHO = "no_value_echo"
CLAIM_NO_SHELL_METACHARACTERS = "no_shell_metacharacters"
CLAIM_NO_UNALLOWED_ENV = "no_unallowed_env"
CLAIM_NO_SOURCE_DISAGREEMENT = "no_source_disagreement"
CLAIM_NO_DESKTOP_CLAIM = "no_desktop_claim"

FIXED_CLAIMS = (
    CLAIM_NO_DESKTOP_CLAIM,
    CLAIM_NO_PROCESS_LAUNCHED,
    CLAIM_NO_SHELL_METACHARACTERS,
    CLAIM_NO_SOURCE_DISAGREEMENT,
    CLAIM_NO_UNALLOWED_ENV,
    CLAIM_NO_VALUE_ECHO,
)

__all__ = [
    "CLAIM_NO_DESKTOP_CLAIM",
    "CLAIM_NO_PROCESS_LAUNCHED",
    "CLAIM_NO_SHELL_METACHARACTERS",
    "CLAIM_NO_SOURCE_DISAGREEMENT",
    "CLAIM_NO_UNALLOWED_ENV",
    "CLAIM_NO_VALUE_ECHO",
    "FIXED_CLAIMS",
    "REASON_AGREEMENT_MISMATCH",
    "REASON_APP_UNAVAILABLE",
    "REASON_INVALID_INPUT",
    "REASON_NOT_APPROVED",
    "REASON_NO_MATCH",
    "REASON_OK",
    "REASON_POLICY_DENIED",
    "STATUS_DENIED",
    "STATUS_NOT_APPROVED",
    "STATUS_NO_MATCH",
    "STATUS_READY",
    "AppLaunchPreview",
    "compose_app_launch_preview",
]


@dataclass(frozen=True)
class AppLaunchPreview:
    """One bounded host preview; denials carry no source material.

    ``claims`` is the fixed tuple of negative claims only on a READY preview.
    Every count is a number, never a copied value.
    """

    status: str
    reason: str
    match_count: int = 0
    favorite_count: int = 0
    env_count: int = 0
    argv_length: int = 0
    claims: Tuple[str, ...] = ()

    @property
    def ready(self):
        return self.status == STATUS_READY

    def to_dict(self):
        """Plain bounded mapping for a host bridge or evidence log."""
        return {
            "status": self.status,
            "reason": self.reason,
            "match_count": self.match_count,
            "favorite_count": self.favorite_count,
            "env_count": self.env_count,
            "argv_length": self.argv_length,
            "claims": list(self.claims),
        }


def _deny(status, reason):
    return AppLaunchPreview(status, reason)


def _argv_agrees(intent, policy):
    """Check both sources describe the same shell-free GIO argv without echoing."""
    argv = intent.argv
    if type(argv) is not tuple or len(argv) < 4:
        return False
    if len(argv) != policy.argv_length:
        return False
    app_id = intent.selected_app_id
    if type(app_id) is not str or DESKTOP_ID.fullmatch(app_id) is None:
        return False
    # Matching lengths alone are not agreement: a wrong-shaped but same-length
    # argv would let a false no_source_disagreement claim reach a READY record.
    # Require the exact GIO prefix for the same selected app id the policy used.
    if argv[:4] != ("gio", "launch", "--", app_id):
        return False
    return all(
        type(token) is str
        and not any(char in SHELL_METACHARACTERS for char in token)
        for token in argv
    )


def compose_app_launch_preview(
    query, catalog, *, favorites=(), allowed_app_ids=None,
    env_allow=(), env_source=None, availability=None,
):
    """Compose one no-echo launch preview from the two tested decisions.

    ``query``/``catalog``/``favorites``/``allowed_app_ids`` feed the launcher
    intent summary; ``env_allow``/``env_source`` and the selected app id feed
    the launch policy snapshot. Neither source value is copied into the result.
    When supplied, ``availability`` must be an ``AppAvailability`` record whose
    ``launch_permitted`` flag allows the launch; a missing application can
    never produce a READY preview or a phantom launch intent.
    """
    # A caller may hand in a bounded but hostile lazy iterable whose read
    # raises an arbitrary built-in mid-consumption. This is the composition
    # boundary: translate any source failure to the module's own denial rather
    # than leak a raw exception to the host. BaseException (interrupt/exit) is
    # deliberately not swallowed.
    try:
        intent = summarize_launcher_intent(
            query, catalog, favorites=favorites,
            allowed_app_ids=allowed_app_ids)
    except Exception:
        return _deny(STATUS_DENIED, REASON_INVALID_INPUT)

    if intent.status == INTENT_NO_MATCH:
        return _deny(STATUS_NO_MATCH, REASON_NO_MATCH)
    if intent.status == INTENT_NOT_APPROVED:
        return _deny(STATUS_NOT_APPROVED, REASON_NOT_APPROVED)
    if intent.status != INTENT_READY:
        return _deny(STATUS_DENIED, REASON_INVALID_INPUT)

    try:
        policy = compose_launch_policy_snapshot(
            env_allow,
            {} if env_source is None else env_source,
            intent.selected_app_id,
            allowed_app_ids=allowed_app_ids,
        )
    except Exception:
        return _deny(STATUS_DENIED, REASON_INVALID_INPUT)
    if policy.status != POLICY_APPROVED:
        return _deny(STATUS_DENIED, REASON_POLICY_DENIED)

    if not _argv_agrees(intent, policy):
        return _deny(STATUS_DENIED, REASON_AGREEMENT_MISMATCH)

    if availability is not None:
        if not isinstance(availability, AppAvailability):
            return _deny(STATUS_DENIED, REASON_INVALID_INPUT)
        if not availability.launch_permitted:
            return _deny(STATUS_DENIED, REASON_APP_UNAVAILABLE)

    return AppLaunchPreview(
        status=STATUS_READY,
        reason=REASON_OK,
        match_count=len(intent.matches),
        favorite_count=len(intent.favorites),
        env_count=policy.env_count,
        argv_length=policy.argv_length,
        claims=FIXED_CLAIMS,
    )
