"""Offline validator/reverter for interrupted dock pin-order transactions.

Pure and deterministic: no Qt, no filesystem, no polling, no background
service, no privileged or networked operation. The caller owns journal
storage and applies the returned RecoveryPlan. This component does NOT prove
a working desktop; future work must wire it into the compiled Classic Qt app.
"""

from dataclasses import dataclass
import hashlib
import hmac
import json
import re

FORMAT_VERSION = 1
PHASES = ("prepared", "committed", "reverted")
MAX_PINS = 64
MAX_PIN_ID_BYTES = 128
MAX_JOURNAL_BYTES = 16_384
MAX_TRANSACTION_ID_BYTES = 64

TRANSACTION_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
PIN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._@-]{0,127}\Z")
CHECKSUM = re.compile(r"sha256:[0-9a-f]{64}\Z")
_KEYS = frozenset(("version", "transaction_id", "phase", "before",
                   "after", "checksum"))
_FIELDS = frozenset(("version", "transaction_id", "phase", "before", "after"))

__all__ = (
    "FORMAT_VERSION", "PHASES", "MAX_PINS", "MAX_PIN_ID_BYTES",
    "MAX_JOURNAL_BYTES", "MAX_TRANSACTION_ID_BYTES", "PinOrderError",
    "Transaction", "RecoveryPlan", "new_transaction", "with_phase",
    "encode", "decode", "plan_recovery",
)


class PinOrderError(ValueError):
    """Invalid journal, pin order, transaction ID or phase."""


def _valid_order(value, label):
    if type(value) not in (list, tuple):
        raise PinOrderError(label + " must be an ordered sequence")
    if len(value) > MAX_PINS:
        raise PinOrderError(label + " exceeds the pin bound")
    seen = set()
    order = []
    for pin in value:
        if type(pin) is not str or not PIN_ID.fullmatch(pin):
            raise PinOrderError("invalid pin id in " + label)
        if len(pin.encode("ascii")) > MAX_PIN_ID_BYTES:
            raise PinOrderError("pin id exceeds byte bound in " + label)
        if pin in seen:
            raise PinOrderError("duplicate pin in " + label)
        seen.add(pin)
        order.append(pin)
    return tuple(order)


@dataclass(frozen=True)
class Transaction:
    """Checksummed journal record for one pin reorder attempt."""

    transaction_id: str
    phase: str
    before: tuple
    after: tuple

    def __post_init__(self):
        if (type(self.transaction_id) is not str
                or not TRANSACTION_ID.fullmatch(self.transaction_id)
                or len(self.transaction_id) > MAX_TRANSACTION_ID_BYTES):
            raise PinOrderError("invalid transaction id")
        if type(self.phase) is not str or self.phase not in PHASES:
            raise PinOrderError("invalid transaction phase")
        before = _valid_order(self.before, "before")
        after = _valid_order(self.after, "after")
        if set(before) != set(after):
            raise PinOrderError("reorder must preserve the pin set")
        object.__setattr__(self, "before", before)
        object.__setattr__(self, "after", after)


@dataclass(frozen=True)
class RecoveryPlan:
    """Decision for the host: what to write and whether to clear the journal."""

    status: str
    order: tuple
    note: str

    @property
    def should_write_order(self):
        return self.status in ("REVERT", "APPLY")

    @property
    def should_clear_journal(self):
        return self.status in ("CLEAN", "DISCARD", "REVERT", "APPLY")


def new_transaction(transaction_id, before, after):
    """Start a prepared reorder. Caller persists encode() result atomically."""
    return Transaction(transaction_id, "prepared", before, after)


def with_phase(transaction, phase):
    """Return an equivalent record at another lifecycle phase."""
    if not isinstance(transaction, Transaction):
        raise TypeError("transaction required")
    return Transaction(transaction.transaction_id, phase,
                       transaction.before, transaction.after)


def _fields(transaction):
    return {
        "version": FORMAT_VERSION,
        "transaction_id": transaction.transaction_id,
        "phase": transaction.phase,
        "before": list(transaction.before),
        "after": list(transaction.after),
    }


def _checksum(fields):
    canonical = json.dumps(fields, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True).encode("ascii")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def encode(transaction):
    """Serialize a transaction to canonical, checksummed ASCII bytes."""
    if not isinstance(transaction, Transaction):
        raise TypeError("transaction required")
    fields = _fields(transaction)
    payload = dict(fields)
    payload["checksum"] = _checksum(fields)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("ascii")


def decode(raw):
    """Parse a journal strictly. Torn, truncated or corrupt input fails closed."""
    if type(raw) is str:
        try:
            data = raw.encode("utf-8", "strict")
        except UnicodeError as exc:
            raise PinOrderError("journal is not valid UTF-8") from exc
    elif type(raw) in (bytes, bytearray):
        data = bytes(raw)
    else:
        raise TypeError("journal must be bytes or str")
    if not data:
        raise PinOrderError("empty journal")
    if len(data) > MAX_JOURNAL_BYTES:
        raise PinOrderError("journal exceeds size bound")
    try:
        payload = json.loads(data.decode("utf-8", "strict"))
    except (UnicodeError, ValueError) as exc:
        raise PinOrderError("journal is truncated or corrupt") from exc
    if type(payload) is not dict:
        raise PinOrderError("journal root must be an object")
    if set(payload) != _KEYS:
        raise PinOrderError("journal has missing or extra fields")
    if type(payload["version"]) is not int or payload["version"] != FORMAT_VERSION:
        raise PinOrderError("unsupported journal version")
    checksum = payload["checksum"]
    if type(checksum) is not str or not CHECKSUM.fullmatch(checksum):
        raise PinOrderError("malformed journal checksum")
    fields = {key: payload[key] for key in _FIELDS}
    if not hmac.compare_digest(checksum, _checksum(fields)):
        raise PinOrderError("journal checksum mismatch")
    return Transaction(fields["transaction_id"], fields["phase"],
                       fields["before"], fields["after"])


def plan_recovery(raw_journal, current_order, baseline):
    """Compare journal, live order and last known-good baseline.

    Never overwrites state on an unknown or torn journal. `baseline` is the
    trusted committed order used only when no valid journal can be decoded.
    """
    current = _valid_order(current_order, "current order")
    base = _valid_order(baseline, "baseline order")
    if raw_journal is None:
        return RecoveryPlan("CLEAN", (), "no journal")

    try:
        transaction = decode(raw_journal)
    except PinOrderError:
        if current == base:
            return RecoveryPlan("DISCARD", (), "torn journal; state at baseline")
        return RecoveryPlan("INVALID", (), "torn journal; state diverged")

    before, after = transaction.before, transaction.after
    if transaction.phase == "prepared":
        if current == before:
            return RecoveryPlan("DISCARD", (), "prepared, never applied")
        if current == after:
            return RecoveryPlan("REVERT", before, "applied before commit")
    elif transaction.phase == "committed":
        if current == after:
            return RecoveryPlan("DISCARD", (), "commit complete")
        if current == before:
            return RecoveryPlan("APPLY", after, "commit recorded, order not applied")
    else:
        if current == before:
            return RecoveryPlan("DISCARD", (), "revert complete")
        if current == after:
            return RecoveryPlan("REVERT", before, "revert recorded, not applied")
    return RecoveryPlan("CONFLICT", (), "state matches neither journal side")
