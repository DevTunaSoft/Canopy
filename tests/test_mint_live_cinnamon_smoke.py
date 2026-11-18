import tempfile
from pathlib import Path
import unittest
from scripts.mint_live_cinnamon_smoke import parse_wmctrl, session_ready, observe


ENV={"XDG_CURRENT_DESKTOP":"X-Cinnamon:Cinnamon",
     "XDG_SESSION_TYPE":"x11","DISPLAY":":0"}


class CinnamonSmokeTests(unittest.TestCase):
    def test_guard_refuses_fake_or_missing_cinnamon(self):
        self.assertTrue(session_ready(ENV, 1000))
        for changed in ({**ENV,"XDG_SESSION_TYPE":"wayland"},
                        {**ENV,"CANOPY_ISOLATED_DISPLAY":"1"},
                        {**ENV,"XDG_CURRENT_DESKTOP":"GNOME"},
                        {**ENV,"DISPLAY":"host:0"}):
            with self.subTest(changed=changed):
                self.assertFalse(session_ready(changed,1000))
        self.assertFalse(session_ready(ENV,0))

    def test_window_enumerator_only_counts_own_pid(self):
        output=("0x123 0 88 vm Canopy Classic preview\n"
                "0x124 0 88 vm Canopy Classic preview\n"
                "0x125 0 99 vm Canopy Classic preview\n"
                "garbage\n")
        self.assertEqual(parse_wmctrl(output,88),["0x123","0x124"])

    def test_missing_source_blocks_without_launching(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                observe(root,environment=ENV,uid=1000,
                        start=lambda *_a,**_k: self.fail("should not launch"))


if __name__=="__main__":
    unittest.main()
