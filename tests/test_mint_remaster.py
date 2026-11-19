"""Offline regression checks for the disposable Mint ISO builder."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "Build-CanopyMintUnattendedISO.sh"
PRESEED = ROOT / "scripts" / "Generate-CanopyMintPreseed.py"

class MintRemasterTests(unittest.TestCase):
    def test_preseed_hash_and_vm_partitioning_contract(self):
        spec = importlib.util.spec_from_file_location("canopy_preseed", PRESEED)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        seed = module.make_preseed("$6$rounds$abcdef")
        self.assertIn("passwd/username string canopy-test", seed)
        self.assertIn("passwd/user-password-crypted password $6$rounds$abcdef", seed)
        self.assertIn("partman/confirm boolean true", seed)
        self.assertNotIn("12345678", seed)
        with self.assertRaises(ValueError):
            module.make_preseed("12345678")

    def test_builder_does_not_overwrite_source_or_existing_output(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "mint.iso"
            source.write_bytes(b"test iso")
            import hashlib
            sha = hashlib.sha256(source.read_bytes()).hexdigest()
            same = subprocess.run(["bash", str(BUILDER), str(source), sha, str(source)],
                                  capture_output=True, text=True)
            self.assertNotEqual(same.returncode, 0)
            self.assertEqual(source.read_bytes(), b"test iso")
            output = Path(d) / "output.iso"
            output.write_bytes(b"keep")
            existing = subprocess.run(["bash", str(BUILDER), str(source), sha, str(output)],
                                      capture_output=True, text=True)
            self.assertNotEqual(existing.returncode, 0)
            self.assertEqual(output.read_bytes(), b"keep")

    def test_bios_isolinux_requires_explicit_support(self):
        script = BUILDER.read_text(encoding="utf-8")
        self.assertIn("BIOS ISOLINUX/SYSLINUX unattended boot is not implemented", script)
        self.assertIn('grep -Eq --', script)
        self.assertLess(script.index("BIOS ISOLINUX/SYSLINUX unattended boot is not implemented"),
                        script.index("xorriso -osirrox on -indev"))

    def test_builder_requires_matching_source_hash(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "mint.iso"
            source.write_bytes(b"test iso")
            output = Path(d) / "output.iso"
            result = subprocess.run(["bash", str(BUILDER), str(source), "a" * 64, str(output)],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())

if __name__ == "__main__":
    unittest.main()
