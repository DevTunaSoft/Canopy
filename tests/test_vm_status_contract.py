from pathlib import Path
import unittest

SOURCE=(Path(__file__).resolve().parents[1]/"scripts/Get-CanopyVMStatus.ps1").read_text(encoding="utf-8")


class VmStatusContract(unittest.TestCase):
    def test_vm_identity_and_false_green_gates(self):
        for token in ('Canopy-Test-Mint','boot_verified=$false',
                      "mint_installed='NOT_VERIFIED'","cinnamon_tested='NOT_RUN'",
                      "guest_ssh='NOT_VERIFIED'",'VMState','UUID'):
            self.assertIn(token,SOURCE)

    def test_read_only_virtualbox(self):
        for forbidden in ('startvm','unregistervm','controlvm','snapshot restore',
                          'createmedium','storageattach','Remove-VM','Set-VM'):
            self.assertNotIn(forbidden,SOURCE)


if __name__=="__main__":
    unittest.main()
