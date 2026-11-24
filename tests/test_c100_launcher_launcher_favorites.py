"""Offline unit tests for bounded persistent launcher favorites.

No Qt runtime, desktop session, network or real Mint VM is involved. Tests
exercise stable-ID identity, duplicate adds, deleted apps, corrupt saved
state, bounds and atomic persistence. They do not prove a working desktop.
"""
import ast
import json
from pathlib import Path
import tempfile
import unittest

from canopy_features.launcher import launcher_favorites as favorites


class StableIdTests(unittest.TestCase):
    def test_id_contract(self):
        accepted = ("Browser", "a.desktop", "org.gnome.Nautilus.desktop",
                    "app_id-1.2+3", "x" * favorites.MAX_ID_BYTES)
        for value in accepted:
            with self.subTest(accepted=value):
                self.assertTrue(favorites.valid_app_id(value))
        rejected = ("", " leading", "trailing ", "a/b", "a:b", "a b",
                    "a\\b", "caf\u00e9", "-lead", "x" * (favorites.MAX_ID_BYTES + 1),
                    1, None, True, [], {})
        for value in rejected:
            with self.subTest(rejected=repr(value)):
                self.assertFalse(favorites.valid_app_id(value))

    def test_add_rejects_invalid_id_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "favorites.json"
            store = favorites.FavoritesStore(path)
            with self.assertRaises(favorites.FavoritesError):
                store.add("bad/id")
            self.assertEqual(store.ids(), ())
            self.assertFalse(path.exists())

    def test_path_argument_must_be_a_path(self):
        with self.assertRaises(favorites.FavoritesError):
            favorites.FavoritesStore(None)


class FavoritesStoreTests(unittest.TestCase):
    def setUp(self):
        self._temporary = tempfile.TemporaryDirectory()
        self.path = Path(self._temporary.name) / "config" / "favorites.json"

    def tearDown(self):
        self._temporary.cleanup()

    def test_add_remove_persist_and_reload(self):
        store = favorites.FavoritesStore(self.path)
        self.assertTrue(store.add("org.gnome.Nautilus.desktop"))
        self.assertTrue(store.add("org.gnome.Terminal.desktop"))
        expected = ("org.gnome.Nautilus.desktop", "org.gnome.Terminal.desktop")
        self.assertEqual(store.ids(), expected)
        self.assertEqual(len(store), 2)
        self.assertEqual(favorites.FavoritesStore(self.path).ids(), expected)

        reloaded = favorites.FavoritesStore(self.path)
        self.assertTrue(reloaded.remove("org.gnome.Nautilus.desktop"))
        self.assertFalse(reloaded.remove("org.gnome.Nautilus.desktop"))
        self.assertEqual(favorites.FavoritesStore(self.path).ids(),
                         ("org.gnome.Terminal.desktop",))

    def test_duplicate_adds_are_idempotent(self):
        store = favorites.FavoritesStore(self.path)
        self.assertTrue(store.add("org.example.Mail.desktop"))
        self.assertFalse(store.add("org.example.Mail.desktop"))
        self.assertFalse(store.add("org.example.Mail.desktop"))
        self.assertEqual(store.ids(), ("org.example.Mail.desktop",))
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(saved["favorites"], ["org.example.Mail.desktop"])

    def test_duplicate_ids_on_disk_are_rejected_as_corrupt(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({
            "version": 1,
            "favorites": ["a.desktop", "a.desktop"],
        }), encoding="utf-8")
        self.assertEqual(favorites.FavoritesStore(self.path).ids(), ())

    def test_deleted_apps_are_hidden_without_loss_then_pruned(self):
        store = favorites.FavoritesStore(self.path)
        for app_id in ("a.desktop", "b.desktop", "c.desktop"):
            self.assertTrue(store.add(app_id))
        installed = {"a.desktop", "c.desktop"}

        self.assertEqual(store.visible(installed), ("a.desktop", "c.desktop"))
        self.assertEqual(store.ids(), ("a.desktop", "b.desktop", "c.desktop"))
        self.assertEqual(store.visible(()), ())
        self.assertEqual(store.ids(), ("a.desktop", "b.desktop", "c.desktop"))

        self.assertTrue(store.prune(installed))
        self.assertEqual(store.ids(), ("a.desktop", "c.desktop"))
        self.assertEqual(favorites.FavoritesStore(self.path).ids(),
                         ("a.desktop", "c.desktop"))
        self.assertFalse(store.prune(installed))

    def test_bound_refuses_new_ids_and_keeps_existing(self):
        store = favorites.FavoritesStore(self.path)
        for index in range(favorites.MAX_FAVORITES):
            self.assertTrue(store.add("app%02d.desktop" % index))
        self.assertFalse(store.add("overflow.desktop"))
        self.assertFalse(store.add("app00.desktop"))
        self.assertEqual(len(store), favorites.MAX_FAVORITES)
        self.assertNotIn("overflow.desktop", store.ids())

    def test_ids_snapshot_is_immutable(self):
        store = favorites.FavoritesStore(self.path)
        store.add("a.desktop")
        snapshot = store.ids()
        self.assertIsInstance(snapshot, tuple)
        store.add("b.desktop")
        self.assertEqual(snapshot, ("a.desktop",))

    def test_save_is_atomic_and_leaves_no_temporary_files(self):
        store = favorites.FavoritesStore(self.path)
        store.add("a.desktop")
        leftovers = [item.name for item in self.path.parent.iterdir()
                     if item.name.startswith(".favorites-")]
        self.assertEqual(leftovers, [])
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")),
                         {"version": 1, "favorites": ["a.desktop"]})

    def test_corrupt_state_fails_closed_and_recovers_on_next_write(self):
        cases = {
            "not json": b"not json",
            "invalid utf-8": b"\xff\xfe",
            "wrong schema version": self._state(version=2, favorites=["a.desktop"]),
            "missing field": json.dumps({"version": 1}).encode("utf-8"),
            "extra field": self._state(extra=True),
            "wrong collection type": self._state(favorites="a.desktop"),
            "non string entry": self._state(favorites=[1]),
            "invalid id": self._state(favorites=["bad/id"]),
            "too many entries": self._state(
                favorites=["app%02d.desktop" % index
                           for index in range(favorites.MAX_FAVORITES + 1)]),
            "duplicate json key": b'{"version":1,"version":1,"favorites":[]}',
            "non-finite constant": b'{"version":1,"favorites":[],"extra":NaN}',
            "oversized file": b"x" * (favorites.MAX_STATE_BYTES + 1),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for name, payload in cases.items():
            with self.subTest(case=name):
                self.path.write_bytes(payload)
                store = favorites.FavoritesStore(self.path)
                self.assertEqual(store.ids(), ())
                self.assertTrue(store.add("recovered.desktop"))
                self.assertEqual(favorites.FavoritesStore(self.path).ids(),
                                 ("recovered.desktop",))

    @staticmethod
    def _state(**fields):
        state = {"version": 1, "favorites": []}
        state.update(fields)
        return json.dumps(state).encode("utf-8")


class ComponentBoundaryTests(unittest.TestCase):
    def test_no_polling_threads_processes_or_network(self):
        tree = ast.parse(Path(favorites.__file__).read_text(encoding="utf-8"))
        imports = set()
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                called.add(node.func.attr)
        self.assertTrue(imports.issubset(
            {"collections", "json", "os", "pathlib", "re", "tempfile"}))
        blocked = ("sleep", "start", "wait", "poll", "connect", "Popen", "launch")
        for token in blocked:
            with self.subTest(blocked=token):
                self.assertNotIn(token, called)


if __name__ == "__main__":
    unittest.main()
