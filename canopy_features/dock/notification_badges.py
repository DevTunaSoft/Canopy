"""Bounded, host-owned unread badge counts for trusted dock applications.

Pure in-memory component. It does not draw pixels, read OS notifications,
poll, start threads or services, open sockets, or touch the compiled Qt
application. A trusted host supplies the application allowlist and feeds
counts in; display code turns the bounded result into a badge later.

This module proves only the count-bounding logic. It is not a working dock
badge until integrated into the compiled Classic Qt application.
"""
import re
from types import MappingProxyType

MAX_TRUSTED_APPLICATIONS = 64
MAX_APP_ID_LENGTH = 64
MAX_COUNT = 99
OVERFLOW_SUFFIX = "+"

_APP_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


class BadgeError(ValueError):
    """Invalid application id, untrusted application, or bad count value."""


def _valid_app(app):
    if (type(app) is not str or len(app) > MAX_APP_ID_LENGTH
            or not _APP_ID.fullmatch(app)):
        raise BadgeError("invalid application id")


def _valid_count(value, *, name="count"):
    # bool is a subclass of int; reject it. Floats (incl. nan/inf), strings,
    # None and containers are malformed notification counts.
    if type(value) is not int:
        raise BadgeError("%s must be an exact int" % name)
    if value < 0:
        raise BadgeError("%s must not be negative" % name)
    return value


class NotificationBadges:
    """Bound unread counts per trusted application, with no background work.

    ``trusted_applications`` is an explicit allowlist from trusted host code.
    Only those ids can hold a badge. The allowlist is hard-bounded, so live
    badge entries are bounded too: no unbounded memory growth.

    ``max_count`` tunes the saturation point and may not exceed ``MAX_COUNT``.
    Counts at or above the bound saturate and display as ``"99+"`` style text.
    """

    def __init__(self, trusted_applications, *, max_count=MAX_COUNT):
        if type(max_count) is not int or not 1 <= max_count <= MAX_COUNT:
            raise BadgeError("invalid badge count bound")
        if type(trusted_applications) not in (list, tuple, set, frozenset):
            raise BadgeError("explicit trusted application allowlist required")
        if len(trusted_applications) > MAX_TRUSTED_APPLICATIONS:
            raise BadgeError("too many trusted applications")
        vetted = set()
        for app in trusted_applications:
            _valid_app(app)
            vetted.add(app)
        self._trusted = frozenset(vetted)
        self._max = max_count
        self._badges = {}

    @property
    def trusted(self):
        return self._trusted

    @property
    def max_count(self):
        return self._max

    def _check(self, app):
        _valid_app(app)
        if app not in self._trusted:
            raise BadgeError("application is not trusted")

    def _store(self, app, value):
        if value > 0:
            self._badges[app] = value
        else:
            self._badges.pop(app, None)

    def set(self, app, count):
        """Set a badge count clamped to the bound; return the stored count."""
        self._check(app)
        value = min(_valid_count(count), self._max)
        self._store(app, value)
        return value

    def increment(self, app, amount=1):
        """Add a non-negative amount, saturating at the bound."""
        self._check(app)
        step = min(_valid_count(amount, name="amount"), self._max)
        value = min(self._badges.get(app, 0) + step, self._max)
        self._store(app, value)
        return value

    def decrement(self, app, amount=1):
        """Subtract a non-negative amount, flooring at zero."""
        self._check(app)
        step = min(_valid_count(amount, name="amount"), self._max)
        value = max(self._badges.get(app, 0) - step, 0)
        self._store(app, value)
        return value

    def clear(self, app):
        """Remove a badge; idempotent for a trusted app with no badge."""
        self._check(app)
        self._badges.pop(app, None)

    def count(self, app):
        """Return the bounded stored count, or zero when no badge is set."""
        self._check(app)
        return self._badges.get(app, 0)

    def display(self, app):
        """Bounded label: "" for zero, "N+" at saturation, else digits."""
        self._check(app)
        value = self._badges.get(app, 0)
        if value == 0:
            return ""
        if value >= self._max:
            return "%d%s" % (self._max, OVERFLOW_SUFFIX)
        return str(value)

    def snapshot(self):
        """Immutable view of active badges, safe to hand to display code."""
        return MappingProxyType(dict(self._badges))

    def active_count(self):
        """Number of applications currently holding a non-zero badge."""
        return len(self._badges)
