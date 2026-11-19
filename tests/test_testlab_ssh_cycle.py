import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from scripts.testlab_ssh_cycle import run_cycle, ssh_args

SHA = "ab" * 20
RUN = "12" * 16

class SecureTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.plan = self.root / "plan.json"
        self.plan.write_text(json.dumps({"version":1,"repository":"DevTunaSoft/Canopy",
                                         "commit":SHA,"checks":["unit","syntax"]}))
        self.key = self.root / "key"
        self.key.write_text("dummy")
        self.hosts = self.root / "known_hosts"
        self.hosts.write_text("dummy")
        self.out = self.root / "result.json"

    def fake(self, *, result="PASS", execution=0, checked=None):
        def runner(argv, **kwargs):
            if checked is not None:
                checked.append(argv)
            if argv[0] == "ssh" and "run_approved_test_plan" in argv[-1]:
                return subprocess.CompletedProcess(argv,execution,"","")
            if argv[0] == "scp" and argv[-2].startswith("canopy-test@"):
                self.out.write_text(json.dumps({
                    "schema_version":1,"status":result,
                    "checks":[{"name":"unit"},{"name":"syntax"}]}))
            return subprocess.CompletedProcess(argv,0,"","")
        return runner

    def test_known_hosts_and_fixed_transport(self):
        argv=ssh_args(self.key,self.hosts,2222)
        self.assertIn("StrictHostKeyChecking=yes",argv)
        self.assertIn("BatchMode=yes",argv)
        with self.assertRaises(ValueError):
            ssh_args(self.key,self.root/"unknown",2222)

    def test_success_keeps_guest_untrusted(self):
        calls=[]
        result=run_cycle(self.plan,RUN,self.key,self.hosts,self.out,runner=self.fake(checked=calls))
        self.assertEqual(result["status"],"PASS")
        self.assertEqual(len(calls),5)
        self.assertTrue(any("run_approved_test_plan" in str(c) for c in calls))
        self.assertTrue(any("PYTHONDONTWRITEBYTECODE=1 python3 -B" in str(c) for c in calls))

    def test_false_success_disagreement_rejected(self):
        with self.assertRaisesRegex(RuntimeError,"contradicts"):
            run_cycle(self.plan,RUN,self.key,self.hosts,self.out,
                      runner=self.fake(result="PASS",execution=1))

    def test_failed_guest_is_not_pass(self):
        result=run_cycle(self.plan,RUN,self.key,self.hosts,self.out,
                         runner=self.fake(result="FAIL",execution=1))
        self.assertEqual(result["status"],"FAIL")

    def test_reject_wrong_checkset_or_run_identifier(self):
        def fake_wrong(argv,**kwargs):
            if argv[0]=="scp" and argv[-2].startswith("canopy-test@"):
                self.out.write_text(json.dumps({"schema_version":1,"status":"PASS",
                                  "checks":[{"name":"gtk"}]}))
            return subprocess.CompletedProcess(argv,0,"","")
        with self.assertRaisesRegex(RuntimeError,"different checks"):
            run_cycle(self.plan,RUN,self.key,self.hosts,self.out,runner=fake_wrong)
        with self.assertRaises(ValueError):
            run_cycle(self.plan,"old",self.key,self.hosts,self.out,runner=self.fake())

    def test_refuse_existing_host_report(self):
        self.out.write_text('old report')
        with self.assertRaisesRegex(ValueError, "already exists"):
            run_cycle(self.plan, RUN, self.key, self.hosts, self.out,
                      runner=self.fake())

    def test_refuse_existing_guest_report(self):
        calls = []
        def stale(argv, **kwargs):
            calls.append(argv)
            if argv[0] == "ssh" and "test ! -e" in argv[-1]:
                return subprocess.CompletedProcess(argv, 1, "", "")
            return subprocess.CompletedProcess(argv, 0, "", "")
        with self.assertRaisesRegex(RuntimeError, "already exists"):
            run_cycle(self.plan, RUN, self.key, self.hosts, self.out, runner=stale)
        self.assertFalse(any(command[0] == "scp" for command in calls))

    def test_missing_report_is_not_success(self):
        with self.assertRaises(RuntimeError):
            run_cycle(self.plan,RUN,self.key,self.hosts,self.out,
                runner=lambda argv,**kw: subprocess.CompletedProcess(argv,0,"",""))

if __name__=="__main__":
    unittest.main()
