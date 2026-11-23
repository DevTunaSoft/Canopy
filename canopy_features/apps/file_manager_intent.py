"""Form safe, inert file-manager launch intents for real user directories.

Data only: this module never spawns a process, opens a desktop file, uses the
network, or keeps state between calls. A trusted host maps the resulting
``file://`` URI to whichever launcher that host owns.

Safety rules mirror ``FileModel::resolveUnderHome`` in the compiled Classic
Qt source: an existing directory whose *canonical* path stays inside the
user's home scope. Canonicalising before the containment check is what
rejects symlink escapes. No GUI, compositor or Mint claim is made here.
"""

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Optional, Union

__all__ = [
    "LAUNCH_ACTION",
    "REASON_HOME_UNAVAILABLE",
    "REASON_INVALID_PATH",
    "REASON_MISSING_DIRECTORY",
    "REASON_NOT_DIRECTORY",
    "REASON_OUTSIDE_HOME",
    "FileManagerIntent",
    "IntentRejected",
    "form_file_manager_intent",
]


LAUNCH_ACTION = "open-directory"

REASON_HOME_UNAVAILABLE = "home_unavailable"
REASON_INVALID_PATH = "invalid_path"
REASON_MISSING_DIRECTORY = "missing_directory"
REASON_NOT_DIRECTORY = "not_directory"
REASON_OUTSIDE_HOME = "outside_home"

_PathInput = Union[str, os.PathLike]


class IntentRejected(ValueError):
    """Candidate directory refused; ``reason`` is one of the REASON_* codes."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class FileManagerIntent:
    """Immutable launch description for one safe directory.

    ``uri`` is a percent-encoded ``file://`` URL built by ``Path.as_uri()``,
    so a host never needs to build a shell command from user input.
    """

    action: str
    uri: str
    directory: str

    def to_dict(self) -> dict:
        """Plain bounded mapping for a trusted host or QML bridge."""
        return {
            "action": self.action,
            "uri": self.uri,
            "directory": self.directory,
        }


def _canonical_home(home: Optional[_PathInput]) -> Path:
    """Resolve and validate the trust root before any candidate is read."""
    try:
        raw = Path.home() if home is None else Path(home).expanduser()
        root = raw.resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError):
        raise IntentRejected(REASON_HOME_UNAVAILABLE) from None
    if not root.is_dir():
        raise IntentRejected(REASON_HOME_UNAVAILABLE)
    return root


def _is_within(candidate: Path, root: Path) -> bool:
    """Path containment with the host's native case rules.

    ``relative_to`` is case-insensitive on Windows and case-sensitive on
    Linux, matching the Qt ``kCase`` choice in the Classic Files model.
    """
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def form_file_manager_intent(
    path: Optional[_PathInput] = None,
    *,
    home: Optional[_PathInput] = None,
) -> FileManagerIntent:
    """Build an intent for ``path``, or for ``home`` when path is empty.

    Relative paths are interpreted under ``home``, never the process working
    directory, so ``..`` cannot silently reach an unrelated location.
    Symlinks are followed before the containment check: a link pointing out
    of the home scope is refused, while a link staying inside is accepted.
    Raises ``IntentRejected`` with a stable reason on every refusal.
    """
    root = _canonical_home(home)

    if path is None:
        raw = ""
    elif isinstance(path, str):
        raw = path.strip()
    else:
        try:
            raw = os.fspath(path)
        except TypeError:
            raise IntentRejected(REASON_INVALID_PATH) from None

    try:
        candidate = root if not raw else Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
    except (RuntimeError, TypeError, ValueError):
        raise IntentRejected(REASON_INVALID_PATH) from None

    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, ValueError):
        raise IntentRejected(REASON_MISSING_DIRECTORY) from None
    except RuntimeError:
        raise IntentRejected(REASON_INVALID_PATH) from None

    if not _is_within(resolved, root):
        raise IntentRejected(REASON_OUTSIDE_HOME)
    if not resolved.is_dir():
        raise IntentRejected(REASON_NOT_DIRECTORY)

    return FileManagerIntent(
        action=LAUNCH_ACTION,
        uri=resolved.as_uri(),
        directory=str(resolved),
    )
