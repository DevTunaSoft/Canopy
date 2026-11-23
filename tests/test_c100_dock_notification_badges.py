"""Offline unit tests for bounded per-application dock unread badges.

No real Mint, compositor, Qt widget or OS notification source is exercised.
"""
from pathlib import Path
import unittest

from canopy_features.dock.notification_badges import (
    MAX_COUNT, MAX_TRUSTED_APPLICATIONS, BadgeError, NotificationBadges,
)


class NotificationBadgeTests(unittest.TestCase):
    def test_trusted_allowlist_and_bounded_registry(self):
        badges = NotificationBadges(["org.canopy.mail", "org.canopy.chat"])
        self.assertEqual(badges.trusted,
                         frozenset({"org.canopy.mail", "org.canopy.chat"}))
        with self.assertRaises(BadgeError):
            badges.set("org.untrusted.app", 1)
        with self.assertRaises(BadgeError):
            badges.count("org.untrusted.app")
        for bad in (None, "app", 5, True, {"a": 1}, iter(["a"])):
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(BadgeError):
                    NotificationBadges(bad)
        with self.assertRaises(BadgeError):
            NotificationBadges(["a"] * (MAX_TRUSTED_APPLICATIONS + 1))
        # Duplicates collapse; the allowlist size is still bounded.
        NotificationBadges(["app-%d" % i for i in range(MAX_TRUSTED_APPLICATIONS)])
        self.assertEqual(len(badges.trusted), 2)

    def test_malformed_application_ids_rejected(self):
        for bad in ("", ".leading", "-dash", "with space", "slash/app",
                    "a" * (MAX_TRUSTED_APPLICATIONS * 2), "é", "nul\x00byte",
                    None, 7, True, b"bytes", ("tuple",)):
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(BadgeError):
                    NotificationBadges([bad])

    def test_badge_count_bound_and_saturation_display(self):
        badges = NotificationBadges(["mail"], max_count=9)
        self.assertEqual(badges.set("mail", 1), 1)
        self.assertEqual(badges.display("mail"), "1")
        self.assertEqual(badges.set("mail", 9), 9)
        self.assertEqual(badges.display("mail"), "9+")
        self.assertEqual(badges.max_count, 9)
        for bad in (0, -1, MAX_COUNT + 1, True, 1.5):
            with self.subTest(bad=bad):
                with self.assertRaises(BadgeError):
                    NotificationBadges(["mail"], max_count=bad)

    def test_negative_counts_rejected(self):
        badges = NotificationBadges(["mail"])
        for value in (-1, -2, -(10 ** 12)):
            with self.subTest(value=value):
                with self.assertRaises(BadgeError):
                    badges.set("mail", value)
                with self.assertRaises(BadgeError):
                    badges.increment("mail", value)
                with self.assertRaises(BadgeError):
                    badges.decrement("mail", value)
        self.assertEqual(badges.count("mail"), 0)

    def test_huge_counts_clamped_without_unbounded_storage(self):
        badges = NotificationBadges(["mail"])
        self.assertEqual(badges.set("mail", 10 ** 12), MAX_COUNT)
        self.assertEqual(badges.count("mail"), MAX_COUNT)
        self.assertEqual(badges.display("mail"), "%d+" % MAX_COUNT)
        self.assertEqual(badges.set("mail", 10 ** 100), MAX_COUNT)
        self.assertEqual(badges.increment("mail", 10 ** 100), MAX_COUNT)
        self.assertEqual(badges.active_count(), 1)
        # A huge decrement floors at zero and releases the entry.
        self.assertEqual(badges.decrement("mail", 10 ** 100), 0)
        self.assertEqual(badges.active_count(), 0)
        self.assertEqual(badges.display("mail"), "")

    def test_malformed_counts_rejected(self):
        badges = NotificationBadges(["mail"])
        for bad in (None, "5", b"5", True, False, 1.5, 0.0,
                    float("nan"), float("inf"), float("-inf"),
                    [], {}, (1,), 3 + 0j):
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(BadgeError):
                    badges.set("mail", bad)
                with self.assertRaises(BadgeError):
                    badges.increment("mail", bad)
                with self.assertRaises(BadgeError):
                    badges.decrement("mail", bad)
        self.assertEqual(badges.count("mail"), 0)

    def test_increment_decrement_clear_and_zero(self):
        badges = NotificationBadges(["mail"])
        self.assertEqual(badges.increment("mail"), 1)
        self.assertEqual(badges.increment("mail", 4), 5)
        self.assertEqual(badges.decrement("mail", 2), 3)
        self.assertEqual(badges.decrement("mail", 99), 0)
        self.assertEqual(badges.count("mail"), 0)
        badges.clear("mail")  # idempotent
        badges.clear("mail")
        self.assertEqual(badges.active_count(), 0)
        self.assertEqual(badges.set("mail", 0), 0)
        self.assertEqual(badges.active_count(), 0)

    def test_snapshot_immutable_and_detached(self):
        badges = NotificationBadges(["mail", "chat"])
        badges.set("mail", 2)
        snap = badges.snapshot()
        with self.assertRaises(TypeError):
            snap["chat"] = 1
        badges.set("mail", 3)
        self.assertEqual(snap["mail"], 2)
        self.assertEqual(dict(badges.snapshot()), {"mail": 3})

    def test_no_polling_background_or_privileged_primitives(self):
        code = (Path(__file__).resolve().parents[1]
                / "canopy_features/dock/notification_badges.py").read_text()
        for token in ("QTimer", "Thread(", "subprocess", "import socket",
                      "time.sleep", "asyncio", "while True", "QApplication",
                      "import dbus", "requests", "urllib", "open("):
            with self.subTest(token=token):
                self.assertNotIn(token, code)


if __name__ == "__main__":
    unittest.main()
