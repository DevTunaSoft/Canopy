"""Parse Linux /proc PSS evidence without estimating missing values.

Pure, offline parser plus a narrow read helper. It never guesses, interpolates,
or substitutes a value when a Pss total is absent or invalid:

- MissingPssError  -> no Pss total line exists.
- MalformedPssError -> a Pss total exists but is not a usable value.
- ProcessDisappearedError -> the process or its /proc entry was gone.

No polling, background services, privileged calls, or network access.
"""
import re
from pathlib import Path

__all__ = [
    "PssError",
    "MissingPssError",
    "MalformedPssError",
    "ProcessDisappearedError",
    "parse_pss_kib",
    "read_pss_kib",
]

# Strict ASCII decimal integer, so Unicode digits and signs cannot slip in.
_INT = re.compile(r"[0-9]+\Z")


class PssError(ValueError):
    """Base class for PSS evidence that cannot be used as reported."""


class MissingPssError(PssError):
    """No Pss total line is present; the value must not be estimated."""


class MalformedPssError(PssError):
    """A Pss total line is present but is not a valid non-negative integer."""


class ProcessDisappearedError(PssError):
    """The process or its /proc entry was gone when the file was read."""


def parse_pss_kib(text):
    """Return the Pss total in KiB from smaps_rollup *text*.

    Only an exact ``Pss:`` field counts; ``Pss_Dirty:``, ``Pss_Anon:`` and
    similar totals are ignored. Raises MissingPssError when no total exists
    and MalformedPssError when one exists but is unusable. Never estimates.
    """
    if not isinstance(text, str):
        raise MalformedPssError("Pss evidence must be text")
    found = None
    for line in text.splitlines():
        if ":" not in line:
            continue
        field, _, raw = line.partition(":")
        if field.strip() != "Pss":
            continue
        tokens = raw.split()
        # Accept "<int>" or "<int> kB"; reject empty, extra, or wrong-unit
        # forms rather than guessing which token is the total.
        if not 1 <= len(tokens) <= 2 or (len(tokens) == 2 and tokens[1] != "kB"):
            raise MalformedPssError("malformed Pss total line")
        token = tokens[0]
        if not _INT.fullmatch(token):
            raise MalformedPssError("Pss total is not a non-negative integer")
        value = int(token)
        if found is not None and found != value:
            raise MalformedPssError("conflicting Pss totals")
        found = value
    if found is None:
        raise MissingPssError("Pss total missing")
    return found


def read_pss_kib(pid, *, proc_root="/proc"):
    """Read the Pss total for *pid* from ``<proc_root>/<pid>/smaps_rollup``.

    A vanished process maps to ProcessDisappearedError. Parse failures surface
    as MissingPssError or MalformedPssError unchanged. No retry or polling.
    Pass *proc_root* to read an offline capture or to test on non-Linux hosts.
    """
    path = Path(proc_root) / str(int(pid)) / "smaps_rollup"
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError, ProcessLookupError) as exc:
        raise ProcessDisappearedError("process or /proc entry disappeared") from exc
    return parse_pss_kib(text)
