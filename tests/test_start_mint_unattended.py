import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

from scripts.start_mint_unattended import start


UUID="11111111-2222-3333-4444-555555555555"

class MintInstallAttemptTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.iso=Path(self.tmp.name)/"mint.iso"
        self.iso.write_bytes(b"small fake fixture")
        self.password=Path(self.tmp.name)/"password.txt"
        self.password.write_text("only synthetic")
        self.digest=hashlib.sha256(self.iso.read_bytes()).hexdigest()
        self.calls=[]
    def mock(self, argv, **_kwargs):
        self.calls.append(argv)
        if argv[1:2]==["showvminfo"]:
            text='name="Canopy-Test-Mint"\nUUID="'+UUID+'"\nVMState="poweroff"\n'
            return subprocess.CompletedProcess(argv,0,text,"")
        return subprocess.CompletedProcess(argv,0,"","")
    def test_requires_authorization_and_matching_checksum(self):
        with self.assertRaises(PermissionError):
            start("VBoxManage",self.iso,self.password,self.digest,UUID,runner=self.mock)
        with self.assertRaises(ValueError):
            start("VBoxManage",self.iso,self.password,"0"*64,UUID,
                  authorized=True,runner=self.mock)
        self.assertEqual(self.calls,[])
    def test_only_dedicated_vm_with_dry_run_first(self):
        result=start("VBoxManage",self.iso,self.password,self.digest,UUID,
                     authorized=True,runner=self.mock)
        self.assertEqual(result["status"],"INSTALL_STARTED_NOT_VERIFIED")
        self.assertFalse(result["os_installed"])
        self.assertTrue(any("--dry-run" in c for c in self.calls))
        self.assertTrue(any("--start-vm=headless" in c for c in self.calls))
        self.assertEqual(self.calls[-1][:4],["VBoxManage","unattended","install","Canopy-Test-Mint"])
    def test_dry_run_failure_never_starts_vm(self):
        def reject(argv,**kwargs):
            if "--dry-run" in argv:
                self.calls.append(argv)
                return subprocess.CompletedProcess(argv,1,"","")
            return self.mock(argv,**kwargs)
        with self.assertRaises(RuntimeError):
            start("VBoxManage",self.iso,self.password,self.digest,UUID,
                  authorized=True,runner=reject)
        self.assertFalse(any("--start-vm=headless" in c for c in self.calls))

if __name__=="__main__":
    unittest.main()
