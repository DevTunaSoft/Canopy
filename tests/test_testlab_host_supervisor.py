"""Fake VM/SSH endpoints validate real coordinator composition without host access."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.testlab_host_supervisor import cycle, choose_action, require_config

SHA = "ab"*20
VMID = "11111111-2222-3333-4444-555555555555"


def report():
    return {"schema_version":1, "status":"PASS",
            "checks":[
                {"name":"unit","status":"PASS","exit_code":0,
                 "duration_seconds":1,"output":"Ran 3 tests in 0.1s\n\nOK\n",
                 "output_truncated":False},
                {"name":"syntax","status":"PASS","exit_code":0,
                 "duration_seconds":0.1,"output":"","output_truncated":False}
            ]}


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for name in ("vbox","key","hosts"):
            (self.root/name).write_text(name)
        (self.root/"approved.json").write_text(json.dumps({
            "version":1,"repository":"DevTunaSoft/Canopy","commit":SHA,
            "checks":["unit","syntax"]}))
        self.config={
            "vboxmanage":str(self.root/"vbox"),
            "expected_vm_uuid":VMID,
            "ssh_key":str(self.root/"key"),
            "known_hosts":str(self.root/"hosts"),
            "plan":str(self.root/"approved.json"),
            "evidence_directory":str(self.root/"evidence"),
            "ssh_port":2222
        }
    def test_one_host_run_and_no_duplicate_green(self):
        started=[]
        def guest(plan,run_id,key,hosts,output,**kwargs):
            output.write_text(json.dumps(report()))
            return {"status":"PASS","commit":SHA,"run_id":run_id}
        def start(exe,action):
            started.append(action)
            return {"status":"PASS","vm":{"uuid":VMID,"state":"running"}}
        result=cycle(self.config,inspect=lambda _:{"uuid":VMID,"state":"poweroff"},
                     operation=start,guest_cycle=guest)
        self.assertEqual(result["status"],"PASS_TEST_SUITE_NOT_RELEASE")
        self.assertFalse(result["release_certified"])
        self.assertEqual(started,["start"])
        repeated=cycle(self.config,inspect=lambda _:self.fail("no extra VM inspection"),
                       guest_cycle=lambda *_a,**_kw:self.fail("no duplicate test"))
        self.assertEqual(repeated["status"],"SKIP_ALREADY_GREEN")
        self.assertEqual(len(list((self.root/"evidence").glob("*-host.json"))),1)

    def test_failure_retries_capped_without_duplicate_infinite_execution(self):
        runs=[]
        def guest(plan,run_id,key,hosts,output,**kwargs):
            runs.append(run_id)
            output.write_text(json.dumps({**report(),"status":"FAIL"}))
            return {"status":"FAIL","commit":SHA,"run_id":run_id}
        for expected_attempt in range(1,4):
            result=cycle(self.config,inspect=lambda _:{"uuid":VMID,"state":"running"},
                         guest_cycle=guest)
            self.assertEqual(result["status"],"FAIL")
            self.assertEqual(result["attempts"],expected_attempt)
        fourth=cycle(self.config,inspect=lambda _:self.fail("fourth should not run"))
        self.assertEqual(fourth["status"],"BLOCKED_ATTEMPT_LIMIT")
        self.assertEqual(len(runs),3)

    def test_untrusted_guest_mismatch_inconclusive(self):
        def guest(plan,run_id,key,hosts,output,**kwargs):
            output.write_text(json.dumps(report()))
            return {"status":"PASS","commit":"cd"*20,"run_id":run_id}
        result=cycle(self.config,inspect=lambda _:{"uuid":VMID,"state":"running"},
                     guest_cycle=guest)
        self.assertEqual(result["status"],"INCONCLUSIVE")
        self.assertFalse(result["release_certified"])

    def test_wrong_vm_uuid_blocks_before_execution(self):
        with self.assertRaises(ValueError):
            cycle(self.config,inspect=lambda _:{"uuid":"2"*36,"state":"running"},
                  guest_cycle=lambda *_a,**kw:self.fail("must not run"))

    def test_reject_malformed_config_and_counter(self):
        with self.assertRaises(ValueError):
            require_config({**self.config,"extra":"unexpected"})
        with self.assertRaises(ValueError):
            choose_action({"plan_sha256":"abc","attempts":True,"status":"FAIL"},"abc")


if __name__=="__main__":
    unittest.main()
