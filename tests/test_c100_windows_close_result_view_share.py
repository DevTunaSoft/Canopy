"""RED/GREEN identity test: IntentResult.state reuses the cached owned view."""
import unittest
from types import MappingProxyType

from canopy_features.windows import window_close_intents as c


class ResultViewShareTests(unittest.TestCase):
    def _model(self):
        model = c.CloseIntentModel()
        model.register("files.win", "shell.owner", state={"page": "home"})
        return model

    def test_result_state_shares_cached_view(self):
        model = self._model()
        result = model.request_close("files.win", "shell.owner")
        self.assertIsInstance(result.state, MappingProxyType)
        self.assertIs(result.state, model.snapshot("files.win", "shell.owner"))

    def test_reopened_result_shares_same_view(self):
        model = self._model()
        first = model.request_close("files.win", "shell.owner")
        second = model.reopen("files.win", "shell.owner")
        self.assertIs(first.state, second.state)
        self.assertIs(second.state, model.snapshot("files.win", "shell.owner"))

    def test_state_write_replaces_shared_view(self):
        model = self._model()
        before = model.request_close("files.win", "shell.owner")
        self.assertTrue(model.update_state("files.win", "shell.owner",
                                           page="settings"))
        after = model.request_close("files.win", "shell.owner")
        self.assertIsNot(after.state, before.state)
        self.assertEqual(dict(before.state), {"page": "home"})
        self.assertEqual(dict(after.state), {"page": "settings"})
        self.assertIs(after.state, model.snapshot("files.win", "shell.owner"))

    def test_denied_result_uses_shared_empty(self):
        model = self._model()
        result = model.request_close("nope.win", "shell.owner")
        self.assertIs(result.state, c.NO_STATE)

    def test_view_is_read_only(self):
        model = self._model()
        result = model.request_close("files.win", "shell.owner")
        with self.assertRaises(TypeError):
            result.state["page"] = "tampered"
        self.assertEqual(dict(model.snapshot("files.win", "shell.owner")),
                         {"page": "home"})


if __name__ == "__main__":
    unittest.main()
