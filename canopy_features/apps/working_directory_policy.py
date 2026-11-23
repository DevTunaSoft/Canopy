"""Offline policy check for application-launch working directories.

Pure evaluation only. No process is launched, no sockets or services are
created, and no polling or background work runs. Host code supplies the
inherited current directory and an injected read-only filesystem view; this
module returns a bounded decision that a launcher can act on.

This is a point-in-time check, not a sandbox. Filesystem state can change
between check and launch (TOCTOU); the launcher must use the returned
resolved path and keep its own launch allowlist.
"""
import os
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath

MAX_PATH_CHARS = 4096
MAX_ROOTS = 32

# An injected filesystem view can report an unusable path (symlink loop,
# undecodable encoding, malformed argument) with any of these faults. They all
# mean "containment cannot be established" and must collapse to a REJECTED
# decision rather than escape this pure evaluator.
_VIEW_FAULTS = (OSError, RuntimeError, TypeError, ValueError)

_ALLOWED = "ALLOWED"
_REJECTED = "REJECTED"


class WorkingDirectoryPolicyError(ValueError):
    """Invalid policy configuration, not a rejected launch request."""


@dataclass(frozen=True)
class Decision:
    status: str
    reason: str
    path: object = None

    @property
    def allowed(self):
        return self.status == _ALLOWED


def _reject(reason):
    return Decision(_REJECTED, reason)


class SystemFilesystem:
    """Read-only host filesystem view. No state, cache, I/O at import time."""

    def is_directory(self, path):
        return os.path.isdir(path)

    def resolve(self, path):
        return os.path.realpath(path)


class WorkingDirectoryPolicy:
    """Evaluate one launch working-directory request against allowed roots.

    ``allowed_roots`` must be absolute paths. ``requested=None`` means the
    launch would inherit the host's current directory. ``flavor`` selects
    path syntax; it defaults to the host platform.
    """

    def __init__(self, allowed_roots, *, filesystem=None, flavor=None):
        if flavor is None:
            flavor = "windows" if os.name == "nt" else "posix"
        if flavor == "posix":
            self._path_type = PurePosixPath
        elif flavor == "windows":
            self._path_type = PureWindowsPath
        else:
            raise WorkingDirectoryPolicyError("unsupported path flavor")

        if isinstance(allowed_roots, (str, bytes)) or not isinstance(
                allowed_roots, (tuple, list)):
            raise WorkingDirectoryPolicyError("allowed_roots must be a sequence")
        if not 1 <= len(allowed_roots) <= MAX_ROOTS:
            raise WorkingDirectoryPolicyError("invalid allowed-roots count")
        roots = []
        for root in allowed_roots:
            if not self._valid_string(root) or not self._path_type(root).is_absolute():
                raise WorkingDirectoryPolicyError(
                    "each allowed root must be an absolute path")
            roots.append(root)
        self._roots = tuple(roots)

        if filesystem is None:
            filesystem = SystemFilesystem()
        if not all(callable(getattr(filesystem, name, None))
                   for name in ("is_directory", "resolve")):
            raise WorkingDirectoryPolicyError("filesystem view is incomplete")
        self._filesystem = filesystem

    @staticmethod
    def _valid_string(value):
        return (isinstance(value, str) and 0 <= len(value) <= MAX_PATH_CHARS
                and "\x00" not in value)

    def _canonical(self, path):
        """Resolve symlinks; return None if the result is unusable.

        Any filesystem-view fault means containment cannot be established, so
        it is treated as an unusable result and the caller rejects fail-closed.
        """
        try:
            resolved = self._filesystem.resolve(path)
        except _VIEW_FAULTS:
            return None
        if not self._valid_string(resolved):
            return None
        resolved_path = self._path_type(resolved)
        if not resolved_path.is_absolute() or ".." in resolved_path.parts:
            return None
        return resolved

    def _within_roots(self, resolved):
        candidate = self._path_type(resolved)
        for root in self._roots:
            base_value = self._canonical(root)
            if base_value is None:
                continue
            base = self._path_type(base_value)
            if candidate == base or base in candidate.parents:
                return True
        return False

    def evaluate(self, requested, inherited):
        """Return a Decision for one requested directory and inherited cwd."""
        if (not self._valid_string(inherited)
                or not self._path_type(inherited).is_absolute()):
            raise WorkingDirectoryPolicyError("inherited cwd must be absolute")

        inherit = requested is None
        if not inherit and not self._valid_string(requested):
            return _reject("INVALID_REQUEST")

        candidate = inherited if inherit else requested
        if not self._path_type(candidate).is_absolute():
            return _reject("RELATIVE_PATH")
        if ".." in self._path_type(candidate).parts:
            return _reject("UNSAFE_INHERITANCE" if inherit else "PATH_TRAVERSAL")

        unsafe = "UNSAFE_INHERITANCE" if inherit else None
        try:
            is_directory = self._filesystem.is_directory(candidate)
        except _VIEW_FAULTS:
            is_directory = False
        if not is_directory:
            return _reject(unsafe or "MISSING_DIRECTORY")

        resolved = self._canonical(candidate)
        if resolved is None or not self._within_roots(resolved):
            return _reject(unsafe or "OUTSIDE_ALLOWED_ROOT")
        return Decision(_ALLOWED, "OK", resolved)
