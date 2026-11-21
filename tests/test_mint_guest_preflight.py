"""Read-only Mint preflight tests: readiness is never acceptance."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

from tools.mint_guest_preflight import NEEDED, assess, parse_release

ROOT = Path(__file__).resolve().parents[1]


class MintGuestPreflightTests(unittest.TestCase):
    def setUp(self):
        self.mint = {"ID": "linuxmint", "VERSION_ID": "22.3"}
        self.env = {
            "DISPLAY": ":0", "XDG_CURRENT_DESKTOP": "X-Cinnamon",
            "XDG_SESSION_TYPE": "x11",
        }
        self.available = {name: True for name in NEEDED}

    def probe(self, **kwargs):
        return assess(
            kwargs.get("release", self.mint),
            kwargs.get("env", self.env),
            kwargs.get("available", self.available),
            kwargs.get("qt_version", "6.4.2"),
        )

    def test_ready_is_not_mint_acceptance(self):
        report = self.probe()
        self.assertEqual(report["status"], "READY_FOR_TESTS")
        self.assertEqual(report["mint_guest_acceptance"], "NOT_RUN")
        self.assertEqual(report["runtime_functional_test"], "NOT_RUN")
        self.assertEqual(report["visual_acceptance"], "NOT_RUN")

    def test_ubuntu_is_not_passed_as_mint(self):
        r = self.probe(release={"ID": "ubuntu", "VERSION_ID": "24.04"})
        self.assertEqual(r["status"], "BLOCKED")
        self.assertFalse(r["mint_identified"])
        self.assertIn("not verified as Linux Mint", " ".join(r["blockers"]))

    def test_missing_gui_fails(self):
        env = dict(self.env)
        env.pop("DISPLAY")
        self.assertEqual(self.probe(env=env)["status"], "BLOCKED")

    def test_wayland_guest_can_be_ready(self):
        env = {
            "WAYLAND_DISPLAY": "wayland-0",
            "XDG_CURRENT_DESKTOP": "X-Cinnamon",
            "XDG_SESSION_TYPE": "wayland",
        }
        self.assertEqual(self.probe(env=env)["status"], "READY_FOR_TESTS")

    def test_missing_desktop_session_identification_is_blocker(self):
        env = dict(self.env)
        env.pop("XDG_CURRENT_DESKTOP")
        self.assertEqual(self.probe(env=env)["status"], "BLOCKED")

    def test_missing_session_type_is_blocker(self):
        env = dict(self.env)
        env.pop("XDG_SESSION_TYPE")
        self.assertEqual(self.probe(env=env)["status"], "BLOCKED")

    def test_missing_each_tool_is_reported(self):
        for tool in NEEDED:
            with self.subTest(tool=tool):
                available = dict(self.available)
                available[tool] = False
                result = self.probe(available=available)
                self.assertEqual(result["status"], "BLOCKED")
                self.assertIn(tool, " ".join(result["blockers"]))

    def test_missing_qt_is_blocker(self):
        result = self.probe(qt_version=None)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("Qt6Core", " ".join(result["blockers"]))

    def test_no_host_private_data_dumped(self):
        env = dict(self.env)
        env.update({"HOME": "/home/secret", "SSH_AUTH_SOCK": "secret",
                    "CANOPY_SECRET": "very secret"})
        report = self.probe(env=env)
        serial = json.dumps(report)
        self.assertNotIn("/home/secret", serial)
        self.assertNotIn("very secret", serial)
        self.assertNotIn("SSH_AUTH_SOCK", serial)
        self.assertNotIn(":0", serial)

    def test_release_parser_only_allows_three_known_fields(self):
        parsed = parse_release(
            'NAME="Ubuntu"\nID=linuxmint\nVERSION_ID="22.3"\n'
            'PRETTY_NAME="Linux Mint 22.3"\nTOKEN=secret\n'
        )
        self.assertEqual(parsed["ID"], "linuxmint")
        self.assertEqual(parsed["VERSION_ID"], "22.3")
        self.assertNotIn("TOKEN", parsed)

    def test_bad_release_values_ignored(self):
        self.assertEqual(parse_release("ID=\"linuxmint\nVERSION_ID=22.3"),
                         {"VERSION_ID": "22.3"})
        self.assertEqual(parse_release("ID=" + chr(0)), {})
        self.assertNotIn("PRETTY_NAME",
                         parse_release("PRETTY_NAME=" + "x" * 121))

    def test_non_mint_local_cli_never_claims_acceptance(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "mint_guest_preflight.py"),
             "--json"], capture_output=True, text=True, check=False,
            cwd=ROOT,
        )
        report = json.loads(proc.stdout)
        self.assertIn(proc.returncode, (0, 1))
        self.assertTrue(report["probe_only"])
        self.assertEqual(report["mint_guest_acceptance"], "NOT_RUN")


if __name__ == "__main__":
    unittest.main()
