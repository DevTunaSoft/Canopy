"""Offline regression tests for bounded, immutable dock pin ordering."""
from __future__ import annotations

import dataclasses
import inspect
import unittest

from canopy_features.dock import dock_pinned_items as pins


class PinnedItemsTests(unittest.TestCase):
    def test_empty_and_append(self):
        state = pins.empty()
        self.assertEqual(state.items, ())
        state = pins.add(state, "nemo")
        state = pins.add(state, "terminal")
        self.assertEqual(state.items, ("nemo", "terminal"))
        self.assertEqual(pins.index_of(state, "terminal"), 1)
        self.assertTrue(pins.contains(state, "nemo"))

    def test_duplicate_add_is_idempotent(self):
        state = pins.add(pins.empty(), "nemo")
        again = pins.add(state, "nemo")
        self.assertEqual(again, state)
        self.assertEqual(again.items.count("nemo"), 1)

    def test_duplicate_ids_are_rejected_at_construction(self):
        for items in (("nemo", "nemo"), ("a", "b", "a")):
            with self.subTest(items=items), self.assertRaises(ValueError):
                pins.PinnedItems(items=items)

    def test_replace_cannot_reintroduce_duplicate_ids(self):
        state = pins.add(pins.empty(), "nemo")
        with self.assertRaises(ValueError):
            dataclasses.replace(state, items=("nemo", "nemo"))

    def test_valid_pinned_state_still_constructs(self):
        state = pins.PinnedItems(items=("nemo", "terminal"))
        self.assertEqual(state.items, ("nemo", "terminal"))
        self.assertEqual(pins.index_of(state, "terminal"), 1)

    def test_remove_missing_id_is_idempotent(self):
        state = pins.add(pins.empty(), "nemo")
        self.assertEqual(pins.remove(state, "not-pinned"), state)
        self.assertEqual(pins.remove(state, "nemo").items, ())

    def test_remove_preserves_remaining_order(self):
        state = pins.apply_operations(pins.empty(), [
            ("add", "a", 0), ("add", "b", 0), ("add", "c", 0)])
        self.assertEqual(state.items, ("a", "b", "c"))
        self.assertEqual(pins.remove(state, "b").items, ("a", "c"))

    def test_move_clamps_target_index(self):
        state = pins.apply_operations(pins.empty(), [
            ("add", "a", 0), ("add", "b", 0), ("add", "c", 0)])
        self.assertEqual(pins.move(state, "a", 99).items, ("b", "c", "a"))
        self.assertEqual(pins.move(state, "c", -5).items, ("c", "a", "b"))

    def test_move_missing_id_is_noop(self):
        state = pins.add(pins.empty(), "nemo")
        self.assertEqual(pins.move(state, "missing", 0), state)

    def test_move_never_duplicates_an_id(self):
        state = pins.apply_operations(pins.empty(), [
            ("add", "a", 0), ("add", "b", 0)])
        moved = pins.move(state, "a", 1)
        self.assertEqual(moved.items, ("b", "a"))
        self.assertEqual(len(moved.items), len(set(moved.items)))

    def test_index_of_missing_id_is_minus_one(self):
        self.assertEqual(pins.index_of(pins.empty(), "nemo"), -1)

    def test_pin_cap_is_bounded(self):
        operations = [("add", f"app-{i}", 0) for i in range(pins.MAX_PINS + 5)]
        state = pins.apply_operations(pins.empty(), operations)
        self.assertEqual(len(state.items), pins.MAX_PINS)

    def test_states_are_immutable(self):
        state = pins.add(pins.empty(), "nemo")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            state.items = ()

    def test_invalid_identifiers_are_rejected(self):
        for app_id in ("", " x ", "x" * (pins.MAX_ID_LENGTH + 1), 7, None, b"x"):
            with self.subTest(app_id=app_id), self.assertRaises(ValueError):
                pins.add(pins.empty(), app_id)

    def test_invalid_target_index_is_rejected(self):
        state = pins.add(pins.empty(), "nemo")
        for target in ("0", 1.5, True, None):
            with self.subTest(target=target), self.assertRaises(ValueError):
                pins.move(state, "nemo", target)

    def test_operation_batches_are_bounded_and_validated(self):
        with self.assertRaises(ValueError):
            pins.apply_operations(pins.empty(), [("add", "x")] * 1025)
        for batch in ("not-a-batch", [("bogus", "x")], [None], [("add",)]):
            with self.subTest(batch=batch), self.assertRaises(ValueError):
                pins.apply_operations(pins.empty(), batch)

    def test_non_state_inputs_are_rejected(self):
        for call in (lambda: pins.contains([], "x"), lambda: pins.add([], "x"),
                     lambda: pins.remove([], "x"), lambda: pins.move([], "x", 0),
                     lambda: pins.index_of([], "x")):
            with self.assertRaises(ValueError):
                call()


class PurityTests(unittest.TestCase):
    def test_no_runtime_or_ui_dependencies(self):
        source = inspect.getsource(pins)
        for token in ("subprocess", "socket", "threading", "PyQt", "PySide",
                      "QML", " open(", "time.", "requests"):
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_only_dataclasses_is_imported(self):
        imports = [line.strip() for line in inspect.getsource(pins).splitlines()
                   if line.startswith(("import ", "from "))]
        self.assertEqual(imports, [
            "from __future__ import annotations",
            "from dataclasses import dataclass",
        ])


if __name__ == "__main__":
    unittest.main()
