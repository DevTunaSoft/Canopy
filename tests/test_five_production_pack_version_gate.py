"""Regression tests for the registered five-icon production-pack renderer gate.

The gate must accept exactly the renderer version declared by the compiled Qt
source and reject stale or unregistered versions. Registration is evidence-based:
the v3 renderer changed only Mail/Terminal/Settings; the frozen five stayed
pixel-identical in genuine compiled captures at 760x500, 1200x750 and 1920x1080.
"""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
QT = ROOT / "prototype" / "classic"
SOURCE_DIGEST = "5aa040ddbfeddbd38dcbd1808710676982efbc4146987c42e93eaa57ad0d4737"

if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location(
    "validate_five_production_icons_gate",
    TOOLS / "validate_five_production_icons.py",
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load the production-pack validator")
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


def registered_manifest(renderer: object = "canopy-five-qt-v3",
                        schema: object = 1, source: object = SOURCE_DIGEST):
    return {"schema_version": schema, "renderer": renderer,
            "source_manifest_sha256": source}


class FiveProductionPackVersionGateTests(unittest.TestCase):
    def test_registered_version_matches_compiled_renderer_exactly(self):
        self.assertEqual(VALIDATOR.EXPECTED_RENDERER, "canopy-five-qt-v3")
        provider = (QT / "RoundedDockIconProvider.cpp").read_text(encoding="utf-8")
        self.assertIn('constexpr auto kPackRenderer = "canopy-five-qt-v3";',
                      provider)
        self.assertNotIn('constexpr auto kPackRenderer = "canopy-five-qt-v2";',
                         provider)

    def test_registered_v3_provenance_is_accepted(self):
        self.assertIsNone(VALIDATOR.verify_pack_provenance(
            registered_manifest(), SOURCE_DIGEST))

    def test_stale_and_unregistered_renderers_are_rejected(self):
        for renderer in ("canopy-five-qt-v1", "canopy-five-qt-v2",
                         "canopy-five-qt-v3-alpha", "canopy-five-qt-v4",
                         "canopy-five-qt-v3 ", "", None, 3, [], {}):
            with self.subTest(renderer=renderer):
                with self.assertRaises(VALIDATOR.ProductionIconError):
                    VALIDATOR.verify_pack_provenance(
                        registered_manifest(renderer=renderer), SOURCE_DIGEST)
        missing = registered_manifest()
        del missing["renderer"]
        with self.assertRaises(VALIDATOR.ProductionIconError):
            VALIDATOR.verify_pack_provenance(missing, SOURCE_DIGEST)

    def test_schema_and_source_provenance_are_not_relaxed(self):
        for schema in (0, 2, "1", None, True):
            with self.subTest(schema=schema):
                with self.assertRaises(VALIDATOR.ProductionIconError):
                    VALIDATOR.verify_pack_provenance(
                        registered_manifest(schema=schema), SOURCE_DIGEST)
        with self.assertRaises(VALIDATOR.ProductionIconError):
            VALIDATOR.verify_pack_provenance(
                registered_manifest(source="0" * 64), SOURCE_DIGEST)
        with self.assertRaises(VALIDATOR.ProductionIconError):
            VALIDATOR.verify_pack_provenance([], SOURCE_DIGEST)

    def test_full_validator_delegates_to_the_exact_provenance_gate(self):
        text = (TOOLS / "validate_five_production_icons.py").read_text(
            encoding="utf-8")
        body = text.split("def verify_pack(", 1)[1].split("def main(", 1)[0]
        self.assertIn("verify_pack_provenance(pack, digest(mbytes))", body)
        self.assertNotIn('pack.get("renderer")', body)
        self.assertNotIn('startswith("canopy-five-qt")', text)
        self.assertNotIn("re.match", text)


if __name__ == "__main__":
    unittest.main()
