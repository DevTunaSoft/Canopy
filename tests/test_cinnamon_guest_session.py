"""Mock process inventory, no Cinnamon session needed in CI."""
import tempfile
from pathlib import Path
import unittest
from scripts.cinnamon_guest_session import parse_environ, find_cinnamon_session

ENV = b"XDG_CURRENT_DESKTOP=X-Cinnamon:Cinnamon\0XDG_SESSION_TYPE=x11\0DISPLAY=:0\0"


class GuestSessionTests(unittest.TestCase):
    def test_only_approved_environment_fields(self):
        result = parse_environ(ENV + b"SECRET=hidden\0")
        self.assertEqual(result["DISPLAY"], ":0")
        self.assertNotIn("SECRET", result)
        with self.assertRaises(ValueError):
            parse_environ(b"x" * 65537)

    def test_only_same_user_cinnamon_with_xauthority(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            home = root / "canopy-test"
            home.mkdir()
            auth = home / ".Xauthority"
            auth.write_bytes(b"fake cookie")
            proc = root / "proc"
            proc.mkdir()
            process = proc / "123"
            process.mkdir()
            (process / "comm").write_text("cinnamon\n")
            (process / "environ").write_bytes(ENV)
            user = process.stat().st_uid
            if user == 0:
                self.skipTest("Mock fixture owner is root; guest selector must reject root")
            result = find_cinnamon_session(proc=proc, uid=user, home=home)
            self.assertEqual(result["XAUTHORITY"], str(auth))
            self.assertEqual(result["DISPLAY"], ":0")

    def test_reject_wrong_account_without_scanning(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                find_cinnamon_session(proc=Path(d), uid=1000, home=Path(d)/"personal")


if __name__ == "__main__":
    unittest.main()
