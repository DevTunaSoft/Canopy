"""Offline normalization of workspace names and identifiers from permitted sources.

Pure, in-memory component for the Windows-inspired Shell Pack workspace list.
It never polls, opens sockets, reads the registry, launches processes or
observes a live desktop. A trusted caller supplies one explicit snapshot at a
time; this module only validates, normalizes and reconciles that snapshot.

Future Shell Host / compiled Qt integration must pass trusted snapshots here
explicitly. Using this module alone does not prove a working desktop.
"""
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import re
import unicodedata

MAX_WORKSPACES = 64
MAX_NAME_BYTES = 128
MAX_IDENTIFIER_BYTES = 64
MAX_PROBLEMS = 32

_IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
_NON_SLUG = re.compile(r"[^a-z0-9]+")


class WorkspaceInventoryError(ValueError):
    """Invalid caller configuration or malformed required argument."""


@dataclass(frozen=True)
class Workspace:
    """One normalized workspace. Immutable; identifiers are canonical slugs."""

    identifier: str
    name: str
    source: str


@dataclass(frozen=True)
class WorkspaceProblem:
    location: str
    reason: str


@dataclass(frozen=True)
class WorkspaceInventory:
    """Canonical snapshot ordered by first occurrence, plus skipped-record notes."""

    workspaces: tuple
    problems: tuple

    def identifiers(self):
        return tuple(workspace.identifier for workspace in self.workspaces)

    def get(self, identifier):
        """Exact-case lookup; no path resolution or code execution."""
        return next(
            (workspace for workspace in self.workspaces
             if workspace.identifier == identifier),
            None,
        )


@dataclass(frozen=True)
class Reconciliation:
    """Bounded differences between two inventories, with the new inventory."""

    inventory: WorkspaceInventory
    added: tuple
    removed: tuple
    renamed: tuple
    reordered: tuple


def _text(value, field):
    if type(value) is not str:
        raise WorkspaceInventoryError(field + " must be a string")
    return value


def _byte_length(value):
    return len(value.encode("utf-8", "strict"))


def _check_permitted(permitted_sources):
    if (type(permitted_sources) is not frozenset or not permitted_sources
            or any(type(source) is not str or not source
                   for source in permitted_sources)):
        raise WorkspaceInventoryError(
            "permitted_sources must be a non-empty frozenset of strings"
        )


def normalize_name(value):
    """NFKC, trim and collapse whitespace; reject empty or control-laden names."""
    text = unicodedata.normalize("NFKC", _text(value, "name"))
    text = " ".join(text.split())
    if not text:
        raise WorkspaceInventoryError("workspace name is empty after normalization")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in text):
        raise WorkspaceInventoryError("workspace name contains a control character")
    if _byte_length(text) > MAX_NAME_BYTES:
        raise WorkspaceInventoryError("workspace name exceeds byte bound")
    return text


def normalize_identifier(value):
    """Casefold and slugify to a stable lowercase identifier."""
    text = unicodedata.normalize("NFKC", _text(value, "identifier"))
    text = _NON_SLUG.sub("-", text.strip().casefold()).strip("-")
    if not text or not _IDENTIFIER.fullmatch(text):
        raise WorkspaceInventoryError("workspace identifier has no usable characters")
    if _byte_length(text) > MAX_IDENTIFIER_BYTES:
        raise WorkspaceInventoryError("workspace identifier exceeds byte bound")
    return text


def normalize_workspace(record, permitted_sources):
    """Normalize one mapping from a permitted source into a Workspace.

    Required fields: source (must be allowlisted) and name. Optional:
    identifier (or id); when absent, a stable slug is derived from the name.
    """
    _check_permitted(permitted_sources)
    if not isinstance(record, Mapping):
        raise WorkspaceInventoryError("workspace record must be a mapping")
    source = _text(record.get("source"), "source")
    if source not in permitted_sources:
        raise WorkspaceInventoryError("workspace source is not permitted")
    name = normalize_name(record.get("name"))
    raw_identifier = record.get("identifier")
    if raw_identifier is None:
        raw_identifier = record.get("id")
    if raw_identifier is None:
        identifier = normalize_identifier(name)
    else:
        identifier = normalize_identifier(raw_identifier)
    return Workspace(identifier=identifier, name=name, source=source)


def build_inventory(records, *, permitted_sources):
    """Validate, normalize and dedupe a snapshot without executing anything.

    Records from non-permitted sources or with invalid fields are skipped and
    reported. Duplicate identifiers keep the first occurrence. Work and memory
    are bounded by MAX_WORKSPACES and MAX_PROBLEMS regardless of input size.
    """
    _check_permitted(permitted_sources)
    if (isinstance(records, (str, bytes, Mapping))
            or not isinstance(records, Iterable)):
        raise WorkspaceInventoryError("records must be an iterable of mappings")

    seen = {}
    problems = []
    for index, record in enumerate(records):
        location = "record[" + str(index) + "]"
        if len(problems) >= MAX_PROBLEMS:
            break
        try:
            workspace = normalize_workspace(record, permitted_sources)
        except WorkspaceInventoryError as exc:
            problems.append(WorkspaceProblem(location, str(exc)))
            continue
        previous = seen.get(workspace.identifier)
        if previous is not None:
            reason = ("duplicate workspace identifier" if previous == workspace
                      else "conflicting duplicate workspace identifier")
            problems.append(WorkspaceProblem(location, reason))
            continue
        if len(seen) >= MAX_WORKSPACES:
            problems.append(WorkspaceProblem(location, "workspace limit reached"))
            continue
        seen[workspace.identifier] = workspace

    return WorkspaceInventory(
        workspaces=tuple(seen.values()),
        problems=tuple(problems),
    )


def reconcile(previous, current):
    """Report added, removed, renamed and reordered shared workspaces."""
    if not isinstance(previous, WorkspaceInventory) or not isinstance(current, WorkspaceInventory):
        raise WorkspaceInventoryError("reconcile requires two WorkspaceInventory objects")

    previous_by_id = {workspace.identifier: workspace for workspace in previous.workspaces}
    current_by_id = {workspace.identifier: workspace for workspace in current.workspaces}
    previous_ids = list(previous_by_id)
    current_ids = list(current_by_id)

    added = tuple(identifier for identifier in current_ids
                  if identifier not in previous_by_id)
    removed = tuple(identifier for identifier in previous_ids
                    if identifier not in current_by_id)
    renamed = tuple(identifier for identifier in current_ids
                    if identifier in previous_by_id
                    and previous_by_id[identifier].name != current_by_id[identifier].name)

    shared_previous = [identifier for identifier in previous_ids if identifier in current_by_id]
    shared_current = [identifier for identifier in current_ids if identifier in previous_by_id]
    reordered = tuple(identifier for identifier in shared_current
                      if shared_previous.index(identifier) != shared_current.index(identifier))

    return Reconciliation(
        inventory=current,
        added=added,
        removed=removed,
        renamed=renamed,
        reordered=reordered,
    )
