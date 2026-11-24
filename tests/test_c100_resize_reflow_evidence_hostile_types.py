"""Fail-closed regression tests for hostile-but-bounded wrong-type inputs.

Every public entry point of ``resize_reflow_evidence`` must translate a
wrong-type caller value into the module's domain ``ValueError``. A raw
built-in exception (TypeError/KeyError/AttributeError) is a contract breach,
and no wrong-type input may yield a false reflow-safe PASS.
"""
import unittest

from canopy_features.accessibility import resize_reflow_evidence as evidence


class HostileWrongTypeTests(unittest.TestCase):
    # --- check_layout_contract: size -------------------------------------
    def test_size_string_is_rejected_with_domain_error(self):
        with self.assertRaisesRegex(ValueError, "size must be a .width, height. pair"):
            evidence.check_layout_contract(size="760x500")

    def test_size_wrong_arity_is_rejected_with_domain_error(self):
        with self.assertRaisesRegex(ValueError, "size must be a .width, height. pair"):
            evidence.check_layout_contract(size=(760, 500, 1))

    def test_size_mapping_is_rejected_with_domain_error(self):
        with self.assertRaisesRegex(ValueError, "size must be a .width, height. pair"):
            evidence.check_layout_contract(size={"width": 760, "height": 500})

    def test_size_bool_is_rejected_with_domain_error(self):
        with self.assertRaisesRegex(ValueError, "size must be a .width, height. pair"):
            evidence.check_layout_contract(size=True)

    def test_size_string_components_are_rejected_with_domain_error(self):
        with self.assertRaisesRegex(ValueError, "size components must be numbers"):
            evidence.check_layout_contract(size=("760", "500"))

    # --- check_layout_contract: sources ---------------------------------
    def test_sources_list_is_rejected_with_domain_error(self):
        with self.assertRaisesRegex(ValueError, "sources must be a mapping"):
            evidence.check_layout_contract(sources=["main", "theme", "preview"])

    def test_sources_missing_key_is_rejected_with_domain_error(self):
        with self.assertRaisesRegex(ValueError, "sources missing"):
            evidence.check_layout_contract(sources={"main": "x"})

    def test_sources_none_value_is_rejected_with_domain_error(self):
        sources = dict(evidence.load_sources())
        sources["main"] = None
        with self.assertRaisesRegex(ValueError, "QML source text"):
            evidence.check_layout_contract(sources=sources)

    def test_sources_bytes_value_is_rejected_with_domain_error(self):
        sources = dict(evidence.load_sources())
        sources["preview"] = b"clip: true"
        with self.assertRaisesRegex(ValueError, "QML source text"):
            evidence.check_layout_contract(sources=sources)

    def test_wrong_type_inputs_never_return_a_safe_verdict(self):
        hostile = (
            dict(size="760x500"),
            dict(size=True),
            dict(sources=[]),
            dict(sources={"main": None}),
        )
        for kwargs in hostile:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    report = evidence.check_layout_contract(**kwargs)
                    self.assertNotEqual(report["status"], "PASS")

    # --- load_sources: source_dir ---------------------------------------
    def test_load_sources_rejects_non_path_source_dir(self):
        with self.assertRaisesRegex(ValueError, "source_dir must be"):
            evidence.load_sources(source_dir=42)

    # --- evaluate: expression and variables -----------------------------
    def test_evaluate_rejects_non_string_expression(self):
        with self.assertRaisesRegex(ValueError, "expression must be a string"):
            evidence.evaluate(123, {})

    def test_evaluate_rejects_non_mapping_variables(self):
        with self.assertRaisesRegex(ValueError, "variables must be a mapping"):
            evidence.evaluate("root.width", None)

    def test_evaluate_missing_attribute_is_domain_error_not_keyerror(self):
        with self.assertRaisesRegex(ValueError, "unknown QML reference: root.width"):
            evidence.evaluate("root.width", {})

    # --- screenshot_evidence: path and size -----------------------------
    def test_screenshot_rejects_non_path_argument(self):
        with self.assertRaisesRegex(ValueError, "screenshot path must be"):
            evidence.screenshot_evidence(None, (760, 500))

    def test_screenshot_rejects_malformed_size(self):
        with self.assertRaisesRegex(ValueError, "screenshot size must be"):
            evidence.screenshot_evidence("x", 760)


if __name__ == "__main__":
    unittest.main()
