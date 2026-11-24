"""RED/GREEN resource regression: per-window state view caching.

Deterministic identity assertions: repeated owned snapshot() reads return the
SAME read-only view; only a real state write invalidates it; guard/close/reopen
changes (which do not touch state) preserve identity.
"""
import unittest
from types import MappingProxyType

from canopy_features.windows import window_close_intents as c


class StateViewCacheTests(unittest.TestCase):
    def _model(self):
        model = c.CloseIntentModel()
        model.register("files.win", "shell.owner", state={"page": "home"})
        return model

    def test_repeated_reads_return_same_object(self):
        model = self._model()
        first = model.snapshot("files.win", "shell.owner")
        self.assertIsInstance(first, MappingProxyType)
        self.assertIs(first, model.snapshot("files.win", "shell.owner"))

    def test_state_write_invalidates(self):
        model = self._model()
        before = model.snapshot("files.win", "shell.owner")
        self.assertTrue(model.update_state("files.win", "shell.owner",
                                           page="settings"))
        after = model.snapshot("files.win", "shell.owner")
        self.assertIsNot(after, before)
        self.assertEqual(dict(after), {"page": "settings"})
        self.assertEqual(dict(before), {"page": "home"})

    def test_lifecycle_changes_preserve_identity(self):
        model = self._model()
        before = model.snapshot("files.win", "shell.owner")
        model.request_close("files.win", "shell.owner")
        model.reopen("files.win", "shell.owner")
        model.set_guard("files.win", "shell.owner", True)
        self.assertIs(model.snapshot("files.win", "shell.owner"), before)

    def test_unknown_and_denied_return_shared_empty(self):
        model = self._model()
        self.assertIs(model.snapshot("nope.win", "shell.owner"), c.NO_STATE)
        self.assertIs(model.snapshot("files.win", "other.owner"), c.NO_STATE)

    def test_release_removes_record(self):
        model = self._model()
        self.assertTrue(model.release("files.win", "shell.owner"))
        self.assertIs(model.snapshot("files.win", "shell.owner"), c.NO_STATE)

    def test_view_is_read_only(self):
        model = self._model()
        view = model.snapshot("files.win", "shell.owner")
        with self.assertRaises(TypeError):
            view["page"] = "tampered"
        self.assertEqual(dict(model.snapshot("files.win", "shell.owner")),
                         {"page": "home"})


if __name__ == "__main__":
    unittest.main()
