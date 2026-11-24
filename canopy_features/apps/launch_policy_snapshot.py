"""One immutable, fail-closed launch policy snapshot for a trusted host.

Pure data only: this module composes the already-tested
``environment_allowlist.build_environment`` and
``launch_argv.gio_launch_argv`` into a single host-facing decision record. It
never starts a process, opens a shell, reads files, polls or touches a desktop.

The record deliberately carries **counts and fixed negative claims only**. No
environment name or value, no argv token and no application id is echoed back,
so an untrusted caller string cannot reach a log, a QML bridge or a host UI
through this snapshot. Every denial is equally terse: a stable reason code and
zero counts, with no source material. A host still owns the allowlists and the
actual process launch; this module only proves the policy decision is bounded
and shell-free.
"""
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Optional, Tuple

from canopy_features.apps.environment_allowlist import (
    EnvironmentAllowlistError,
    build_environment,
)
from canopy_features.apps.launch_argv import (
    SHELL_METACHARACTERS,
    LaunchArgvError,
    gio_launch_argv,
)

STATUS_APPROVED = "APPROVED"
STATUS_DENIED = "DENIED"

REASON_OK = "ok"
REASON_ENV_REJECTED = "env_rejected"
REASON_ARGV_REJECTED = "argv_rejected"
REASON_SOURCE_DISAGREEMENT = "source_disagreement"

# Fixed negative claims. These are assertions about what did NOT happen; they
# never contain caller data.
CLAIM_ENV_ALLOWLIST_ONLY = "env_allowlist_only"
CLAIM_ENV_NO_CREDENTIAL_NAMES = "env_no_credential_names"
CLAIM_ENV_NO_NUL_VALUES = "env_no_nul_values"
CLAIM_ARGV_SHELL_FREE = "argv_shell_free"
CLAIM_ARGV_HOST_APPROVED = "argv_host_approved"
CLAIM_NO_PROCESS_LAUNCHED = "no_process_launched"
FIXED_CLAIMS = (
    CLAIM_ARGV_HOST_APPROVED,
    CLAIM_ARGV_SHELL_FREE,
    CLAIM_ENV_ALLOWLIST_ONLY,
    CLAIM_ENV_NO_CREDENTIAL_NAMES,
    CLAIM_ENV_NO_NUL_VALUES,
    CLAIM_NO_PROCESS_LAUNCHED,
)

__all__ = [
    "CLAIM_ARGV_HOST_APPROVED",
    "CLAIM_ARGV_SHELL_FREE",
    "CLAIM_ENV_ALLOWLIST_ONLY",
    "CLAIM_ENV_NO_CREDENTIAL_NAMES",
    "CLAIM_ENV_NO_NUL_VALUES",
    "CLAIM_NO_PROCESS_LAUNCHED",
    "FIXED_CLAIMS",
    "REASON_ARGV_REJECTED",
    "REASON_ENV_REJECTED",
    "REASON_OK",
    "REASON_SOURCE_DISAGREEMENT",
    "STATUS_APPROVED",
    "STATUS_DENIED",
    "LaunchPolicySnapshot",
    "SnapshotInputError",
    "compose_launch_policy_snapshot",
]


class SnapshotInputError(ValueError):
    """Caller passed a source mapping or app id of the wrong type."""


@dataclass(frozen=True)
class LaunchPolicySnapshot:
    """One bounded host decision; denials carry no source material.

    ``claims`` is the fixed tuple of negative claims on an approved record and
    empty on a denial. ``env_count`` and ``argv_length`` are counts, never
    copied values.
    """

    status: str
    reason: str
    env_count: int = 0
    argv_length: int = 0
    claims: Tuple[str, ...] = ()

    @property
    def approved(self):
        return self.status == STATUS_APPROVED

    def to_dict(self):
        """Plain bounded mapping for a host bridge or evidence log."""
        return {
            "status": self.status,
            "reason": self.reason,
            "env_count": self.env_count,
            "argv_length": self.argv_length,
            "claims": list(self.claims),
        }


def _read_labels(values):
    """Materialize a caller-supplied label iterable, or return ``None``.

    Reading a lazy or hostile iterable can fail with any built-in exception,
    not just ``TypeError``/``ValueError``. The caller has no way to prove the
    labels it did read were the complete set, so a failed read is unusable.
    """
    try:
        return tuple(values)
    except Exception:
        return None


def _deny(reason):
    return LaunchPolicySnapshot(STATUS_DENIED, reason)


def _env_agrees(env, allow_names):
    """Verify the tested builder's output without echoing any of it."""
    allowed = frozenset(name for name in allow_names if type(name) is str)
    return (type(env) is dict
            and all(type(key) is str and key in allowed for key in env)
            and all(type(value) is str and "\x00" not in value
                    for value in env.values()))


def _argv_agrees(argv, app_id):
    """Verify the tested argv builder emitted the expected GIO shape."""
    if type(argv) is not tuple or len(argv) < 4:
        return False
    if argv[:4] != ("gio", "launch", "--", app_id):
        return False
    return all(
        type(token) is str
        and not any(char in SHELL_METACHARACTERS for char in token)
        for token in argv
    )


def compose_launch_policy_snapshot(
    allow, source, app_id, arguments=(), *, allowed_app_ids=None,
):
    """Compose one no-echo launch policy decision; launch nothing.

    ``allow`` and ``source`` feed ``build_environment``; ``app_id``,
    ``arguments`` and ``allowed_app_ids`` feed ``gio_launch_argv``. Malformed
    inputs from either tested module deny with a fixed reason. Disagreement
    between the two outputs denies with ``source_disagreement``. No caller
    value is copied into the returned record.
    """
    if not isinstance(source, Mapping):
        raise SnapshotInputError("source must be a mapping")
    if type(app_id) is not str:
        raise SnapshotInputError("app_id must be a string")

    # Hostile-but-bounded label iterables must fail closed, never leak the
    # built-in exception raised partway through a read to a host bridge. The
    # sibling tested builders normalize once for the same reason.
    allow_names = _read_labels(allow)
    if allow_names is None:
        return _deny(REASON_ENV_REJECTED)

    try:
        env = build_environment(allow_names, source)
    except (EnvironmentAllowlistError, TypeError, ValueError):
        return _deny(REASON_ENV_REJECTED)
    except Exception:
        # A custom Mapping or value may fail with any built-in exception while
        # being read. Nothing can be proven safe, so deny without echoing it.
        return _deny(REASON_ENV_REJECTED)

    # A host allowlist carrying a non-string label cannot ground an
    # "argv_host_approved" claim, even when the app id itself would match.
    if allowed_app_ids is not None:
        if (isinstance(allowed_app_ids, (str, bytes, bytearray, dict))
                or not isinstance(allowed_app_ids, Iterable)):
            return _deny(REASON_ARGV_REJECTED)
        approved = _read_labels(allowed_app_ids)
        if approved is None or not all(type(item) is str for item in approved):
            return _deny(REASON_ARGV_REJECTED)
        allowed_app_ids = frozenset(approved)

    try:
        argv = gio_launch_argv(
            app_id, arguments, allowed_app_ids=allowed_app_ids)
    except (LaunchArgvError, TypeError, ValueError):
        return _deny(REASON_ARGV_REJECTED)
    except Exception:
        # A bounded token iterable may fail with any built-in exception. Deny
        # instead of letting a raw exception pass as a policy decision.
        return _deny(REASON_ARGV_REJECTED)

    try:
        agreed = _env_agrees(env, allow_names) and _argv_agrees(argv, app_id)
    except Exception:
        agreed = False
    if not agreed:
        return _deny(REASON_SOURCE_DISAGREEMENT)

    return LaunchPolicySnapshot(
        status=STATUS_APPROVED,
        reason=REASON_OK,
        env_count=len(env),
        argv_length=len(argv),
        claims=FIXED_CLAIMS,
    )
