"""SYNTHETIC fail-closed tests for PE-099 quick-controls status contracts.

Pure-Python contract checks at the existing trusted-source boundary. They never
probe a device, audio server, network, VM, desktop or clock; no Qt build, live
host reading, Mint acceptance, screen-reader session or visual approval is
claimed. Every fact below is an explicitly supplied bounded fixture.
"""
import ast
from dataclasses import FrozenInstanceError
from pathlib import Path
import unittest
from types import MappingProxyType
from unittest.mock import patch

from canopy_features.quick_controls import host_status_producer as producer
from canopy_features.quick_controls import status_contracts as contracts
from canopy_features.system.quick_controls_state import (
    Observation, STATUS_LABELS, STATUS_TOKENS,
)

SOURCE = Path(contracts.__file__)
SRC = "host-status-file"


def _snapshot(**overrides):
    facts = dict(source=SRC, network_connected=True, battery_charging=False,
                 volume_percent=42)
    facts.update(overrides)
    return producer.compose(**facts)


def _audio(status="muted", source=SRC):
    return Observation("audio", status, source)


class TrustedSourceProjectionTests(unittest.TestCase):
    def test_exact_three_domains_and_existing_token_vocabulary(self):
        self.assertEqual(contracts.DOMAINS, ("audio", "network", "power"))
        for domain in contracts.DOMAINS:
            self.assertEqual(contracts.KNOWN_STATUSES[domain],
                             STATUS_TOKENS[domain] - {"unknown"})
        self.assertEqual(contracts.UNKNOWN, "unknown")

    def test_network_and_power_facts_project_to_existing_status_tokens(self):
        view = contracts.from_snapshot(_snapshot())
        self.assertEqual(view.record("network").status, "connected")
        self.assertEqual(view.record("power").status, "discharging")
        self.assertEqual(view.record("network").status_label,
                         STATUS_LABELS["connected"])
        self.assertEqual(view.record("power").status_label,
                         STATUS_LABELS["discharging"])
        self.assertTrue(view.record("network").observed)
        self.assertTrue(view.record("power").observed)

    def test_audio_status_comes_only_from_explicit_trusted_observation(self):
        view = contracts.from_snapshot(_snapshot(),
                                       observations=(_audio("unmuted"),))
        audio = view.record("audio")
        self.assertEqual(audio.status, "unmuted")
        self.assertEqual(audio.status_label, STATUS_LABELS["unmuted"])
        self.assertEqual(audio.detail_kind, "volume")
        self.assertEqual(audio.detail_value, 42)
        self.assertTrue(audio.observed)

    def test_volume_zero_does_not_invent_a_mute_status(self):
        view = contracts.from_snapshot(_snapshot(volume_percent=0))
        audio = view.record("audio")
        self.assertEqual(audio.status, contracts.UNKNOWN)
        self.assertFalse(audio.observed)
        self.assertEqual(audio.detail_value, 0)

    def test_missing_facts_are_unknown_not_false_or_zero(self):
        view = contracts.from_snapshot(producer.compose(
            source=SRC, volume_percent=None, network_connected=None,
            battery_charging=False))
        self.assertEqual(view.record("network").status, contracts.UNKNOWN)
        self.assertEqual(view.record("audio").status, contracts.UNKNOWN)
        self.assertEqual(view.record("power").status, "discharging")
        self.assertFalse(view.record("network").observed)
        self.assertIsNone(view.record("audio").detail_kind)

    def test_unavailable_revokes_every_domain_and_detail(self):
        view = contracts.from_snapshot(producer.unavailable(source=SRC))
        for domain in contracts.DOMAINS:
            record = view.record(domain)
            self.assertEqual(record.status, contracts.UNKNOWN)
            self.assertFalse(record.observed)
            self.assertIsNone(record.detail_kind)
            self.assertIsNone(record.detail_value)

    def test_from_payload_uses_existing_trusted_source_boundary(self):
        view = contracts.from_payload({
            "topic": "capabilities.report",
            "network_connected": False,
            "battery_charging": True,
            "volume_percent": 100,
            "unrelated": "not-echoed",
        }, source=SRC, observations=(_audio("muted"),))
        mapping = dict(view.to_dict())
        self.assertEqual(mapping["source"], SRC)
        self.assertEqual(mapping["domains"]["network"]["status"],
                         "disconnected")
        self.assertEqual(mapping["domains"]["audio"]["status"], "muted")
        self.assertEqual(mapping["domains"]["power"]["status"], "charging")
        self.assertNotIn("unrelated", view.to_json_bytes().decode("utf-8"))

    def test_empty_payload_is_an_explicit_absence_event(self):
        view = contracts.from_payload({}, source=SRC)
        self.assertEqual(view.to_dict(), contracts.unavailable(source=SRC).to_dict())

    def test_snapshot_is_frozen_and_view_is_read_only(self):
        view = contracts.from_snapshot(_snapshot())
        with self.assertRaises(FrozenInstanceError):
            view.source = "other"
        with self.assertRaises(FrozenInstanceError):
            view.record("network").status = "connected"
        mapping = view.to_dict()
        self.assertIsInstance(mapping, MappingProxyType)
        self.assertIsInstance(mapping["domains"], MappingProxyType)
        with self.assertRaises(TypeError):
            mapping["source"] = "forged"
        self.assertEqual(tuple(mapping["domains"]), contracts.DOMAINS)

    def test_bytes_are_deterministic_bounded_ascii(self):
        view = contracts.from_snapshot(_snapshot(),
                                       observations=(_audio("muted"),))
        encoded = view.to_json_bytes()
        self.assertIs(type(encoded), bytes)
        self.assertTrue(encoded.isascii())
        self.assertLessEqual(len(encoded), contracts.MAX_JSON_BYTES)
        self.assertEqual(encoded, contracts.from_snapshot(
            _snapshot(), observations=(_audio("muted"),)).to_json_bytes())

    def test_byte_cap_is_enforced_before_return(self):
        view = contracts.from_snapshot(_snapshot())
        with patch.object(contracts, "MAX_JSON_BYTES", 16):
            with self.assertRaises(contracts.StatusContractError):
                view.to_json_bytes()

    def test_as_observations_reuses_existing_quick_controls_model(self):
        view = contracts.from_snapshot(
            _snapshot(network_connected=False, battery_charging=True),
            observations=(_audio("muted"),))
        emitted = view.as_observations()
        self.assertIsInstance(emitted, tuple)
        self.assertEqual({item.domain for item in emitted},
                         {"audio", "network", "power"})
        for item in emitted:
            self.assertIsInstance(item, Observation)
            self.assertEqual(item.source, SRC)
        self.assertEqual({item.domain: item.status for item in emitted}, {
            "network": "disconnected", "audio": "muted", "power": "charging"})

    def test_unknown_domain_rejected_by_accessor(self):
        view = contracts.from_snapshot(_snapshot())
        for domain in ("session", "networks", 7, None, True):
            with self.subTest(domain=repr(domain)):
                with self.assertRaises(contracts.StatusContractError):
                    view.record(domain)


class FailClosedTests(unittest.TestCase):
    def test_wrong_snapshot_type_is_refused(self):
        for bad in (None, {}, object(), "host-status-file", 42,
                    contracts.from_snapshot(producer.unavailable(source=SRC))):
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(contracts.StatusContractError):
                    contracts.from_snapshot(bad)

    def test_wrong_observation_containers_and_types_are_refused(self):
        for bad in (None, {}, "muted", 7, {_audio("muted")},
                    [_audio("muted"), "extra"],
                    [_audio("muted"), Observation("audio", "muted", SRC)]):
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(contracts.StatusContractError):
                    contracts.from_snapshot(_snapshot(), observations=bad)

    def test_non_audio_observations_are_refused(self):
        for domain, status in (("network", "connected"),
                               ("power", "charging"),
                               ("session", "active"), ("audio", "unknown")):
            with self.subTest(domain=domain, status=status):
                with self.assertRaises(contracts.StatusContractError):
                    contracts.from_snapshot(
                        _snapshot(), observations=(Observation(domain, status, SRC),))

    def test_contradictory_observation_provenance_is_refused(self):
        for source in ("host-events", "host", "other", "",
                       "host-status-file:extra"):
            with self.subTest(source=repr(source)):
                with self.assertRaises(contracts.StatusContractError):
                    contracts.from_snapshot(_snapshot(),
                                            observations=(_audio("muted", source),))

    def test_observations_cannot_coexist_with_a_revocation(self):
        with self.assertRaises(contracts.StatusContractError):
            contracts.from_snapshot(producer.unavailable(source=SRC),
                                    observations=(_audio("muted"),))

    def test_untrusted_sources_are_refused(self):
        for source in ("", "untrusted", "host-events ", "host-status-file/",
                       "a" * 65, None, 7, True, [], b"host-events"):
            with self.subTest(source=repr(source)):
                with self.assertRaises(contracts.StatusContractError):
                    contracts.unavailable(source=source)
                with self.assertRaises(contracts.StatusContractError):
                    contracts.from_payload({}, source=source)

    def test_hostile_payloads_fail_closed_at_the_boundary(self):
        for payload in (None, [], (), "payload", 7,
                        {"topic": "session.state.changed"},
                        {"source": "untrusted"},
                        {"network_connected": "true"},
                        {"volume_percent": 101},
                        {"battery_charging": 1}):
            with self.subTest(payload=repr(payload)):
                with self.assertRaises(contracts.StatusContractError):
                    contracts.from_payload(payload, source=SRC)

    def test_record_detail_is_bounded_and_domain_scoped(self):
        for bad_kind in ("mute", 7, True, [], ""):
            with self.subTest(kind=repr(bad_kind)):
                with self.assertRaises(contracts.StatusContractError):
                    contracts.StatusRecord("audio", "muted", bad_kind, 42)
        for bad_value in (-1, 101, 1.0, True, "42", [], None):
            with self.subTest(value=repr(bad_value)):
                with self.assertRaises(contracts.StatusContractError):
                    contracts.StatusRecord("audio", "muted", "volume", bad_value)
        with self.assertRaises(contracts.StatusContractError):
            contracts.StatusRecord("network", "connected", "volume", 42)
        with self.assertRaises(contracts.StatusContractError):
            contracts.StatusRecord("audio", "connected", None, None)

    def test_numeric_and_string_subclasses_fail_closed(self):
        class IntSubclass(int):
            pass

        class StrSubclass(str):
            pass

        with self.assertRaises(contracts.StatusContractError):
            contracts.StatusRecord("audio", StrSubclass("muted"), None, None)
        with self.assertRaises(contracts.StatusContractError):
            contracts.StatusRecord("audio", "muted", "volume", IntSubclass(42))

    def test_observation_limit_is_bounded(self):
        extra = [_audio("muted") for _ in range(contracts.MAX_OBSERVATIONS + 1)]
        with self.assertRaises(contracts.StatusContractError):
            contracts.from_snapshot(_snapshot(), observations=extra)


class PurityTests(unittest.TestCase):
    def test_no_io_host_or_transport_imports(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        forbidden = {"os", "sys", "subprocess", "socket", "pathlib", "time",
                     "datetime", "random", "threading", "multiprocessing",
                     "signal", "ctypes", "dbus", "gi", "PyQt5", "PySide6",
                     "pulseaudio", "networkmanager", "upower", "vm"}
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                found.add(node.module.split(".")[0])
        self.assertFalse(found & forbidden,
                         "unexpected imports: %r" % (found & forbidden))

    def test_no_file_or_process_calls(self):
        code = "\n".join(
            line for line in SOURCE.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#"))
        for forbidden in ("open(", "os.environ", "subprocess", "Popen",
                          "QProcess", "socket.", "gdbus", "dbus-send",
                          "pkexec", "sudo ", "systemctl", "Timer(", "poll("):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)

    def test_projection_opens_no_files(self):
        with patch("builtins.open", side_effect=AssertionError("file I/O")):
            view = contracts.from_snapshot(_snapshot(),
                                           observations=(_audio("muted"),))
            view.to_dict()
            view.to_json_bytes()
        self.assertEqual(view.record("audio").status, "muted")


if __name__ == "__main__":
    unittest.main()
