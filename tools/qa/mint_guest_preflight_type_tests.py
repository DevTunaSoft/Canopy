"""Wrong-type caller inputs to the Mint preflight must fail closed.

Pure-stub regression tests: no VM, no guest control, no Qt. CI discovers only
``tests/``; run explicitly with
``python -m unittest tools.qa.mint_guest_preflight_type_tests -v``.
"""
from pathlib import Path
import sys
import unittest
from types import MappingProxyType

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools import mint_guest_preflight as preflight  # noqa: E402

GOOD_RELEASE = {"ID": "linuxmint", "VERSION_ID": "22.3"}
GOOD_ENV = {"XDG_CURRENT_DESKTOP": "X-Cinnamon", "XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"}
GOOD_AVAILABLE = {name: True for name in preflight.NEEDED}


class MintPreflightTypeTests(unittest.TestCase):
    def assert_domain_error(self, fn):
        with self.assertRaises(ValueError) as caught:
            fn()
        self.assertNotIsInstance(caught.exception, (TypeError, AttributeError))

    def test_assess_wrong_type_mappings_fail_closed(self):
        for bad in ([], "text", 5, None):
            with self.subTest(value=repr(bad)):
                self.assert_domain_error(lambda bad=bad: preflight.assess(bad, GOOD_ENV, GOOD_AVAILABLE))
                self.assert_domain_error(lambda bad=bad: preflight.assess(GOOD_RELEASE, bad, GOOD_AVAILABLE))
                self.assert_domain_error(lambda bad=bad: preflight.assess(GOOD_RELEASE, GOOD_ENV, bad))

    def test_assess_non_string_version_id_fail_closed(self):
        for bad in (22, True, [], None):
            with self.subTest(value=repr(bad)):
                release = dict(GOOD_RELEASE)
                release["VERSION_ID"] = bad
                self.assert_domain_error(lambda release=release: preflight.assess(release, GOOD_ENV, GOOD_AVAILABLE))

    def test_parse_release_wrong_type_fail_closed(self):
        for bad in (123, None, [], b"ID=linuxmint"):
            with self.subTest(value=repr(bad)):
                self.assert_domain_error(lambda bad=bad: preflight.parse_release(bad))

    def test_valid_inputs_still_ready_and_bounded(self):
        result = preflight.assess(GOOD_RELEASE, GOOD_ENV, GOOD_AVAILABLE, "6.4.2")
        self.assertEqual(result["status"], "READY_FOR_TESTS")
        self.assertEqual(result["blockers"], [])
        huge = {str(i): True for i in range(10000)}
        bounded = preflight.assess(GOOD_RELEASE, GOOD_ENV, huge, "6.4.2")
        self.assertEqual(len(bounded["commands_present"]), len(preflight.NEEDED))

    def test_environ_like_mapping_accepted(self):
        result = preflight.assess(MappingProxyType(GOOD_RELEASE),
                                  MappingProxyType(GOOD_ENV),
                                  MappingProxyType(GOOD_AVAILABLE), "6.4.2")
        self.assertEqual(result["status"], "READY_FOR_TESTS")

    def test_parse_release_valid_subset(self):
        parsed = preflight.parse_release("ID=linuxmint\nVERSION_ID=22.3\nPRETTY_NAME=Linux Mint 22.3\n")
        self.assertEqual(parsed, {"ID": "linuxmint", "VERSION_ID": "22.3",
                                  "PRETTY_NAME": "Linux Mint 22.3"})


if __name__ == "__main__":
    unittest.main()
