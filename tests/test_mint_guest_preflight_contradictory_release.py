"""Contradictory os-release metadata must never yield a false readiness PASS.

The preflight is a read-only readiness probe, not a Mint acceptance test.
A release file whose ID says Linux Mint but whose PRETTY_NAME names a
different distribution is contradictory, plausible-looking input (for
example a copied or stale os-release), and must fail closed.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.mint_guest_preflight import NEEDED, assess  # noqa: E402


class MintPreflightContradictoryReleaseTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            "XDG_CURRENT_DESKTOP": "X-Cinnamon",
            "XDG_SESSION_TYPE": "x11",
            "DISPLAY": ":0",
        }
        self.available = {name: True for name in NEEDED}

    def probe(self, pretty_name=None):
        release = {"ID": "linuxmint", "VERSION_ID": "22.3"}
        if pretty_name is not None:
            release["PRETTY_NAME"] = pretty_name
        return assess(release, self.env, self.available, "6.4.2")

    def test_conflicting_pretty_name_blocks_false_ready_pass(self):
        result = self.probe("Ubuntu 24.04 LTS")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(result["mint_identified"])
        self.assertTrue(any("contradicts Linux Mint identity" in reason
                            for reason in result["blockers"]))
        self.assertEqual(result["mint_guest_acceptance"], "NOT_RUN")
        self.assertEqual(result["runtime_functional_test"], "NOT_RUN")
        self.assertEqual(result["visual_acceptance"], "NOT_RUN")
        self.assertNotIn("Ubuntu 24.04 LTS", json.dumps(result))

    def test_other_conflicting_pretty_names_also_block(self):
        for pretty_name in ("Debian GNU/Linux 12 (bookworm)",
                            "LINUX MINT-like Ubuntu 22.04",
                            "Fedora Linux 40"):
            with self.subTest(pretty_name=pretty_name):
                result = self.probe(pretty_name)
                self.assertEqual(result["status"], "BLOCKED")
                self.assertFalse(result["mint_identified"])

    def test_mint_pretty_name_and_absent_pretty_name_remain_ready(self):
        for pretty_name in ("Linux Mint 22.3", None):
            with self.subTest(pretty_name=pretty_name):
                result = self.probe(pretty_name)
                self.assertEqual(result["status"], "READY_FOR_TESTS")
                self.assertTrue(result["mint_identified"])
                self.assertEqual(result["blockers"], [])
                self.assertEqual(result["mint_guest_acceptance"], "NOT_RUN")


if __name__ == "__main__":
    unittest.main()
