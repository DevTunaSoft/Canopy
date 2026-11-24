"""Wrong-type evidence-directory inputs must fail closed with EvidenceError.

Regression tests for tools/mint_acceptance_report_gate.py: a non-path caller
argument previously raised a raw TypeError from pathlib.Path() before the
domain guard could produce EvidenceError. These are pure-stub tests: no VM,
no Qt binary, no guest and no acceptance claim.

CI discovers only ``tests/``; run explicitly with
``python -m unittest tools.qa.mint_acceptance_gate_type_tests -v``.
"""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools import mint_acceptance_report_gate as gate  # noqa: E402
from tools import mint_classic_qt_smoke as qt  # noqa: E402

SOURCE = "a" * 40
BINARY = "b" * 64


class MintAcceptanceGateTypeTests(unittest.TestCase):
    def call(self, directory, *, source=SOURCE, binary=BINARY):
        return gate.validate(directory, expected_source_sha=source,
                             expected_binary_sha256=binary)

    def test_wrong_type_directory_raises_domain_error(self):
        for bad in (123, None, True, 0, [], b"/tmp/evidence", object()):
            with self.subTest(value=repr(bad)):
                with self.assertRaises(gate.EvidenceError) as caught:
                    self.call(bad)
                self.assertNotIsInstance(caught.exception, TypeError)

    def test_valid_directory_type_still_reaches_evidence_check(self):
        with tempfile.TemporaryDirectory(prefix="canopy-gate-dir-type-") as td:
            candidate = Path(td)
            with self.assertRaises((gate.EvidenceError, qt.MintSmokeError)) as caught:
                self.call(candidate)
            self.assertNotIsInstance(caught.exception, TypeError)

    def test_sha_argument_controls_remain_domain_errors(self):
        for source, binary in ((True, BINARY), (123, BINARY), (SOURCE, True), (SOURCE, 456)):
            with self.subTest(source=repr(source), binary=repr(binary)):
                with self.assertRaises(gate.EvidenceError) as caught:
                    self.call("C:/nonexistent-evidence", source=source, binary=binary)
                self.assertNotIsInstance(caught.exception, TypeError)


if __name__ == "__main__":
    unittest.main()
