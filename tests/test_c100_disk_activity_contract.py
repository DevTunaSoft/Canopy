"""Targeted synthetic tests for the bounded disk-activity contract.

No test touches a real disk, clock, thread, timer or host path. The module under
test only produces immutable write intents; a host must execute any write.
"""
import unittest

from canopy_features.reliability import disk_activity_contract as dac


class CoalescingTests(unittest.TestCase):
    def test_repeated_marks_emit_one_latest_write_on_explicit_flush(self):
        controller = dac.DiskWriteCoalescer(
            (dac.WriteTarget("launcher_catalog", 64),))

        first = controller.mark_dirty("launcher_catalog", b"first")
        second = controller.mark_dirty("launcher_catalog", b"second")
        third = controller.mark_dirty("launcher_catalog", b"third")

        self.assertFalse(first.coalesced)
        self.assertTrue(second.coalesced)
        self.assertTrue(third.coalesced)
        intents = controller.flush()
        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0].target, "launcher_catalog")
        self.assertEqual(intents[0].payload, b"third")
        self.assertEqual(controller.flush(), ())
        snapshot = controller.snapshot()
        self.assertEqual(snapshot.pending_count, 0)
        self.assertEqual(snapshot.coalesced_count, 2)
        self.assertEqual(snapshot.flush_count, 1)


class ExplicitControlTests(unittest.TestCase):
    def setUp(self):
        self.controller = dac.DiskWriteCoalescer((
            dac.WriteTarget("launcher_catalog", 64),
            dac.WriteTarget("icon_cache", 64),
        ))

    def test_selective_flush_emits_only_named_pending_target(self):
        self.controller.mark_dirty("launcher_catalog", b"catalog")
        self.controller.mark_dirty("icon_cache", b"icons")

        first = self.controller.flush(("icon_cache",))

        self.assertEqual(len(first), 1)
        self.assertEqual(first[0].target, "icon_cache")
        self.assertEqual(first[0].payload, b"icons")
        self.assertEqual(self.controller.snapshot().pending_targets,
                         ("launcher_catalog",))
        second = self.controller.flush()
        self.assertEqual(len(second), 1)
        self.assertEqual(second[0].target, "launcher_catalog")
        self.assertEqual(second[0].payload, b"catalog")

    def test_invalidate_drops_pending_without_emitting_a_write(self):
        self.controller.mark_dirty("launcher_catalog", b"catalog")

        dropped = self.controller.invalidate("launcher_catalog")

        self.assertTrue(dropped)
        self.assertEqual(self.controller.flush(), ())
        self.assertEqual(self.controller.snapshot().invalidated_count, 1)
        self.controller.mark_dirty("launcher_catalog", b"fresh")
        self.assertEqual(len(self.controller.flush()), 1)

    def test_invalidate_all_clears_every_pending_target(self):
        self.controller.mark_dirty("launcher_catalog", b"catalog")
        self.controller.mark_dirty("icon_cache", b"icons")

        dropped = self.controller.invalidate_all()

        self.assertEqual(dropped, 2)
        self.assertEqual(self.controller.flush(), ())
        self.assertEqual(self.controller.snapshot().pending_count, 0)
        self.assertEqual(self.controller.snapshot().invalidated_count, 2)


class BoundsTests(unittest.TestCase):
    def test_oversized_payload_is_refused_without_changing_pending_state(self):
        controller = dac.DiskWriteCoalescer(
            (dac.WriteTarget("launcher_catalog", 8),))
        controller.mark_dirty("launcher_catalog", b"12345678")

        with self.assertRaises(dac.DiskActivityError):
            controller.mark_dirty("launcher_catalog", b"123456789")

        self.assertEqual(controller.flush()[0].payload, b"12345678")
        self.assertEqual(controller.snapshot().coalesced_count, 0)

    def test_bounded_target_count_refuses_extra_targets(self):
        targets = tuple(dac.WriteTarget("target_%02d" % index, 8)
                        for index in range(dac.MAX_TARGETS))
        dac.DiskWriteCoalescer(targets)

        with self.assertRaises(dac.DiskActivityError):
            dac.DiskWriteCoalescer(targets + (dac.WriteTarget("extra", 8),))

    def test_pending_payload_total_is_bounded(self):
        targets = tuple(dac.WriteTarget("target_%02d" % index,
                                        dac.MAX_PAYLOAD_BYTES)
                        for index in range(5))
        controller = dac.DiskWriteCoalescer(targets)
        for index in range(4):
            controller.mark_dirty("target_%02d" % index,
                                  b"x" * dac.MAX_PAYLOAD_BYTES)

        with self.assertRaises(dac.DiskActivityError):
            controller.mark_dirty("target_04", b"x" * dac.MAX_PAYLOAD_BYTES)

        self.assertEqual(controller.snapshot().pending_bytes,
                         4 * dac.MAX_PAYLOAD_BYTES)

    def test_hostile_types_and_names_fail_closed(self):
        controller = dac.DiskWriteCoalescer(
            (dac.WriteTarget("launcher_catalog", 64),))
        for payload in (None, True, 7, "text", bytearray(b"bytes"), b""):
            with self.assertRaises(dac.DiskActivityError):
                controller.mark_dirty("launcher_catalog", payload)
        for name in (None, True, 7, b"launcher_catalog", ["launcher_catalog"]):
            with self.assertRaises(dac.DiskActivityError):
                controller.mark_dirty(name, b"payload")
        for name in ("", "Bad", "with space", "../escape",
                     "a" * (dac.MAX_NAME_CHARS + 1), "line\nbreak"):
            with self.assertRaises(dac.DiskActivityError):
                dac.WriteTarget(name, 64)
        for cap in (True, 0, -1, dac.MAX_PAYLOAD_BYTES + 1, 8.0):
            with self.assertRaises(dac.DiskActivityError):
                dac.WriteTarget("launcher_catalog", cap)
        self.assertEqual(controller.snapshot().pending_count, 0)

    def test_generation_and_counts_saturate_within_fixed_ceilings(self):
        controller = dac.DiskWriteCoalescer(
            (dac.WriteTarget("launcher_catalog", 8),))
        for _ in range(dac.GENERATION_CEILING + 5):
            controller.mark_dirty("launcher_catalog", b"x")

        intent = controller.flush()[0]
        snapshot = controller.snapshot()
        self.assertEqual(intent.generation, dac.GENERATION_CEILING)
        self.assertEqual(snapshot.coalesced_count, dac.COUNTER_CEILING)
        self.assertEqual(snapshot.flush_count, 1)


class NoPollingContractTests(unittest.TestCase):
    def test_module_source_has_no_clock_timer_thread_or_io(self):
        source = __import__("pathlib").Path(dac.__file__).read_text(encoding="utf-8")
        for token in ("import time", "import threading", "import asyncio",
                      "import sched", "import os", "from pathlib", "sleep(",
                      "while True", "open(", "Timer(", "setInterval",
                      "setTimeout", "subprocess"):
            self.assertNotIn(token, source, "forbidden mechanism: " + token)

    def test_fixed_negative_claims_are_emitted(self):
        controller = dac.DiskWriteCoalescer(
            (dac.WriteTarget("launcher_catalog", 64),))
        controller.mark_dirty("launcher_catalog", b"PE070_PAYLOAD_MARKER")
        snapshot = controller.snapshot()
        self.assertEqual(snapshot.claims, dac.FIXED_CLAIMS)
        self.assertIn("no_polling", dac.FIXED_CLAIMS)
        self.assertIn("no_filesystem_io", dac.FIXED_CLAIMS)
        self.assertIn("no_timers", dac.FIXED_CLAIMS)

    def test_snapshot_diagnostics_never_echo_payload_bytes(self):
        controller = dac.DiskWriteCoalescer(
            (dac.WriteTarget("launcher_catalog", 64),))
        controller.mark_dirty("launcher_catalog", b"PE070_PAYLOAD_MARKER")

        rendered = repr(controller.snapshot()) + repr(controller.snapshot().to_dict())

        self.assertNotIn("PE070_PAYLOAD_MARKER", rendered)


if __name__ == "__main__":
    unittest.main()
