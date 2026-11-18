import hashlib
import tempfile
from pathlib import Path
import unittest

from scripts.testlab_run_ledger import advance, new_run, record_artifact, save_new


SHA = "ab" * 20
ID = "12" * 16


class LedgerTests(unittest.TestCase):
    def test_run_identity_and_exclusive_write(self):
        with tempfile.TemporaryDirectory() as folder:
            run = new_run(SHA, nonce=ID)
            self.assertEqual(run["state"], "CREATED")
            file = save_new(Path(folder) / (ID + ".json"), run)
            with self.assertRaises(FileExistsError):
                save_new(file, run)

    def test_reject_bad_identity_and_run_id(self):
        for sha, nonce in (("main", ID), (SHA, "guess")):
            with self.subTest(sha=sha, nonce=nonce), self.assertRaises(ValueError):
                new_run(sha, nonce=nonce)

    def test_hash_evidence_and_require_for_pass(self):
        run = new_run(SHA, nonce=ID)
        advance(run, "RUNNING")
        with self.assertRaises(ValueError):
            advance(run, "PASS")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "evidence.json"
            path.write_bytes(b"separate host evidence")
            record_artifact(run, "host-process", path)
            self.assertEqual(run["artifacts"][0]["sha256"],
                             hashlib.sha256(b"separate host evidence").hexdigest())
            with self.assertRaises(ValueError):
                record_artifact(run, "host-process", path)
            advance(run, "PASS")
        with self.assertRaises(ValueError):
            advance(run, "RUNNING")

    def test_retry_limit(self):
        run = new_run(SHA, nonce=ID)
        for index in range(3):
            advance(run, "RUNNING")
            advance(run, "FAIL")
        with self.assertRaises(ValueError):
            advance(run, "RUNNING")

    def test_invalid_transition_and_artifact_name(self):
        run = new_run(SHA, nonce=ID)
        with self.assertRaises(ValueError):
            advance(run, "PASS")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "artifact"
            path.write_text("yes")
            with self.assertRaises(ValueError):
                record_artifact(run, "../secret", path)


if __name__ == "__main__":
    unittest.main()
