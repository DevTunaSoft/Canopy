"""Regression tests: embedded frame-pacing flags must agree with snapshot negatives.

A frozen ``FramePacingReport`` can be constructed directly, bypassing the
hardcoded negatives in ``parse_frame_times``.  Because the snapshot embeds the
caller's report verbatim, a forged positive measurement flag was published next
to the snapshot's ``real_hardware_measured=False`` claim -- a contradictory
passing/failing flag pair and a false performance-safe claim.  These tests pin
the cross-field contract.
"""
import json
import unittest
from dataclasses import asdict

from canopy_features.performance.frame_pacing import (
    FramePacingReport, parse_frame_times,
)
from canopy_features.performance.performance_snapshot import (
    NOT_ESTABLISHED, SnapshotError, compose_snapshot,
)


def genuine_fields():
    return asdict(parse_frame_times([16.7, 16.8, 33.4], refresh_hz=60))


def forged_report(**overrides):
    fields = genuine_fields()
    fields.update(overrides)
    return FramePacingReport(**fields)


class FramePacingFlagContradictionTests(unittest.TestCase):
    def test_real_gpu_measurement_flag_contradiction_fails_closed(self):
        # A caller-built report can set the flag that parse_frame_times always
        # leaves False.  Publishing it beside real_hardware_measured=False is
        # a contradictory passing/failing flag pair.
        report = forged_report(real_gpu_measurement=True)
        with self.assertRaises(SnapshotError):
            compose_snapshot(frame_pacing=report)

    def test_real_gpu_source_label_contradiction_fails_closed(self):
        # The source label is the other half of the same positive measurement
        # claim: it must stay the offline-parse label, never a real capture.
        report = forged_report(measurement_source="real_gpu_capture")
        with self.assertRaises(SnapshotError):
            compose_snapshot(frame_pacing=report)

    def test_genuine_report_still_publishes_negative_claims(self):
        snap = compose_snapshot(frame_pacing=parse_frame_times([16.7]))
        projected = snap.as_dict()
        self.assertIs(projected["frame_pacing"]["real_gpu_measurement"], False)
        self.assertIs(projected["measurement_performed"], False)
        self.assertIs(projected["real_hardware_measured"], False)
        self.assertEqual(projected["linux_mint_acceptance"], NOT_ESTABLISHED)
        self.assertEqual(projected["owner_visual_approval"], NOT_ESTABLISHED)

    def test_subclass_as_dict_override_cannot_inject_positive_flags(self):
        # isinstance() still accepts a subclass, but the snapshot's projection
        # must come from the validated dataclass fields, not an overridable
        # method that can add forged claim fields to the nested evidence.
        class Forged(FramePacingReport):
            def as_dict(self):
                return dict(super().as_dict(),
                            real_hardware_measured=True,
                            measurement_performed=True,
                            linux_mint_acceptance="APPROVED",
                            owner_visual_approval="APPROVED")

        snap = compose_snapshot(frame_pacing=Forged(**genuine_fields()))
        projected = snap.as_dict()
        frame = projected["frame_pacing"]
        for key in ("real_hardware_measured", "measurement_performed",
                    "linux_mint_acceptance", "owner_visual_approval"):
            self.assertNotIn(key, frame)
        self.assertIs(projected["real_hardware_measured"], False)
        self.assertIs(projected["measurement_performed"], False)

    def test_subclass_as_dict_override_cannot_leak_raw_exception(self):
        # An overridden as_dict() returning a non-JSON value used to surface a
        # raw TypeError from json.dumps instead of a bounded snapshot record.
        class Bad(FramePacingReport):
            def as_dict(self):
                return {"real_gpu_measurement": object()}

        snap = compose_snapshot(frame_pacing=Bad(**genuine_fields()))
        blob = json.dumps(snap.as_dict(), sort_keys=True)
        self.assertIs(json.loads(blob)["frame_pacing"]["real_gpu_measurement"],
                      False)


if __name__ == "__main__":
    unittest.main()
