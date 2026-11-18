import subprocess
from pathlib import Path
import tempfile
import unittest
from scripts.probe_vbox_unattended import inspect_installer


UUID="11111111-2222-3333-4444-555555555555"


class UnattendedProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.iso=self.root/"mint.iso"
        self.iso.write_bytes(b"fake ISO for dry run shape test")
        self.pwd=self.root/"secret"
        self.pwd.write_bytes(b"fakepass")
        self.calls=[]
    def runner(self, args, **kwargs):
        self.calls.append(args)
        if "showvminfo" in args:
            return subprocess.CompletedProcess(args,0,
                'name="Canopy-Test-Mint"\nUUID="'+UUID+'"\nVMState="poweroff"\n',"")
        return subprocess.CompletedProcess(args,0,"","")
    def test_no_unintended_start(self):
        result=inspect_installer("VBoxManage",self.iso,self.pwd,runner=self.runner)
        self.assertFalse(result["installation_started"])
        self.assertIn("--dry-run",self.calls[-1])
        self.assertFalse(any("startvm" in args for args in self.calls))
        self.assertEqual(result["status"],"CAPABILITY_PROBE_PASSED")
    def test_missing_or_empty_credentials_blocked(self):
        self.pwd.write_bytes(b"")
        with self.assertRaises(ValueError):
            inspect_installer("VBoxManage",self.iso,self.pwd,runner=self.runner)
        self.assertEqual(self.calls,[])
    def test_real_unattended_unsupported_is_blocked(self):
        def reject(args,**kwargs):
            if "showvminfo" in args:
                return self.runner(args,**kwargs)
            return subprocess.CompletedProcess(args,1,"","Unsupported")
        result=inspect_installer("VBoxManage",self.iso,self.pwd,runner=reject)
        self.assertEqual(result["status"],"BLOCKED")
        self.assertEqual(result["exit_code"],1)


if __name__=="__main__":
    unittest.main()
