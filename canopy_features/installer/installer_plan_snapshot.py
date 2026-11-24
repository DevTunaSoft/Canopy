"""Pure, immutable composition of offline installer planning decisions.

This module records what four already-tested installer helpers *decide* about
host-supplied planning inputs, without performing any of the work they plan:

* ``icon_cache_optin`` -- user-scoped icon-cache description (tool lookup is
  injected by the caller; this module never searches PATH),
* ``xdg_user_paths`` -- lexical XDG base resolution for a relative target,
* ``uninstall_integrity`` -- ownership-manifest normalization,
* ``session_entry_validation`` -- textual session-entry metadata shape.

Only fixed status tokens and a bounded file count reach the frozen record. No
path, command, environment value, manifest entry or entry text is echoed into
the record or an error. This is NOT proof that any file exists, that a binary
is executable, that an uninstall is safe to execute, that a session was
registered or that a package was installed: those are hardcoded negative
claims. Nothing is written, launched, mounted, installed or registered here,
and no visual or pack code is imported.

Malformed bounded wrapper shape fails closed with :class:`SnapshotError`;
rejections by a composing validator become fixed status tokens.
"""
from dataclasses import dataclass
from pathlib import Path

from canopy_features.installer import icon_cache_optin as icon_mod
from canopy_features.installer import session_entry_validation as session_mod
from canopy_features.installer import uninstall_integrity as uninstall_mod
from canopy_features.installer import xdg_user_paths as xdg_mod

SCHEMA = 1
TOP_KEYS = frozenset({
    "schema", "home", "xdg_home", "icon_dirs", "tool_available",
    "xdg_kind", "xdg_relative", "env", "ownership_manifest", "session_entry_text",
})

ICON_STATUSES = frozenset({"AVAILABLE", "UNAVAILABLE", "REFUSED", "INVALID"})
XDG_STATUSES = frozenset({"WITHIN_HOME", "OUTSIDE_HOME", "INVALID"})
OWNERSHIP_STATUSES = frozenset({"VALID", "INVALID"})
SESSION_STATUSES = frozenset({"VALID", "INVALID"})

MAX_HOME_CHARS = 512
MAX_RELATIVE_CHARS = 256
MAX_ENV_ENTRIES = 64
MAX_ENV_CHARS = 512
MAX_OWNED_FILES = 8192

# Injected lookup result: a fixed, non-privileged tool path. It is never
# echoed into the report and no PATH search or filesystem access is performed.
_TOOL_PATH = "/usr/bin/" + icon_mod.CACHE_TOOL


class SnapshotError(ValueError):
    """Malformed, unbounded or unrecognized installer planning input."""


def _bounded_int(value, label, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise SnapshotError("installer snapshot " + label + " is invalid")
    return value


def _text(value, label, maximum):
    if type(value) is not str or not value or len(value) > maximum:
        raise SnapshotError("installer snapshot " + label + " is invalid")
    return value


def _icon_status(home, icon_dirs, tool_available):
    def lookup(name):
        if name != icon_mod.CACHE_TOOL:
            return None
        return _TOOL_PATH if tool_available else None

    try:
        description = icon_mod.describe_refresh(home, icon_dirs, tool_lookup=lookup)
    except icon_mod.PrivilegedRefreshRefused:
        return "REFUSED"
    except icon_mod.IconCacheDescriptionError:
        return "INVALID"
    if description.reason == "TOOL_AVAILABLE":
        return "AVAILABLE"
    if description.reason == "TOOL_MISSING":
        return "UNAVAILABLE"
    raise SnapshotError("unsupported icon description reason")


def _xdg_status(kind, relative, xdg_home, env):
    # The XDG helper needs a NATIVE absolute home; the icon helper needs a
    # POSIX one. Callers supply both explicitly so no environment is read.
    try:
        base = xdg_mod.base_dir(kind, home=xdg_home, env=env)
        parts = Path(relative).parts
        if not parts or ".." in parts:
            return "INVALID"
        candidate = base.joinpath(*parts)
    except (xdg_mod.UnsafeXdgPath, TypeError, ValueError, OSError):
        return "INVALID"
    try:
        candidate.relative_to(Path(xdg_home))
    except ValueError:
        # Lexically outside the user's home: a distinct, fixed planning token.
        return "OUTSIDE_HOME"
    return "WITHIN_HOME"


def _ownership(manifest):
    if type(manifest) is not dict:
        return "INVALID", 0
    files = manifest.get("files")
    if isinstance(files, dict) and len(files) > MAX_OWNED_FILES:
        return "INVALID", 0
    try:
        normalized = uninstall_mod.normalize_manifest(manifest)
    except uninstall_mod.UninstallIntegrityError:
        return "INVALID", 0
    count = len(normalized["files"])
    if type(count) is not int or not 0 <= count <= MAX_OWNED_FILES:
        raise SnapshotError("unsupported ownership file count")
    return "VALID", count


def _session_status(text):
    try:
        fields = session_mod._parse(text)
        session_mod._clean_string(fields["Name"], "Name", session_mod.MAX_NAME_CHARS)
        session_mod._safe_exec_path(fields["Exec"])
        if "Comment" in fields:
            session_mod._clean_string(
                fields["Comment"], "Comment", session_mod.MAX_COMMENT_CHARS)
        if "Icon" in fields:
            session_mod._clean_string(
                fields["Icon"], "Icon", session_mod.MAX_ICON_CHARS)
    except (session_mod.SessionEntryError, KeyError, TypeError, ValueError):
        return "INVALID"
    return "VALID"


@dataclass(frozen=True)
class InstallerPlanSnapshot:
    """Frozen, value-free record of four offline planning decisions."""

    schema: int
    icon_status: str
    xdg_status: str
    ownership_status: str
    ownership_file_count: int
    session_status: str

    def as_dict(self):
        """Return a fresh copy with a fixed token and hardcoded negative claims.

        Type-checks precede every frozenset membership so unhashable wrong
        types cannot leak a raw TypeError past this fail-closed boundary.
        """
        _bounded_int(self.schema, "schema", SCHEMA, SCHEMA)
        if type(self.icon_status) is not str or self.icon_status not in ICON_STATUSES:
            raise SnapshotError("unsupported icon status token")
        if type(self.xdg_status) is not str or self.xdg_status not in XDG_STATUSES:
            raise SnapshotError("unsupported XDG status token")
        if (type(self.ownership_status) is not str
                or self.ownership_status not in OWNERSHIP_STATUSES):
            raise SnapshotError("unsupported ownership status token")
        if (type(self.session_status) is not str
                or self.session_status not in SESSION_STATUSES):
            raise SnapshotError("unsupported session status token")
        _bounded_int(self.ownership_file_count, "ownership file count",
                     0, MAX_OWNED_FILES)
        return {
            "status": "PLAN_SNAPSHOT",
            "schema": SCHEMA,
            "icon_status": self.icon_status,
            "xdg_status": self.xdg_status,
            "ownership_status": self.ownership_status,
            "ownership_file_count": self.ownership_file_count,
            "session_status": self.session_status,
            "filesystem_verified": False,
            "binary_verified": False,
            "uninstall_executed": False,
            "session_registered": False,
            "package_installed": False,
            "release_approved": False,
            "linux_mint_acceptance_proven": False,
            "owner_visual_approval": False,
        }


def snapshot(record):
    """Validate the bounded wrapper, then compose the four pure decisions."""
    if type(record) is not dict or frozenset(record) != TOP_KEYS:
        raise SnapshotError("installer snapshot has an unexpected key set")
    _bounded_int(record["schema"], "schema", SCHEMA, SCHEMA)
    home = _text(record["home"], "home", MAX_HOME_CHARS)
    xdg_home = _text(record["xdg_home"], "xdg home", MAX_HOME_CHARS)
    dirs = record["icon_dirs"]
    if (type(dirs) not in (list, tuple)
            or len(dirs) > icon_mod.MAX_THEME_DIRS):
        raise SnapshotError("installer snapshot icon directories are invalid")
    tool_available = record["tool_available"]
    if type(tool_available) is not bool:
        raise SnapshotError("installer snapshot tool_available must be boolean")
    kind = _text(record["xdg_kind"], "xdg kind", MAX_HOME_CHARS)
    relative = _text(record["xdg_relative"], "xdg relative", MAX_RELATIVE_CHARS)
    env = record["env"]
    if type(env) is not dict or len(env) > MAX_ENV_ENTRIES:
        raise SnapshotError("installer snapshot env is invalid or unbounded")
    for key, value in env.items():
        if (type(key) is not str or type(value) is not str
                or len(key) > MAX_ENV_CHARS or len(value) > MAX_ENV_CHARS):
            raise SnapshotError("installer snapshot env entry is invalid")
    entry_text = record["session_entry_text"]
    if type(entry_text) is not str or len(entry_text) > session_mod.MAX_ENTRY_BYTES:
        raise SnapshotError("installer snapshot session entry text is invalid")

    ownership_status, count = _ownership(record["ownership_manifest"])
    return InstallerPlanSnapshot(
        schema=SCHEMA,
        icon_status=_icon_status(home, dirs, tool_available),
        xdg_status=_xdg_status(kind, relative, xdg_home, env),
        ownership_status=ownership_status,
        ownership_file_count=count,
        session_status=_session_status(entry_text),
    )
