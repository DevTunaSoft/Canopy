"""Deterministic tests for Linux process CPU accounting."""
from pathlib import Path
import tempfile
import unittest
from scripts.cpu_metrics import measure, parse_proc_stat, read_ticks


def stat(comm="Canopy (test)", utime=20, stime=10, start=1234):
    # Linux /proc/PID/stat: after closing comm field, state is field 3.
    parts = ["S"] + ["0"] * 19
    parts[11] = str(utime)
    parts[12] = str(stime)
    parts[19] = str(start)
    return "77 (" + comm + ") " + " ".join(parts)


class CpuMetricsTests(unittest.TestCase):
    def test_parentheses_and_spaces_in_process_name(self):
        self.assertEqual(parse_proc_stat(stat("Canopy (desktop) preview")), (30, 1234))

    def test_malformed_or_negative_stats(self):
        for value in ("x", "7 (x) S 1", stat(utime=-1), stat(stime="oops")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_proc_stat(value)

    def test_own_process_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            proc = Path(directory) / "77"
            proc.mkdir()
            (proc / "stat").write_text(stat())
            owner = proc.stat().st_uid
            self.assertEqual(read_ticks(77, proc_root=Path(directory), uid=owner), (30, 1234))
            with self.assertRaises(PermissionError):
                read_ticks(77, proc_root=Path(directory), uid=owner + 1)
            with self.assertRaises(ValueError):
                read_ticks(True, proc_root=Path(directory))

    def test_cpu_percent_for_one_core(self):
        samples = iter([(10, 22), (60, 22)])
        moments = iter([1.0, 3.0])
        result = measure(77, interval=1, reader=lambda pid: next(samples),
                         clock=lambda: next(moments), sleep=lambda _: None,
                         ticks_per_second=100)
        self.assertEqual(result["cpu_seconds"], 0.5)
        self.assertEqual(result["cpu_percent_one_core"], 25.0)

    def test_reject_pid_reuse_and_bad_intervals(self):
        samples = iter([(10, 22), (11, 23)])
        with self.assertRaisesRegex(RuntimeError, "reused"):
            measure(77, reader=lambda _: next(samples), clock=lambda: 1.0,
                    sleep=lambda _: None, ticks_per_second=100)
        for interval in (0, -0.1, 31):
            with self.subTest(interval=interval), self.assertRaises(ValueError):
                measure(77, interval=interval)


if __name__ == "__main__":
    unittest.main()
