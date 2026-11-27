"""PE-026: explicit unavailable state for absent native quick-control services.

SYNTHETIC pure-Python producer/view contracts plus read-only C++ source
contracts. No host probe, Qt compile, live desktop, screen-reader or Linux Mint
acceptance is claimed here; those remain NOT_RUN. Every fixture value is
explicitly supplied by this test, never inferred from the host.
"""
import json
import unittest
from pathlib import Path

from canopy_core.host_events import CAPABILITIES_TOPIC
from canopy_features.quick_controls import host_status_producer as producer
from canopy_features.quick_controls.host_state import (
    HostStateController,
    HostStateSnapshot,
)
from canopy_features.system.quick_controls_state import STATUS_LABELS

ROOT = Path(__file__).resolve().parents[1]
MAIN_CPP = ROOT / "prototype" / "classic" / "main.cpp"

ABSENCE_SOURCE = "host-status-file"


def _absence():
    return producer.unavailable(source=ABSENCE_SOURCE)


class ExplicitAbsenceWireTests(unittest.TestCase):
    def test_absence_wire_carries_only_topic_and_provenance(self):
        record = _absence()
        self.assertTrue(record.is_unavailable)
        payload = dict(record.to_dict())
        self.assertEqual(payload, {"topic": CAPABILITIES_TOPIC,
                                   "source": ABSENCE_SOURCE})
        raw = record.to_json_bytes()
        self.assertEqual(raw, _absence().to_json_bytes())
        text = raw.decode("utf-8")
        for invented in ("null", "false", "true", "volume_percent",
                         "network_connected", "battery_charging", '"status":'):
            with self.subTest(invented=invented):
                self.assertNotIn(invented, text)

    def test_absence_requires_a_trusted_source(self):
        for source in ("", "untrusted", "host-events ", None, 7, True,
                       "host—status-file"):
            with self.subTest(source=repr(source)):
                with self.assertRaises(producer.ProducerError):
                    producer.unavailable(source=source)

    def test_absence_cannot_carry_observations(self):
        for kwargs in (
            {"network_connected": True},
            {"battery_charging": False},
            {"volume_percent": 0},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(producer.ProducerError):
                    producer.HostStatusSnapshot(source=ABSENCE_SOURCE,
                                                _absent=True, **kwargs)

    def test_ordinary_empty_compose_still_refused(self):
        # The accidental "no facts" call path stays fail closed; only the
        # explicit unavailable() API can publish an absence event.
        with self.assertRaises(producer.ProducerError):
            producer.compose(source=ABSENCE_SOURCE)

    def test_empty_trusted_payload_is_an_explicit_absence(self):
        record = producer.from_payload({"topic": CAPABILITIES_TOPIC},
                                       source=ABSENCE_SOURCE)
        self.assertTrue(record.is_unavailable)
        self.assertEqual(dict(record.to_dict()),
                         dict(_absence().to_dict()))


class AbsentServiceViewTests(unittest.TestCase):
    @staticmethod
    def _views(record):
        payload = dict(record.to_dict())
        payload.pop("topic")
        return HostStateController.from_payload(payload).to_dict()

    def test_absence_event_renders_unknown_for_network_audio_and_power(self):
        views = self._views(_absence())
        for domain in ("network", "audio", "power", "session"):
            with self.subTest(domain=domain):
                view = views[domain]
                self.assertEqual(view["status"], "unknown")
                self.assertEqual(view["status_label"], STATUS_LABELS["unknown"])
                self.assertFalse(view["observed"])
                self.assertEqual(view["source"], "none")
                self.assertEqual(view["availability"], "UNAVAILABLE")
                self.assertFalse(view["control"]["allowed"])
                self.assertEqual(view["detail_kind"], "")
                self.assertEqual(view["detail_value"], -1)

    def test_absence_event_revokes_previously_supplied_status(self):
        before = self._views(producer.compose(
            source=ABSENCE_SOURCE,
            network_connected=True,
            battery_charging=True,
            volume_percent=42,
        ))
        self.assertEqual(before["network"]["status"], "connected")
        self.assertEqual(before["power"]["status"], "charging")
        self.assertEqual(before["audio"]["detail_value"], 42)
        after = self._views(_absence())
        for domain in ("network", "audio", "power"):
            with self.subTest(domain=domain):
                self.assertEqual(after[domain]["status"], "unknown")
                self.assertFalse(after[domain]["observed"])
        self.assertEqual(after["audio"]["detail_kind"], "")
        self.assertEqual(after["power"]["detail_value"], -1)

    def test_absence_never_enables_a_control_or_settings_bridge(self):
        view = HostStateSnapshot.from_payload(
            dict(_absence().to_dict()), source=ABSENCE_SOURCE).view("power")
        self.assertFalse(view["control"]["allowed"])
        self.assertFalse(view["settings"]["allowed"])


class CompiledRevokeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cpp = MAIN_CPP.read_text(encoding="utf-8")
        start = cls.cpp.index("class QuickControlsHostStateController final")
        end = cls.cpp.index("\n};", start)
        cls.controller = cls.cpp[start:end]

    def test_accepted_event_replaces_every_observation(self):
        for marker in (
            "bool haveNetwork = false, network = false;",
            "bool haveMuted = false, muted = false;",
            "bool haveCharging = false, charging = false;",
            "int volume = -1, brightness = -1;",
            "m_hasNetwork = haveNetwork;",
            "m_hasMuted = haveMuted;",
            "m_hasCharging = haveCharging;",
            "m_volume = volume;",
            "m_brightness = brightness;",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.controller)
        self.assertNotIn("if (haveNetwork)", self.controller)
        self.assertNotIn("if (haveMuted)", self.controller)
        self.assertNotIn("if (haveCharging)", self.controller)

    def test_no_new_topic_field_or_host_probe_is_added(self):
        self.assertIn(QStringLiteral(CAPABILITIES_TOPIC), self.controller)
        for forbidden in ("QProcess", "QTcpSocket", "QLocalSocket", "QDBus",
                          "std::system", "status_service", "thermal"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.controller)


def QStringLiteral(text):
    return 'QStringLiteral("%s")' % text


if __name__ == "__main__":
    unittest.main()
