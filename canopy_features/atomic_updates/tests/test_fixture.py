"""Fixture-gate regression tests: synthetic pass cases and hostile controls."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from canopy_features.atomic_updates import contract as c
from canopy_features.atomic_updates.fixture import evaluate_fixture, parse_fixture

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "scratch" / "lacos_atomic_updates" / "fixtures"
HOSTILE = ROOT / "scratch" / "lacos_atomic_updates" / "hostile"


def minimal_fixture() -> dict[str, object]:
    text = (FIXTURES / "F001-ready-handoff.json").read_text(encoding="utf-8")
    return json.loads(text)


class FixtureTests(unittest.TestCase):
    def test_every_synthetic_fixture_matches_expected_decision(self) -> None:
        paths = sorted(FIXTURES.glob("*.json"))
        self.assertGreaterEqual(len(paths), 7)
        for path in paths:
            with self.subTest(fixture=path.name):
                fixture = parse_fixture(path.read_text(encoding="utf-8"))
                decision = evaluate_fixture(fixture)
                self.assertEqual(decision.status, fixture.expect)
                self.assertEqual(decision.guest_status, c.GUEST_NOT_RUN)
                self.assertFalse(any(step.executed for step in decision.steps))

    def test_hostile_fixtures_are_rejected(self) -> None:
        paths = sorted(HOSTILE.glob("*.json"))
        self.assertGreaterEqual(len(paths), 3)
        for path in paths:
            with self.subTest(fixture=path.name):
                with self.assertRaises(c.AtomicUpdatesError):
                    parse_fixture(path.read_text(encoding="utf-8"))

    def test_duplicate_key_rejected(self) -> None:
        text = '{"schema":"a","schema":"b"}\n'
        with self.assertRaises(c.AtomicUpdatesError):
            parse_fixture(text)

    def test_huge_integer_valueerror_translated(self) -> None:
        text = '{"x": ' + "9" * 5000 + "}\n"
        with self.assertRaises(c.AtomicUpdatesError):
            parse_fixture(text)

    def test_unknown_key_rejected(self) -> None:
        data = minimal_fixture()
        data["exec_command"] = "anything"
        with self.assertRaises(c.AtomicUpdatesError):
            parse_fixture(json.dumps(data))

    def test_non_synthetic_label_rejected(self) -> None:
        data = minimal_fixture()
        data["label"] = "REAL_GUEST"
        with self.assertRaises(c.AtomicUpdatesError):
            parse_fixture(json.dumps(data))

    def test_real_guest_status_rejected(self) -> None:
        data = minimal_fixture()
        data["guest_status"] = "PASS"
        with self.assertRaises(c.AtomicUpdatesError):
            parse_fixture(json.dumps(data))

    def test_nested_wrong_type_rejected(self) -> None:
        data = minimal_fixture()
        data["observation"] = ["not", "an", "object"]
        with self.assertRaises(c.AtomicUpdatesError):
            parse_fixture(json.dumps(data))

    def test_fixture_name_requires_text(self) -> None:
        data = minimal_fixture()
        data["name"] = {"nested": "object"}
        with self.assertRaises(c.AtomicUpdatesError):
            parse_fixture(json.dumps(data))

    def test_wrong_expectation_is_not_self_fulfilling(self) -> None:
        data = minimal_fixture()
        data["expect"] = c.STATUS_BLOCKED
        fixture = parse_fixture(json.dumps(data))
        self.assertEqual(evaluate_fixture(fixture).status, c.STATUS_READY)
        self.assertNotEqual(evaluate_fixture(fixture).status, fixture.expect)


if __name__ == "__main__":
    unittest.main()
