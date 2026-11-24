"""Bounded notification delivery with explicit missed/repeated/reordered and
overflow-fallback contracts.

This is a pure, single-thread, in-memory primitive for host code that already
owns a notification sequence (for example ``HostEvent.sequence``). It does not
duplicate ``canopy_core.host_events``: that module dispatches trusted callbacks;
this module verifies the health of a bounded delivery channel and reports what
the fallback did when the channel filled.

Limits: no threads, timers, polling, sockets, privileged calls or OS/Qt event
observation. Callers own payload size and thread confinement. Memory is bounded
by ``capacity``: pending items, delivery history and notice history never
exceed it. Sequence gaps are counted, never materialised in full.
"""
from collections import deque
from dataclasses import dataclass

MAX_CAPACITY = 64
POLICIES = frozenset({"drop_oldest", "reject_new"})

QUEUED = "queued"
DROPPED_OLDEST = "dropped_oldest"
REJECTED = "rejected"

DELIVERED = "delivered"
DUPLICATE = "duplicate"
REORDERED = "reordered"
GAP = "gap"


class DeliveryError(ValueError):
    """Invalid capacity, policy, sequence or caller state."""


class ChannelClosed(RuntimeError):
    """No send or receive after explicit cleanup."""


@dataclass(frozen=True)
class OverflowNotice:
    """Explicit record of one overflow fallback; never a silent drop."""

    sequence: int
    policy: str
    pending_count: int


@dataclass(frozen=True)
class SendResult:
    accepted: bool
    status: str
    sequence: int
    notice: object = None


@dataclass(frozen=True)
class Delivery:
    sequence: int
    payload: object
    status: str
    missed_count: int = 0
    missed_sequences: tuple = ()


@dataclass(frozen=True)
class DeliveryStats:
    sent: int
    received: int
    delivered: int
    duplicates: int
    reordered: int
    gaps: int
    missed: int
    dropped: int
    rejected: int


class BoundedDeliveryChannel:
    """Fixed-capacity FIFO channel with counted overflow and delivery health.

    ``send`` queues a caller-sequenced notification. When the queue is full,
    ``drop_oldest`` evicts the oldest pending item, or ``reject_new`` refuses
    the new one; both return an ``OverflowNotice`` and increment a counter.
    ``receive`` delivers FIFO and classifies the observed sequence against the
    highest sequence delivered so far:

    - ``delivered``: next expected sequence;
    - ``gap``: higher sequence, with missed count (missed, e.g. after a drop);
    - ``duplicate``: sequence already delivered recently (repeated notice);
    - ``reordered``: lower, not-recently-delivered sequence (late notice).
    """

    def __init__(self, capacity=16, *, policy="drop_oldest", start_sequence=1):
        if (type(capacity) is not int or not 1 <= capacity <= MAX_CAPACITY):
            raise DeliveryError("capacity must be an int within 1..64")
        # Gate on type before the frozenset membership test: an unhashable
        # caller value (list/dict) must fail closed with the documented
        # DeliveryError, not leak a bare TypeError from set lookup.
        if not isinstance(policy, str) or policy not in POLICIES:
            raise DeliveryError("unsupported overflow policy")
        if type(start_sequence) is not int or start_sequence < 0:
            raise DeliveryError("invalid start sequence")
        self._capacity = capacity
        self._policy = policy
        self._start = start_sequence
        self._pending = deque()
        self._seen = deque()
        self._seen_set = set()
        self._notices = deque(maxlen=capacity)
        self._last = start_sequence - 1
        self._closed = False
        self._counts = dict(sent=0, received=0, delivered=0, duplicates=0,
                            reordered=0, gaps=0, missed=0, dropped=0,
                            rejected=0)

    def _ready(self):
        if self._closed:
            raise ChannelClosed("delivery channel is closed")

    def _check_sequence(self, sequence):
        if (type(sequence) is not int or sequence < self._start):
            raise DeliveryError("invalid notification sequence")

    def _notice(self, sequence):
        notice = OverflowNotice(sequence, self._policy, len(self._pending))
        self._notices.append(notice)
        return notice

    def send(self, sequence, payload=None):
        """Queue one notification; apply the bounded overflow fallback."""
        self._ready()
        self._check_sequence(sequence)
        self._counts["sent"] += 1
        if len(self._pending) < self._capacity:
            self._pending.append((sequence, payload))
            return SendResult(True, QUEUED, sequence)
        if self._policy == "reject_new":
            self._counts["rejected"] += 1
            return SendResult(False, REJECTED, sequence,
                              self._notice(sequence))
        evicted_sequence, _ = self._pending.popleft()
        self._counts["dropped"] += 1
        notice = self._notice(evicted_sequence)
        self._pending.append((sequence, payload))
        return SendResult(True, DROPPED_OLDEST, sequence, notice)

    def receive(self):
        """Deliver the oldest pending item, or return None when empty."""
        self._ready()
        if not self._pending:
            return None
        sequence, payload = self._pending.popleft()
        counts = self._counts
        counts["received"] += 1
        missed_count = 0
        missed_sequences = ()
        if sequence > self._last:
            if sequence == self._last + 1:
                status = DELIVERED
                counts["delivered"] += 1
            else:
                status = GAP
                counts["gaps"] += 1
                missed_count = sequence - self._last - 1
                counts["missed"] += missed_count
                # shortcut: expose at most capacity absent sequences; callers
                # needing a full list must unblock delivery, not grow memory.
                missed_sequences = tuple(range(
                    self._last + 1, self._last + 1 + min(missed_count, self._capacity)))
            self._last = sequence
        elif sequence in self._seen_set:
            status = DUPLICATE
            counts["duplicates"] += 1
        else:
            status = REORDERED
            counts["reordered"] += 1
        if sequence not in self._seen_set:
            if len(self._seen) >= self._capacity:
                self._seen_set.discard(self._seen.popleft())
            self._seen.append(sequence)
            self._seen_set.add(sequence)
        return Delivery(sequence, payload, status, missed_count,
                        missed_sequences)

    def close(self):
        """Fail-closed cleanup: release pending, history and notice state."""
        self._pending.clear()
        self._seen.clear()
        self._seen_set.clear()
        self._notices.clear()
        self._closed = True

    @property
    def pending_count(self):
        return len(self._pending)

    @property
    def closed(self):
        return self._closed

    @property
    def stats(self):
        return DeliveryStats(**self._counts)

    def overflow_notices(self):
        """Bounded copy (at most capacity entries) of overflow fallbacks."""
        return tuple(self._notices)
