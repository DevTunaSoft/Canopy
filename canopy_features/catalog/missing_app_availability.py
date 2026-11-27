"""Pure, bounded missing-application availability source contract.

Classic's catalog, dock and launcher need one stable answer when an application
is absent from the source catalog, fails its ``TryExec`` probe, or cannot be
read. This module supplies that answer as an immutable record with fixed reason
codes. It performs no filesystem access, process launch, shell call, polling,
timer, network work or visual change, and it echoes no application text into
its diagnostic mapping.

A missing application stays UNAVAILABLE and never grants launch permission.
Re-checking is explicit and bounded: one refresh call probes at most
``MAX_REFRESH_ATTEMPTS`` times, a transient single positive probe cannot flip
the state, and a tracker allows at most ``MAX_REFRESH_CYCLES`` refreshes per
authoritative catalog epoch before freezing on ``refresh_exhausted``. A new
authoritative ``observe()`` or explicit ``reconcile()`` starts a new epoch and
clears the exhaustion; no timer, poll or background retry ever does. Probe
exceptions and malformed or partial probe shapes
become a fixed reason instead of leaking a raw exception to the host. A probe
mapping must carry explicit ``tryexec_ok`` and ``entry_readable`` booleans:
omitted facts are a failed probe, never an assumed positive, so catalog
presence alone can never grant launch permission.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Tuple

from canopy_features.apps.launch_argv import DESKTOP_ID

STATUS_AVAILABLE = "available"
STATUS_UNAVAILABLE = "unavailable"

REASON_OK = "ok"
REASON_NOT_IN_CATALOG = "not_in_catalog"
REASON_TRYEXEC_FAILED = "tryexec_failed"
REASON_ENTRY_UNREADABLE = "entry_unreadable"
REASON_PROBE_FAILED = "probe_failed"
REASON_EXHAUSTED = "refresh_exhausted"
REASON_INVALID_INPUT = "invalid_input"

FIXED_REASONS = (
    REASON_ENTRY_UNREADABLE,
    REASON_EXHAUSTED,
    REASON_INVALID_INPUT,
    REASON_NOT_IN_CATALOG,
    REASON_OK,
    REASON_PROBE_FAILED,
    REASON_TRYEXEC_FAILED,
)

CLAIM_NO_PROCESS_LAUNCH = "no_process_launch"
CLAIM_NO_UNBOUNDED_REFRESH = "no_unbounded_refresh"
CLAIM_NO_VALUE_ECHO = "no_value_echo"
CLAIM_STABLE_UNAVAILABLE = "stable_unavailable_state"

FIXED_CLAIMS = (
    CLAIM_NO_PROCESS_LAUNCH,
    CLAIM_NO_UNBOUNDED_REFRESH,
    CLAIM_NO_VALUE_ECHO,
    CLAIM_STABLE_UNAVAILABLE,
)

MAX_REFRESH_ATTEMPTS = 3
MAX_REFRESH_CYCLES = 8
MAX_TRACKED_APPS = 256
MAX_APP_ID_CHARS = 128
REQUIRED_CONFIRMATIONS = 2

__all__ = [
    "CLAIM_NO_PROCESS_LAUNCH",
    "CLAIM_NO_UNBOUNDED_REFRESH",
    "CLAIM_NO_VALUE_ECHO",
    "CLAIM_STABLE_UNAVAILABLE",
    "FIXED_CLAIMS",
    "FIXED_REASONS",
    "MAX_APP_ID_CHARS",
    "MAX_REFRESH_ATTEMPTS",
    "MAX_REFRESH_CYCLES",
    "MAX_TRACKED_APPS",
    "REQUIRED_CONFIRMATIONS",
    "REASON_ENTRY_UNREADABLE",
    "REASON_EXHAUSTED",
    "REASON_INVALID_INPUT",
    "REASON_NOT_IN_CATALOG",
    "REASON_OK",
    "REASON_PROBE_FAILED",
    "REASON_TRYEXEC_FAILED",
    "STATUS_AVAILABLE",
    "STATUS_UNAVAILABLE",
    "AppAvailability",
    "MissingAppError",
    "MissingAppTracker",
    "classify_missing_app",
]


class MissingAppError(ValueError):
    """A caller supplied a malformed id, bound, fact or probe."""


def _check_app_id(app_id):
    if type(app_id) is not str or len(app_id) > MAX_APP_ID_CHARS:
        raise MissingAppError("invalid application id")
    if DESKTOP_ID.fullmatch(app_id) is None:
        raise MissingAppError("invalid application id")
    return app_id


def _check_bool(value, label):
    if type(value) is not bool:
        raise MissingAppError("invalid %s fact" % label)
    return value


def _check_bound(value, maximum, label):
    if type(value) is not int or not 1 <= value <= maximum:
        raise MissingAppError("invalid %s bound" % label)
    return value


@dataclass(frozen=True)
class AppAvailability:
    """One bounded availability decision for a validated desktop id.

    ``app_id`` is available to trusted matching code only; ``to_dict`` carries
    counts, fixed reason/claim tokens and a permission flag, never source text.
    """

    app_id: str
    status: str
    reason: str
    refresh_count: int = 0
    confirmations: int = 0
    probe_calls: int = 0
    claims: Tuple[str, ...] = field(default=FIXED_CLAIMS)

    def __post_init__(self):
        _check_app_id(self.app_id)
        if self.status not in (STATUS_AVAILABLE, STATUS_UNAVAILABLE):
            raise MissingAppError("invalid availability status")
        if self.reason not in FIXED_REASONS:
            raise MissingAppError("invalid availability reason")
        for name in ("refresh_count", "confirmations", "probe_calls"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise MissingAppError("invalid %s" % name)
        if self.claims != FIXED_CLAIMS:
            raise MissingAppError("invalid availability claims")

    @property
    def available(self):
        return self.status == STATUS_AVAILABLE

    @property
    def unavailable(self):
        return self.status == STATUS_UNAVAILABLE

    @property
    def launch_permitted(self):
        """Only an explicitly confirmed, present application may be launched."""
        return self.status == STATUS_AVAILABLE and self.reason == REASON_OK

    def to_dict(self):
        return {
            "status": self.status,
            "reason": self.reason,
            "refresh_count": self.refresh_count,
            "confirmations": self.confirmations,
            "probe_calls": self.probe_calls,
            "launch_permitted": self.launch_permitted,
            "claims": list(self.claims),
        }


def classify_missing_app(
    app_id, *, in_catalog, tryexec_ok=True, entry_readable=True,
):
    """Classify source facts without touching the host or emitting an intent.

    Facts must be real booleans. Every refusal has one fixed reason and an
    immutable record whose ``launch_permitted`` is false.
    """
    _check_app_id(app_id)
    _check_bool(in_catalog, "in_catalog")
    _check_bool(tryexec_ok, "tryexec_ok")
    _check_bool(entry_readable, "entry_readable")

    if not in_catalog:
        reason = REASON_NOT_IN_CATALOG
    elif not entry_readable:
        reason = REASON_ENTRY_UNREADABLE
    elif not tryexec_ok:
        reason = REASON_TRYEXEC_FAILED
    else:
        return AppAvailability(app_id, STATUS_AVAILABLE, REASON_OK)
    return AppAvailability(app_id, STATUS_UNAVAILABLE, reason)


def _probe_facts(raw):
    """Translate a probe result into strict booleans or fail closed.

    A complete positive fact set is required: omitting TryExec or read facts
    is never treated as a positive default. The historical bool shorthand
    stays a complete fact set for backward compatibility.
    """
    if type(raw) is bool:
        return {
            "in_catalog": raw,
            "tryexec_ok": raw,
            "entry_readable": raw,
        }
    if isinstance(raw, Mapping) and "in_catalog" in raw:
        if "tryexec_ok" not in raw or "entry_readable" not in raw:
            raise MissingAppError("probe omitted required availability facts")
        return {
            "in_catalog": raw["in_catalog"],
            "tryexec_ok": raw["tryexec_ok"],
            "entry_readable": raw["entry_readable"],
        }
    raise MissingAppError("probe returned an unsupported availability shape")


class MissingAppTracker:
    """Bounded, in-memory availability states; no timers or background work."""

    def __init__(self, *, max_refresh_attempts=MAX_REFRESH_ATTEMPTS,
                 max_refresh_cycles=MAX_REFRESH_CYCLES):
        self._max_attempts = _check_bound(
            max_refresh_attempts, MAX_REFRESH_ATTEMPTS, "refresh attempts")
        self._max_cycles = _check_bound(
            max_refresh_cycles, MAX_REFRESH_CYCLES, "refresh cycles")
        self._states = {}

    def state(self, app_id):
        """Return the stored decision; unknown ids are stably unavailable."""
        _check_app_id(app_id)
        return self._states.get(
            app_id,
            AppAvailability(app_id, STATUS_UNAVAILABLE, REASON_NOT_IN_CATALOG),
        )

    def observe(self, app_id, *, in_catalog, tryexec_ok=True,
                entry_readable=True):
        """Record one authoritative catalog observation (not a probe retry)."""
        _check_app_id(app_id)
        state = classify_missing_app(
            app_id, in_catalog=in_catalog, tryexec_ok=tryexec_ok,
            entry_readable=entry_readable)
        if app_id not in self._states and len(self._states) >= MAX_TRACKED_APPS:
            raise MissingAppError("availability state cache is full")
        self._states[app_id] = state
        return state

    def reconcile(self, app_id, *, in_catalog, tryexec_ok=True,
                  entry_readable=True):
        """Apply authoritative facts and open a new refresh epoch.

        This is the explicit recovery path for an ``refresh_exhausted`` app.
        It reuses the same bounded state cache and strict fact validation as
        ``observe``: no probe is called here, no fact is inferred from an
        exhausted counter, and no launch permission is granted without real
        positive facts.
        """
        return self.observe(
            app_id, in_catalog=in_catalog, tryexec_ok=tryexec_ok,
            entry_readable=entry_readable)

    def refresh(self, app_id, probe):
        """Re-check a state with at most ``max_refresh_attempts`` probe calls.

        The probe may return a bool or a mapping of source facts. Any raised
        exception, malformed shape or non-boolean fact becomes
        ``probe_failed``. Two consecutive positive probes are required before
        an unavailable application may become launchable. The cycle cap is
        per authoritative epoch: ``observe()`` or ``reconcile()`` opens a new
        epoch, while this method never probes past the cap.
        """
        _check_app_id(app_id)
        if not callable(probe):
            raise MissingAppError("probe must be callable")
        prior = self.state(app_id)
        if prior.reason == REASON_EXHAUSTED:
            return prior
        if prior.refresh_count >= self._max_cycles:
            state = replace(prior, reason=REASON_EXHAUSTED, probe_calls=0)
            self._states[app_id] = state
            return state

        confirmations = 0
        calls = 0
        last_failure = REASON_PROBE_FAILED
        for _ in range(self._max_attempts):
            calls += 1
            try:
                candidate = classify_missing_app(
                    app_id, **_probe_facts(probe(app_id)))
            except Exception:
                # Host probes are untrusted: never let their exception reach
                # the shell, and never interpret it as a positive presence.
                confirmations = 0
                last_failure = REASON_PROBE_FAILED
                continue
            if candidate.launch_permitted:
                confirmations += 1
                if confirmations >= REQUIRED_CONFIRMATIONS:
                    break
            else:
                confirmations = 0
                last_failure = candidate.reason

        if confirmations >= REQUIRED_CONFIRMATIONS:
            state = AppAvailability(
                app_id, STATUS_AVAILABLE, REASON_OK,
                refresh_count=prior.refresh_count + 1,
                confirmations=REQUIRED_CONFIRMATIONS, probe_calls=calls)
        else:
            state = AppAvailability(
                app_id, STATUS_UNAVAILABLE, last_failure,
                refresh_count=prior.refresh_count + 1,
                confirmations=0, probe_calls=calls)
        if app_id not in self._states and len(self._states) >= MAX_TRACKED_APPS:
            raise MissingAppError("availability state cache is full")
        self._states[app_id] = state
        return state

    def snapshot(self):
        """Immutable, deterministic snapshot ordered by application id."""
        return tuple(
            self._states[key] for key in sorted(self._states)
        )
