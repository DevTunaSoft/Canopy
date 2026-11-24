"""Pure model of reduced-motion preference propagation, with no rendering changes.

This module resolves a user's reduced-motion preference from three sources
(system accessibility setting, Canopy-wide user setting and a per-presentation
override) and propagates the resulting decision to named presentation
consumers. It is a host-side contract model only:

- no Qt, QML, compositor or window access; no animation is started or stopped;
- no thread, timer, poll loop, process, socket, file or network access;
- no persistent state; all decisions are computed from explicit inputs;
- bounded consumer and input counts, immutable results and explicit cleanup.

It does NOT prove a working desktop, a real accessibility setting read, or
that a compiled Qt presentation honors the decision. A future reviewed host
adapter must consume these decisions and verify real behavior separately.
This deliberately does not reuse ``canopy_core.host_events``: that bus is a
trusted-callback dispatcher with a fixed topic set and no accessibility topic;
extending it is out of scope for this module. The scalar ``as_event_fields``
shape matches the host event payload contract without importing that bus.
"""
from dataclasses import dataclass
import re
from types import MappingProxyType

UNSET = "unset"
FULL = "full"
REDUCE = "reduce"

PREFERENCES = frozenset({UNSET, FULL, REDUCE})

SYSTEM = "system"
USER = "user"
PRESENTATION = "presentation"
DEFAULT_SOURCE = "default"

MAX_CONSUMERS = 64
MAX_PRESENTATIONS = 64
_NAME = re.compile(r"[a-z][a-z0-9_.:-]{0,63}\Z")


class MotionContractError(ValueError):
    """Invalid preference value, consumer name, input mapping or lifecycle use."""


@dataclass(frozen=True)
class MotionDecision:
    """Immutable decision produced by :func:`resolve` for one consumer.

    ``conflicts`` lists explicit sources whose value disagrees with the
    outcome. ``unset_sources`` lists sources that expressed no preference.
    """
    reduced: bool
    source: str
    conflicts: tuple
    unset_sources: tuple
    from_default: bool = False

    @property
    def motion_allowed(self):
        return not self.reduced

    @property
    def conflict_count(self):
        return len(self.conflicts)

    def as_event_fields(self):
        """Flat, scalar payload suitable for a bounded host event field map."""
        return {
            "reduced": self.reduced,
            "source": self.source,
            "conflict_count": self.conflict_count,
            "unset_count": len(self.unset_sources),
            "from_default": self.from_default,
        }


@dataclass(frozen=True)
class PropagationResult:
    """One update's immutable decisions for every registered consumer."""
    version: int
    decisions: object
    changed: tuple

    def decision_for(self, consumer_id):
        """Return the decision delivered to ``consumer_id`` on this update.

        Any id that is not a delivered consumer fails closed with
        :class:`MotionContractError`, including unhashable ids whose mapping
        lookup raises ``TypeError`` rather than ``KeyError``.
        """
        try:
            return self.decisions[consumer_id]
        except (KeyError, TypeError) as exc:
            raise MotionContractError("unknown reduced-motion consumer") from exc


def _check_preference(value, label):
    if type(value) is not str or value not in PREFERENCES:
        raise MotionContractError("invalid reduced-motion preference for " + label)


def _check_name(value, label):
    if type(value) is not str or not _NAME.fullmatch(value):
        raise MotionContractError("invalid reduced-motion " + label)


def resolve(system=UNSET, user=UNSET, presentation=UNSET):
    """Resolve one decision from three explicitly supplied source values.

    Precedence is system < user < presentation. A ``REDUCE`` from any source
    is authoritative: accessibility must not be re-enabled by a more specific
    ``FULL`` override. The highest-authority source agreeing with the outcome
    is recorded as the deciding source. With no explicit value at all, the
    decision fails safe to ``REDUCE`` from ``default``.
    """
    for label, value in (("system", system), ("user", user),
                         ("presentation", presentation)):
        _check_preference(value, label)

    # Ordered from lowest to highest authority.
    sources = ((SYSTEM, system), (USER, user), (PRESENTATION, presentation))
    unset = tuple(name for name, value in sources if value == UNSET)
    explicit = tuple((name, value) for name, value in sources if value != UNSET)

    reducers = tuple(name for name, value in explicit if value == REDUCE)
    if reducers:
        reduced = True
        deciding = reducers[-1]
        conflicts = tuple(name for name, value in explicit if value == FULL)
    elif explicit:
        reduced = False
        deciding = explicit[-1][0]
        conflicts = ()
    else:
        return MotionDecision(True, DEFAULT_SOURCE, (), unset, True)

    return MotionDecision(reduced, deciding, conflicts, unset)


class ReducedMotionContract:
    """Bounded, event-driven propagation of one decision to named consumers.

    Decisions are recomputed only by :meth:`update`. Registration of a late
    consumer resolves it against the current inputs. No background work runs
    and nothing is rendered.
    """

    def __init__(self):
        self._consumers = {}
        self._last = {}
        self._system = UNSET
        self._user = UNSET
        self._overrides = {}
        self._version = 0

    @property
    def version(self):
        return self._version

    @property
    def consumer_ids(self):
        return tuple(self._consumers)

    def register(self, consumer_id):
        """Add a consumer name; a late joiner gets the current decision."""
        _check_name(consumer_id, "consumer id")
        if consumer_id in self._consumers:
            raise MotionContractError("reduced-motion consumer already registered")
        if len(self._consumers) >= MAX_CONSUMERS:
            raise MotionContractError("reduced-motion consumer limit reached")
        self._consumers[consumer_id] = None
        if self._version:
            self._last[consumer_id] = resolve(
                self._system, self._user, self._overrides.get(consumer_id, UNSET))

    def unregister(self, consumer_id):
        """Remove a consumer and drop its last decision. Returns True if found."""
        _check_name(consumer_id, "consumer id")
        if consumer_id not in self._consumers:
            return False
        del self._consumers[consumer_id]
        self._last.pop(consumer_id, None)
        self._overrides.pop(consumer_id, None)
        return True

    def snapshot(self):
        """Immutable view of the last decision delivered to each consumer."""
        return MappingProxyType(dict(self._last))

    def update(self, *, system=UNSET, user=UNSET, presentations=None):
        """Recompute and propagate decisions. Returns a PropagationResult.

        ``presentations`` maps a registered consumer id to that consumer's
        per-presentation override; unlisted consumers use ``unset``.
        """
        _check_preference(system, "system")
        _check_preference(user, "user")
        if presentations is None:
            presentations = {}
        if type(presentations) is not dict:
            raise MotionContractError("presentation overrides must be a mapping")
        if len(presentations) > MAX_PRESENTATIONS:
            raise MotionContractError("presentation override limit reached")
        for consumer_id, preference in presentations.items():
            _check_name(consumer_id, "consumer id")
            if consumer_id not in self._consumers:
                raise MotionContractError("override for unknown reduced-motion consumer")
            _check_preference(preference, "presentation override for " + consumer_id)

        previous = self._last
        delivered = {}
        changed = []
        for consumer_id in self._consumers:
            decision = resolve(system, user, presentations.get(consumer_id, UNSET))
            delivered[consumer_id] = decision
            if previous.get(consumer_id) != decision:
                changed.append(consumer_id)

        self._system = system
        self._user = user
        self._overrides = dict(presentations)
        self._last = delivered
        self._version += 1
        return PropagationResult(self._version, MappingProxyType(delivered),
                                 tuple(changed))

    def clear(self):
        """Release all consumers and inputs; further updates start from default."""
        self._consumers.clear()
        self._last.clear()
        self._overrides.clear()
        self._system = UNSET
        self._user = UNSET
        self._version = 0
