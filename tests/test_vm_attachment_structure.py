"""Prevent accidental duplication or truncation of the VM ISO attachment script."""
from pathlib import Path
import re
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / "scripts" /
          "Attach-CanopyPreparedISO.ps1")


class AttachmentStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding="utf-8-sig")

    def test_no_duplicate_functions(self):
        names = re.findall(r"(?im)^function\s+([\w-]+)\b", self.source)
        self.assertTrue(names, "Expected PowerShell functions")
        self.assertEqual(len(names), len(set(n.casefold() for n in names)))

    def test_single_execution_path(self):
        for marker in (
            "if ($SelfTest) {",
            "Assert-Input $IsoPath $IsoSha256",
            "$verifiedInfo = @(& $vbox showvminfo",
            "Assert-AttachedIso ($verifiedInfo | Out-String) $iso",
            "if ($Start) {",
        ):
            with self.subTest(marker=marker):
                self.assertEqual(self.source.count(marker), 1)

    def test_no_code_after_final_status(self):
        marker = "} else { 'Prepared ISO attached; VM not started.' }"
        self.assertEqual(self.source.count(marker), 1)
        self.assertFalse(self.source.split(marker, 1)[1].strip())

    def test_iso_readback_precedes_vm_start(self):
        source = self.source
        self.assertLess(source.index("Assert-AttachedIso ($verifiedInfo | Out-String) $iso"),
                        source.index("& $vbox startvm 'Canopy-Test-Mint'"))


if __name__ == "__main__":
    unittest.main()
