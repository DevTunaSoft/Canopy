"""RED/GREEN: wrong-type state_dir must raise the domain CheckpointError."""
import tempfile
import unittest
from pathlib import Path

from canopy_features.reliability import startup_checkpoints as s


class PathTypeGuardTests(unittest.TestCase):
    WRONG = (None, 7, 1.5, True, [], {}, b"bytes")

    def test_wrong_types_raise_domain_error(self):
        for value in self.WRONG:
            with self.subTest(value=repr(value)):
                with self.assertRaises(s.CheckpointError):
                    s.StartupCheckpoints(value, ["alpha"])

    def test_raw_typeerror_is_not_leaked(self):
        with self.assertRaises(s.CheckpointError) as caught:
            s.StartupCheckpoints(None, ["alpha"])
        self.assertNotIsInstance(caught.exception, TypeError)

    def test_str_path_still_works(self):
        with tempfile.TemporaryDirectory() as directory:
            cp = s.StartupCheckpoints(directory, ["alpha"])
            cp.begin()
            self.assertTrue(Path(directory, "startup.json").is_file())

    def test_pathlib_path_still_works(self):
        with tempfile.TemporaryDirectory() as directory:
            cp = s.StartupCheckpoints(Path(directory), ["alpha"])
            cp.begin()
            self.assertEqual(cp.steps, ("alpha",))

    def test_other_argument_validation_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(s.CheckpointError):
                s.StartupCheckpoints(directory, None)
            with self.assertRaises(s.CheckpointError):
                s.StartupCheckpoints(directory, [])


if __name__ == "__main__":
    unittest.main()
