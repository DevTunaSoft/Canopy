"""Cross-component synthetic integration; never claims a Mint guest was tested."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.run_approved_test_plan import run_plan
from scripts.audit_test_evidence import audit
from scripts.testlab_run_ledger import new_run, advance, record_artifact
from scripts.guest_result_envelope import wrap

COMMIT = "ab" * 20
RUN = "12" * 16
BOOT = "11111111-2222-3333-4444-555555555555"

def fake_report():
    return {"schema_version": 1, "status": "PASS",
            "checks": [
                {"name": "unit", "status": "PASS", "exit_code": 0,
                 "duration_seconds": 1.0, "output": "Ran 3 tests in 0.01s\n\nOK\n",
                 "output_truncated": False},
                {"name": "syntax", "status": "PASS", "exit_code": 0,
                 "duration_seconds": 0.2, "output": "", "output_truncated": False}
            ]}


class PipelineContractTests(unittest.TestCase):
    def test_end_to_end_synthetic_handoff_with_separate_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = root / "checkout"
            checkout.mkdir()
            approved = root / "approved.json"
            approved.write_text(json.dumps({"version": 1, "repository": "DevTunaSoft/Canopy",
                                            "commit": COMMIT, "checks": ["unit", "syntax"]}))
            guest_output = root / "guest" / "report.json"
            guest_output.parent.mkdir()
            calls = []
            def mock_execute(source, out, checks):
                calls.append((source, checks))
                out.write_text(json.dumps(fake_report()))
                return fake_report()
            action = run_plan(approved, checkout, guest_output,
                              validator=lambda plan, root: {"status": "PASS"},
                              executor=mock_execute)
            self.assertEqual(action["status"], "PASS")
            self.assertEqual(calls[0][1], ["unit", "syntax"])
            evidence = audit(json.loads(guest_output.read_text()), ["unit", "syntax"])
            self.assertEqual(evidence["status"], "PASS")
            guest = wrap(commit=COMMIT, run_id=RUN, boot_id=BOOT, report=guest_output)
            self.assertFalse(guest["host_verified"])
            host = new_run(COMMIT, nonce=RUN)
            advance(host, "RUNNING")
            record_artifact(host, "received-guest-report", guest_output)
            # Host-side hashing an untrusted guest report does NOT establish
            # independent execution or UI correctness; do not mark release PASS.
            self.assertEqual(host["state"], "RUNNING")
            self.assertEqual(host["artifacts"][0]["sha256"], guest["report_sha256"])

    def test_host_guest_mismatch_is_never_certified(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "fake.json"
            out.write_text(json.dumps(fake_report() | {"status": "FAIL"}))
            with self.assertRaises(ValueError):
                audit(json.loads(out.read_text()), ["unit", "syntax"])

if __name__ == "__main__":
    unittest.main()
