"""Synthetic preflight tests; real Mint session is not represented."""
import unittest
from scripts.mint_preflight import detect, parse_os_release


MINT = 'NAME="Linux Mint"\nID=linuxmint\nVERSION_ID="22.2"\n'
ENV = {"XDG_CURRENT_DESKTOP": "X-Cinnamon:Cinnamon", "DISPLAY": ":0"}


class MintPreflightTests(unittest.TestCase):
    def probe(self, release=MINT, env=None, gtk=True, root=False, commands=None):
        return detect(os_release=release, environ=ENV if env is None else env,
                      which=(lambda command: "/usr/bin/" + command
                             if commands is None or command in commands else None),
                      probe_gtk=lambda: gtk, geteuid=lambda: 0 if root else 1000)

    def test_mint_session_ready(self):
        result = self.probe()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(len(result["checks"]), 8)
        self.assertEqual(result["distro"]["version"], "22.2")

    def test_unsupported_distro_is_blocked(self):
        result = self.probe(release="ID=ubuntu\n")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["checks"][0]["status"], "BLOCKED")

    def test_no_cinnamon_and_no_display_are_blocked(self):
        result = self.probe(env={"XDG_CURRENT_DESKTOP": "GNOME", "DISPLAY": "wayland-0"})
        failures = [x["name"] for x in result["checks"] if x["status"] != "PASS"]
        self.assertIn("cinnamon-session", failures)
        self.assertIn("x11-display", failures)

    def test_no_gtk_or_xvfb_is_blocked(self):
        result = self.probe(gtk=False, commands={"git", "python3"})
        failures = [x["name"] for x in result["checks"] if x["status"] != "PASS"]
        self.assertIn("gtk3-python", failures)
        self.assertIn("xvfb-run", failures)

    def test_refuse_root(self):
        self.assertEqual(self.probe(root=True)["status"], "BLOCKED")

    def test_release_parser(self):
        parsed = parse_os_release('ID="linuxmint"\nVERSION_ID=22.2\n# comment\n')
        self.assertEqual(parsed["ID"], "linuxmint")
        self.assertEqual(parsed["VERSION_ID"], "22.2")


if __name__ == "__main__":
    unittest.main()
