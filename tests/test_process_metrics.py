import tempfile
from pathlib import Path
import unittest
from scripts.process_metrics import parse_status, read_memory, sample


class ProcessMetricsTests(unittest.TestCase):
    def test_parse_memory(self):
        self.assertEqual(parse_status("Name: canopy\nVmRSS:  2048 kB\nVmHWM: 4096 kB\n"),
                         {"vmrss_kib": 2048, "vmhwm_kib": 4096})

    def test_reject_malformed(self):
        with self.assertRaises(ValueError):
            parse_status("VmRSS: 1 MB")

    def test_uid_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "42"
            path.mkdir()
            (path / "status").write_text("VmRSS: 12 kB\n")
            self.assertEqual(read_memory(42, proc_root=Path(directory), uid=path.stat().st_uid),
                             {"vmrss_kib": 12})
            with self.assertRaises(PermissionError):
                read_memory(42, proc_root=Path(directory), uid=path.stat().st_uid + 1)

    def test_sample_peak_and_process_exit(self):
        states = iter([{"vmrss_kib": 12, "vmhwm_kib": 12},
                       {"vmrss_kib": 20, "vmhwm_kib": 21}])
        def reader(_pid):
            try:
                return next(states)
            except StopIteration:
                raise FileNotFoundError()
        report = sample(42, samples=4, interval=0, reader=reader, sleep=lambda _: None)
        self.assertEqual(report["samples"], 2)
        self.assertEqual(report["rss_peak_observed_kib"], 20)
        self.assertEqual(report["hwm_reported_kib"], 21)

    def test_bounded_inputs_and_missing(self):
        for samples, interval in [(0, 0.1), (121, 0.1), (2, -1), (2, 11)]:
            with self.assertRaises(ValueError):
                sample(4, samples=samples, interval=interval)
        with self.assertRaises(RuntimeError):
            sample(4, reader=lambda _: (_ for _ in ()).throw(FileNotFoundError()))


if __name__ == "__main__":
    unittest.main()
