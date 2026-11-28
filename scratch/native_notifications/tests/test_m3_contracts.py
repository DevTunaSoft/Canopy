"""SYNTHETIC contract tests for the M3 native notification/tray adapters.

These tests live under owned ``scratch/native_notifications/`` only. They use
finite hostile callers and trusted in-process sources; they do not touch a
D-Bus session, a daemon, the compiled shell, a VM or the public ``tests/``
suite. Run with:

    PYTHONPATH=<worktree> python -m unittest discover \
        -s scratch/native_notifications/tests -t . -v
"""
import ast
import pathlib
import unittest

from canopy_features.notifications.center_badge import (
    AVAILABLE as BADGE_AVAILABLE, UNAVAILABLE as BADGE_UNAVAILABLE,
    BadgeState, CenterBadgeError, NotificationCenterBadge,
)
from canopy_features.notifications.daemon_owner import (
    ACCEPT as OWNER_ACCEPT, ACCEPTED as OWNER_ACCEPTED,
    DaemonOwnerError, DaemonOwnerProof, OwnerState,
)
from canopy_features.notifications.freedesktop_notifications import (
    ACCEPT, AVAILABLE, BUS_NAME, CAPABILITIES_CALL,
    CLOSED_SIGNAL, CLOSE_CALL, INTERFACE, INVALID_NOTIFICATION_OBSERVATION,
    NOTIFY_CALL, NOTIFY_RETURN, OBJECT_PATH, OWNER_CHANGED, REFUSED,
    UNAVAILABLE, DeliveryEvidence, FreedesktopNotifications,
    NotificationContractError,
)
from canopy_features.notifications.host_snapshot_producer import (
    HostSnapshotProducer,
)
from canopy_features.notifications.tray_interaction import (
    ACCEPT as TRAY_ACCEPT, ACCEPTED as TRAY_ACCEPTED, BUS_NAME as TRAY_BUS,
    INVALID_TRAY_OBSERVATION, REFUSED as TRAY_REFUSED, OPEN_CENTER,
    TrayInteraction, TrayInteractionError, TrayState,
)

OWNER = ":1.22"


def fd_observation(member, identifier=None, owner=OWNER):
    return {"bus_name": BUS_NAME, "object_path": OBJECT_PATH,
            "interface": INTERFACE, "member": member, "owner": owner,
            "notification_id": identifier}


def complete_roundtrip(view, identifier=7, owner=OWNER):
    for member, ident in ((NOTIFY_CALL, None), (NOTIFY_RETURN, identifier),
                          (CLOSE_CALL, identifier),
                          (CLOSED_SIGNAL, identifier)):
        assert view.observe(fd_observation(member, ident, owner)) == ACCEPT


def owner_observation(**overrides):
    row = {"well_known_name": BUS_NAME, "owner": OWNER, "owner_pid": 5422,
           "owner_comm": "plasmashell", "foreign_daemon_count": 0,
           "canopy_daemon_count": 0, "activatable_service_files": 0}
    row.update(overrides)
    return row


def tray_observation(**overrides):
    row = {"facility": TRAY_BUS, "action": OPEN_CENTER,
           "acknowledged": True, "unique_name": OWNER}
    row.update(overrides)
    return row


class HostileMapping(dict):
    """Finite hostile mapping; the marker must never reach a state surface."""

    def items(self):
        raise RuntimeError("SECRET_MAPPER_MARKER")

    def keys(self):
        raise RuntimeError("SECRET_MAPPER_MARKER")

    def __len__(self):
        raise RuntimeError("SECRET_MAPPER_MARKER")


class FreedesktopContractTests(unittest.TestCase):
    def test_complete_roundtrip_is_available(self):
        view = FreedesktopNotifications()
        complete_roundtrip(view)
        evidence = view.evidence()
        self.assertEqual(evidence.status, AVAILABLE)
        self.assertEqual(evidence.reason, "none")
        self.assertEqual(evidence.matched_id, 7)
        self.assertTrue(evidence.owner_stable)
        self.assertEqual(evidence.call_count, 1)
        self.assertEqual(evidence.return_count, 1)
        self.assertEqual(evidence.close_count, 1)
        self.assertEqual(evidence.closed_count, 1)

    def test_incomplete_roundtrip_stays_unavailable(self):
        view = FreedesktopNotifications()
        view.observe(fd_observation(NOTIFY_CALL))
        view.observe(fd_observation(NOTIFY_RETURN, 7))
        evidence = view.evidence()
        self.assertEqual(evidence.status, UNAVAILABLE)
        self.assertEqual(evidence.reason, "incomplete_roundtrip")
        self.assertIsNone(evidence.matched_id)

    def test_capability_only_observation_never_claims_delivery(self):
        view = FreedesktopNotifications()
        self.assertEqual(view.observe(fd_observation(CAPABILITIES_CALL)),
                         ACCEPT)
        self.assertEqual(view.evidence().status, UNAVAILABLE)

    def test_wrong_service_identity_is_refused(self):
        view = FreedesktopNotifications()
        for field, value in (("bus_name", "org.fake.Notifications"),
                             ("object_path", "/org/fake/Notifications"),
                             ("interface", "org.fake.Interface")):
            row = fd_observation(NOTIFY_CALL)
            row[field] = value
            self.assertEqual(view.observe(row), REFUSED, field)
        self.assertEqual(view.evidence().refusal,
                         INVALID_NOTIFICATION_OBSERVATION)
        self.assertEqual(view.evidence().call_count, 0)

    def test_unknown_member_is_refused(self):
        view = FreedesktopNotifications()
        self.assertEqual(view.observe(fd_observation("Notify.hack")), REFUSED)
        self.assertEqual(view.evidence().call_count, 0)

    def test_owner_must_be_an_exact_unique_name(self):
        view = FreedesktopNotifications()
        for owner in ("", ":1.x", ":1", "1.22", ":1.22;rm", ":1." + "9" * 12,
                     123, None, True):
            self.assertEqual(view.observe(fd_observation(NOTIFY_CALL,
                                                         owner=owner)),
                             REFUSED, repr(owner))
        self.assertEqual(view.evidence().call_count, 0)

    def test_notification_id_rules_are_exact(self):
        view = FreedesktopNotifications()
        self.assertEqual(view.observe(fd_observation(NOTIFY_RETURN, True)),
                         REFUSED)
        for bad in (0, -1, 1 << 33, "7", None, 7.0):
            self.assertEqual(view.observe(fd_observation(NOTIFY_RETURN, bad)),
                             REFUSED, repr(bad))
        self.assertEqual(view.observe(fd_observation(NOTIFY_CALL, 7)), REFUSED)
        self.assertEqual(view.evidence().call_count, 0)

    def test_owner_change_is_refused_and_sticky(self):
        view = FreedesktopNotifications()
        complete_roundtrip(view, owner=":1.22")
        self.assertEqual(view.observe(fd_observation(NOTIFY_CALL,
                                                     owner=":1.99")), REFUSED)
        self.assertEqual(view.evidence().refusal, OWNER_CHANGED)
        self.assertEqual(view.observe(fd_observation(NOTIFY_CALL,
                                                     owner=":1.22")), REFUSED)
        self.assertEqual(view.evidence().status, UNAVAILABLE)

    def test_hostile_mapping_never_echoes_marker(self):
        view = FreedesktopNotifications()
        self.assertEqual(view.observe(HostileMapping()), REFUSED)
        text = repr(view.evidence().as_dict())
        self.assertNotIn("SECRET_MAPPER_MARKER", text)

    def test_wrong_containers_are_refused(self):
        view = FreedesktopNotifications()
        for value in (None, "", b"{}", 7, [], (), frozenset(), set()):
            self.assertEqual(view.observe(value), REFUSED, repr(value))

    def test_extra_or_missing_fields_are_refused(self):
        view = FreedesktopNotifications()
        row = fd_observation(NOTIFY_CALL)
        row["extra"] = "x"
        self.assertEqual(view.observe(row), REFUSED)
        row = fd_observation(NOTIFY_CALL)
        del row["member"]
        self.assertEqual(view.observe(row), REFUSED)

    def test_event_budget_is_bounded(self):
        view = FreedesktopNotifications(max_events=2)
        for _ in range(6):
            self.assertEqual(view.observe(fd_observation(NOTIFY_CALL)),
                             ACCEPT)
        self.assertEqual(view.evidence().call_count, 2)
        with self.assertRaises(NotificationContractError):
            FreedesktopNotifications(max_events=0)
        with self.assertRaises(NotificationContractError):
            FreedesktopNotifications(max_events=33)

    def test_state_is_frozen_and_snapshot_is_a_copy(self):
        view = FreedesktopNotifications()
        complete_roundtrip(view)
        evidence = view.evidence()
        self.assertIsInstance(evidence, DeliveryEvidence)
        with self.assertRaises(Exception):
            evidence.matched_id = 9
        copy = evidence.as_dict()
        copy["matched_id"] = 9
        self.assertEqual(view.evidence().matched_id, 7)

    def test_close_is_explicit_unavailable_and_idempotent(self):
        view = FreedesktopNotifications()
        complete_roundtrip(view)
        view.close()
        view.close()
        self.assertEqual(view.evidence().status, UNAVAILABLE)
        self.assertEqual(view.evidence().reason, "closed")
        self.assertIsNone(view.evidence().matched_id)
        with self.assertRaises(NotificationContractError):
            view.observe(fd_observation(NOTIFY_CALL))


class CenterBadgeTests(unittest.TestCase):
    def test_closed_badge_is_unavailable(self):
        badge = NotificationCenterBadge()
        badge.close()
        state = badge.state()
        self.assertEqual(state.status, BADGE_UNAVAILABLE)
        self.assertEqual(state.count, 0)
        self.assertEqual(state.label, "")

    def test_real_host_events_raise_bounded_badge(self):
        badge = NotificationCenterBadge()
        empty = badge.state()
        self.assertEqual(empty.status, BADGE_AVAILABLE)
        self.assertEqual(empty.count, 0)
        self.assertEqual(empty.label, "")
        producer = badge._producer
        producer.publish("session.state.changed", {"state": "active"})
        producer.publish("window.state.changed", {"window_count": 3})
        state = badge.state()
        self.assertEqual(state.status, BADGE_AVAILABLE)
        self.assertEqual(state.count, 2)
        self.assertEqual(state.label, "2")
        badge.close()

    def test_source_loss_gives_unavailable_zero_badge(self):
        badge = NotificationCenterBadge()
        badge._producer.close()
        state = badge.state()
        self.assertEqual(state.status, BADGE_UNAVAILABLE)
        self.assertEqual(state.count, 0)
        self.assertEqual(state.label, "")
        badge.close()
        badge.close()

    def test_injected_producer_is_not_closed_by_badge(self):
        producer = HostSnapshotProducer()
        badge = NotificationCenterBadge(producer=producer)
        badge.close()
        self.assertTrue(producer.connected())

    def test_untrusted_producer_is_refused(self):
        for value in ([], {}, "producer", 1, HostSnapshotProducer):
            with self.assertRaises(CenterBadgeError):
                NotificationCenterBadge(producer=value)

    def test_bad_bounds_are_refused(self):
        for value in (0, -1, 100, True, "9", 1.0):
            with self.assertRaises(CenterBadgeError):
                NotificationCenterBadge(max_badge=value)

    def test_state_is_frozen_and_copy_is_fresh(self):
        badge = NotificationCenterBadge()
        state = badge.state()
        self.assertIsInstance(state, BadgeState)
        with self.assertRaises(Exception):
            state.count = 99
        copy = state.as_dict()
        copy["count"] = 99
        self.assertEqual(badge.state().count, 0)
        badge.close()


class TrayInteractionTests(unittest.TestCase):
    def test_allowlisted_action_is_accepted(self):
        tray = TrayInteraction()
        self.assertEqual(tray.observe(tray_observation()), TRAY_ACCEPT)
        state = tray.state()
        self.assertEqual(state.status, TRAY_ACCEPTED)
        self.assertEqual(state.last_action, OPEN_CENTER)
        self.assertEqual(state.accepted_count, 1)
        self.assertIsInstance(state, TrayState)

    def test_unknown_action_is_refused(self):
        tray = TrayInteraction()
        for action in ("CLICK_EVERYTHING", "", "open_center", "OPEN_CENTER;",
                       None, 7):
            self.assertEqual(tray.observe(tray_observation(action=action)),
                             TRAY_REFUSED)
        self.assertEqual(tray.state().refusal, INVALID_TRAY_OBSERVATION)
        self.assertEqual(tray.state().accepted_count, 0)

    def test_acknowledgement_must_be_exact_true(self):
        tray = TrayInteraction()
        for value in (False, 1, "true", None, [], {}):
            self.assertEqual(tray.observe(tray_observation(acknowledged=value)),
                             TRAY_REFUSED)

    def test_wrong_facility_and_owner_are_refused(self):
        tray = TrayInteraction()
        self.assertEqual(tray.observe(tray_observation(facility=TRAY_BUS + "x")),
                         TRAY_REFUSED)
        for name in (":1", "1.22", ":1.22\n", "SECRET:1.22", None, 7):
            self.assertEqual(tray.observe(tray_observation(unique_name=name)),
                             TRAY_REFUSED)

    def test_hostile_mapping_never_echoes_marker(self):
        tray = TrayInteraction()
        self.assertEqual(tray.observe(HostileMapping()), TRAY_REFUSED)
        self.assertNotIn("SECRET_MAPPER_MARKER", repr(tray.state().as_dict()))

    def test_budget_and_close(self):
        tray = TrayInteraction(max_observations=2)
        self.assertEqual(tray.observe(tray_observation()), TRAY_ACCEPT)
        self.assertEqual(tray.observe(tray_observation()), TRAY_ACCEPT)
        self.assertEqual(tray.observe(tray_observation()), TRAY_REFUSED)
        tray.close()
        tray.close()
        self.assertEqual(tray.state().reason, "closed")
        self.assertIsNone(tray.state().last_action)
        with self.assertRaises(TrayInteractionError):
            tray.observe(tray_observation())
        with self.assertRaises(TrayInteractionError):
            TrayInteraction(max_observations=0)


class DaemonOwnerProofTests(unittest.TestCase):
    def test_real_guest_shape_is_single_upstream_owner(self):
        proof = DaemonOwnerProof()
        self.assertEqual(proof.observe(owner_observation()), OWNER_ACCEPT)
        state = proof.state()
        self.assertEqual(state.status, "single_upstream_owner")
        self.assertEqual(state.reason, "none")
        self.assertTrue(state.owner_verified)
        self.assertEqual(state.foreign_daemon_count, 0)
        self.assertEqual(state.canopy_daemon_count, 0)
        self.assertEqual(state.activatable_service_files, 0)
        self.assertEqual(state.probe_count, 1)
        self.assertIsInstance(state, OwnerState)

    def test_foreign_daemon_count_is_refused(self):
        proof = DaemonOwnerProof()
        self.assertEqual(proof.observe(owner_observation(
            foreign_daemon_count=1)), "refused")
        self.assertEqual(proof.state().status, "unavailable")

    def test_canopy_daemon_or_service_file_is_refused(self):
        for field in ("canopy_daemon_count", "activatable_service_files"):
            proof = DaemonOwnerProof()
            self.assertEqual(proof.observe(owner_observation(**{field: 1})),
                             "refused", field)
            self.assertFalse(proof.state().owner_verified)

    def test_wrong_owner_comm_is_refused(self):
        proof = DaemonOwnerProof()
        for comm in ("dunst", "notification-daemon", "python3", "",
                     "plasmashell\n", 7):
            self.assertEqual(proof.observe(owner_observation(owner_comm=comm)),
                             "refused", repr(comm))

    def test_wrong_name_pid_and_missing_fields_are_refused(self):
        proof = DaemonOwnerProof()
        self.assertEqual(proof.observe(owner_observation(
            well_known_name="org.fake.Notifications")), "refused")
        for pid in (0, -1, True, "5422", None, 1 << 32):
            self.assertEqual(proof.observe(owner_observation(owner_pid=pid)),
                             "refused", repr(pid))
        row = owner_observation()
        del row["owner_comm"]
        self.assertEqual(proof.observe(row), "refused")

    def test_owner_change_and_budget_are_refused(self):
        proof = DaemonOwnerProof()
        self.assertEqual(proof.observe(owner_observation()), OWNER_ACCEPT)
        self.assertEqual(proof.observe(owner_observation(owner=":1.99")),
                         "refused")
        self.assertFalse(proof.state().owner_verified)
        bounded = DaemonOwnerProof(max_probes=2)
        bounded.observe(owner_observation())
        bounded.observe(owner_observation())
        self.assertEqual(bounded.observe(owner_observation()), "refused")
        self.assertEqual(bounded.state().probe_count, 2)
        with self.assertRaises(DaemonOwnerError):
            DaemonOwnerProof(max_probes=9)

    def test_hostile_mapping_and_close(self):
        proof = DaemonOwnerProof()
        self.assertEqual(proof.observe(HostileMapping()), "refused")
        self.assertNotIn("SECRET_MAPPER_MARKER", repr(proof.state().as_dict()))
        proof.close()
        proof.close()
        self.assertEqual(proof.state().reason, "closed")
        with self.assertRaises(DaemonOwnerError):
            proof.observe(owner_observation())


class SourceIntegrityTests(unittest.TestCase):
    MODULES = ("freedesktop_notifications.py", "center_badge.py",
               "tray_interaction.py", "daemon_owner.py")
    FORBIDDEN_IMPORTS = frozenset({
        "os", "socket", "subprocess", "threading", "asyncio", "gi",
        "dbus", "pydbus", "dbus_fast", "PyQt5", "PySide6", "requests",
        "shutil", "tempfile",
    })
    FORBIDDEN_LITERALS = (
        "app.catalog.changed", "window.state.changed",
        "session.state.changed", "capabilities.report", "RequestName",
        "gdbus", "xdotool", "plasmashell --", "pgrep",
        "org.freedesktop.DBus.StartServiceByName",
    )

    def test_new_modules_have_no_transport_execution_or_new_topics(self):
        root = pathlib.Path(__file__).resolve().parents[3]
        for name in self.MODULES:
            path = root / "canopy_features" / "notifications" / name
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=name)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn(alias.name.split(".")[0],
                                         self.FORBIDDEN_IMPORTS, name)
                if isinstance(node, ast.ImportFrom) and node.module:
                    self.assertNotIn(node.module.split(".")[0],
                                     self.FORBIDDEN_IMPORTS, name)
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    for literal in self.FORBIDDEN_LITERALS:
                        self.assertNotIn(literal, node.value, (name, literal))


if __name__ == "__main__":
    unittest.main()
