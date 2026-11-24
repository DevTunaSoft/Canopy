"""Agent A regression: bounded workspace identifiers survive hostile re-decisions.

Covers the idempotence/monotonicity contract for a sequence of well-formed but
hostile snapshots: oversized bounded text in a workspace identifier must be
truncated in the projection (as it already is for names, reasons and focus
targets), and repeated stale/stale-newer generations must not leak it.
"""

import json
from pathlib import Path
import unittest
from types import MappingProxyType

from canopy_features.windows import switcher_state as switcher
from canopy_features.windows import wayland_portal_capabilities as portal
from canopy_features.windows import window_session_snapshot as snapshot
from canopy_features.windows import window_state_capabilities as wsc
from canopy_features.windows import workspace_inventory as inventory

FEATURES = wsc.WindowStateFeature
SEV = {"OK": 0, "ATTENTION": 1, "BLOCKED": 2}
OVERSIZE = "id-" + ("x" * (snapshot.MAX_CHARS * 2 + 1))


def _plain(value):
    if isinstance(value, MappingProxyType):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_plain(item) for item in value)
    return value


def _encode(record):
    return json.dumps(_plain(record.to_dict()), sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _switcher():
    return switcher.SwitchState(False, None, None, (1, 2, 3))


def _workspace(identifier="alpha"):
    workspaces = (inventory.Workspace(identifier, "Name", "test"),)
    return inventory.WorkspaceInventory(workspaces, ())


def _portal(denied=False):
    if denied:
        return portal.describe(
            "wayland", ("remote_desktop",),
            {"remote_desktop": "denied"})
    return portal.describe(
        "wayland", ("remote_desktop", "screen_cast"),
        {"remote_desktop": "granted", "screen_cast": "granted"})


def _negotiation(unsupported=False):
    if unsupported:
        return wsc.negotiate("headless", [FEATURES.MINIMIZE])
    return wsc.negotiate(
        "x11", [FEATURES.MINIMIZE, FEATURES.MAXIMIZE, FEATURES.RESTORE])


def _compose(identifier="alpha", denied=False, unsupported=False):
    return snapshot.compose(
        _switcher(), _workspace(identifier), _portal(denied),
        _negotiation(unsupported))


class WindowSessionSnapshotIdentifierBoundTests(unittest.TestCase):
    def test_oversized_workspace_identifier_is_truncated(self):
        record = _compose(OVERSIZE)
        self.assertEqual(record.workspace.workspace_count, 1)
        self.assertEqual(record.workspace.identifiers,
                         (OVERSIZE[:snapshot.MAX_CHARS],))
        self.assertLessEqual(len(record.workspace.identifiers[0]),
                             snapshot.MAX_CHARS)

    def test_hostile_identifier_cannot_enlarge_encoded_record(self):
        encoded = _encode(_compose(OVERSIZE))
        canonical = _encode(_compose(OVERSIZE[:snapshot.MAX_CHARS]))
        self.assertNotIn(OVERSIZE.encode("utf-8"), encoded)
        self.assertEqual(encoded, canonical)

    def test_repeated_stale_generations_stay_bounded_and_idempotent(self):
        clean = _encode(_compose("alpha"))
        stale_newer = _encode(_compose(OVERSIZE, denied=True))
        replay_clean = _encode(_compose("alpha"))
        replay_stale_newer = _encode(_compose(OVERSIZE, denied=True))
        self.assertEqual(replay_clean, clean)
        self.assertEqual(replay_stale_newer, stale_newer)
        self.assertNotEqual(stale_newer, clean)
        record = _compose(OVERSIZE, denied=True)
        self.assertLessEqual(len(record.workspace.identifiers[0]),
                             snapshot.MAX_CHARS)

    def test_valid_identifier_is_preserved(self):
        identifier = "id-" + "y" * (snapshot.MAX_CHARS - 3)
        self.assertEqual(_compose(identifier).workspace.identifiers,
                         (identifier,))

    def test_wrong_identifier_type_fails_closed_on_redecision(self):
        workspaces = (inventory.Workspace(None, "Name", "test"),)  # type: ignore[arg-type]
        bad = inventory.WorkspaceInventory(workspaces, ())
        for _ in range(2):
            with self.assertRaises(snapshot.SnapshotError):
                snapshot.compose(
                    _switcher(), bad, _portal(), _negotiation())

    def test_status_never_de_escalates_under_repeated_denials(self):
        clean = _compose("alpha")
        denied = _compose("alpha", denied=True)
        denied_again = _compose("alpha", denied=True)
        blocked = _compose(OVERSIZE, denied=True, unsupported=True)
        self.assertLess(SEV[clean.status], SEV[denied.status])
        self.assertEqual(denied.status, denied_again.status)
        self.assertEqual(blocked.status, denied.status)
        self.assertTrue(blocked.is_blocked)

    def test_module_stays_pure(self):
        source = Path(snapshot.__file__).read_text(encoding="utf-8")
        self.assertNotIn("open(", source)
        self.assertNotIn("subprocess", source)


if __name__ == "__main__":
    unittest.main()
