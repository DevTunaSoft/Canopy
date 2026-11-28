"""Synthetic contract tests for the M4 runtime-outcome mapping.

These are evidence-tooling tests under scratch/native_suspend; they are not
part of Foundation CI's ``unittest discover -s tests``. No VM, guest, D-Bus,
X11 or host action is performed. All observations are constructed in process.
"""
import unittest

from canopy_features.reliability import suspend_resume_contracts as decisions
from canopy_features.reliability import suspend_resume_native as native


def observation(label="NATIVE RUNTIME", *, dock=True, launcher=True,
                window=True, suspend=True, resume=True,
                during_shell=False):
    return {
        "evidence_label": label,
        "before": {
            "shell_active": True, "dock_visible": dock,
            "launcher_visible": launcher, "window_visible": window,
        },
        "during": {
            "shell_active": during_shell, "suspend_confirmed": suspend,
        },
        "after": {
            "shell_active": True, "dock_visible": dock,
            "launcher_visible": launcher, "window_visible": window,
            "resume_confirmed": resume,
        },
    }


class RuntimeOutcomeTests(unittest.TestCase):
    def test_directive_vocabulary_is_exact(self):
        self.assertEqual(decisions.EVIDENCE_LABELS, frozenset({
            "STATIC SOURCE ONLY", "SYNTHETIC", "CI-SCOPED", "NATIVE RUNTIME"}))
        self.assertEqual(decisions.OUTCOMES,
                         frozenset({"PASS", "FAIL", "BLOCKED", "NOT RUN"}))
        self.assertIs(native.EVIDENCE_LABELS, decisions.EVIDENCE_LABELS)
        self.assertIs(native.OUTCOMES, decisions.OUTCOMES)

    def test_full_native_observation_passes(self):
        result = native.runtime_outcome(observation())
        self.assertEqual(result.to_dict(), {
            "evidence_label": "NATIVE RUNTIME", "outcome": "PASS",
            "reason": "suspend-resume-recovery-verified"})

    def test_unobserved_desktop_facts_are_not_run_not_fail(self):
        record = observation()
        record["after"]["dock_visible"] = None
        result = native.runtime_outcome(record)
        self.assertEqual(result.outcome, "NOT RUN")
        self.assertEqual(result.reason, "desktop-state-not-reobserved")

    def test_synthetic_report_never_becomes_native_pass(self):
        for label in ("SYNTHETIC", "STATIC SOURCE ONLY", "CI-SCOPED"):
            with self.subTest(label=label):
                result = native.runtime_outcome(observation(label=label))
                self.assertEqual(result.outcome, "BLOCKED")
                self.assertEqual(result.reason, "non-native-evidence")

    def test_missing_suspend_or_resume_is_not_run(self):
        self.assertEqual(
            native.runtime_outcome(observation(suspend=False)).reason,
            "suspend-not-observed")
        self.assertEqual(
            native.runtime_outcome(observation(resume=False)).reason,
            "resume-not-observed")

    def test_contradictory_or_absent_desktop_facts_fail(self):
        self.assertEqual(
            native.runtime_outcome(observation(during_shell=True)).reason,
            "shell-active-during-suspend")
        for key in ("dock_visible", "launcher_visible", "window_visible"):
            with self.subTest(key=key):
                record = observation()
                record["before"][key] = False
                self.assertEqual(
                    native.runtime_outcome(record).reason,
                    "desktop-state-not-observed")

    def test_hostile_shapes_fail_closed(self):
        bad = [
            None, "NATIVE RUNTIME", 7, {},
            {**observation(), "extra": True},
            {**observation(), "before": None},
            {**observation(), "evidence_label": "native runtime"},
            {**observation(), "evidence_label": 7},
        ]
        for value in bad:
            with self.subTest(value=value):
                with self.assertRaises(native.SuspendResumeNativeError):
                    native.runtime_outcome(value)
        record = observation()
        record["during"]["shell_active"] = "false"
        with self.assertRaises(native.SuspendResumeNativeError):
            native.runtime_outcome(record)
        record = observation()
        del record["after"]["resume_confirmed"]
        with self.assertRaises(native.SuspendResumeNativeError):
            native.runtime_outcome(record)

    def test_mapping_is_pure(self):
        from pathlib import Path
        for module in (decisions, native):
            source = Path(str(module.__file__)).read_text(encoding="utf-8")
            for forbidden in ("subprocess", "socket", "os.system", "VBoxManage",
                              "time.sleep", "QTimer", "open("):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
