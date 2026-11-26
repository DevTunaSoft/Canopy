"""Deterministic fixture tests for the read-only Linux resource probe.

All numbers here come from synthetic /proc fixtures. No real Linux Mint,
desktop-session, GPU or screen-reader measurement is claimed by this module.
"""
import json
import tempfile
import unittest
from pathlib import Path

from tools.qa.linux_resource_probe import (
    MAX_INTERVAL_SECONDS,
    MeasurementError,
    build_startup_timings,
    build_wakeups,
    compute_cpu,
    read_cpu_ticks,
    read_memory,
    read_wakeups,
    validate_scope,
    main,
    measure,
)


class LinuxResourceProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.proc = Path(self.temp.name)

    def _pid_dir(self, pid):
        path = self.proc / str(pid)
        path.mkdir()
        return path

    def test_read_memory_from_smaps_rollup(self):
        pid_dir = self._pid_dir(4242)
        (pid_dir / "smaps_rollup").write_text(
            "Rss:               8192 kB\nPss:               4096 kB\n"
            "Shared_Clean:         0 kB\nPrivate_Dirty:     4096 kB\n",
            encoding="utf-8",
        )
        self.assertEqual(
            read_memory(4242, self.proc),
            {"pid": 4242, "pss_kib": 4096, "rss_kib": 8192,
             "source": "smaps_rollup"},
        )


    def test_read_memory_falls_back_to_smaps_sum(self):
        pid_dir = self._pid_dir(4243)
        (pid_dir / "smaps").write_text(
            "00400000-00500000 r-xp 00000000 00:00 0 /bin/example\n"
            "Size:                  4 kB\nRss:                   4 kB\n"
            "Pss:                   2 kB\nVmFlags: rd ex mr\n"
            "00600000-00700000 rw-p 00000000 00:00 0\n"
            "Size:                  8 kB\nRss:                   8 kB\n"
            "Pss:                   3 kB\n",
            encoding="utf-8",
        )
        self.assertEqual(
            read_memory(4243, self.proc),
            {"pid": 4243, "pss_kib": 5, "rss_kib": 12, "source": "smaps"},
        )

    def test_read_memory_rejects_malformed_rollup(self):
        pid_dir = self._pid_dir(4244)
        (pid_dir / "smaps_rollup").write_text(
            "Rss: 10 kB\nPss: not-a-number kB\n", encoding="utf-8"
        )
        with self.assertRaises(MeasurementError):
            read_memory(4244, self.proc)

    def test_read_memory_reports_missing_pss_as_null(self):
        pid_dir = self._pid_dir(4245)
        (pid_dir / "smaps_rollup").write_text("Rss: 10 kB\n", encoding="utf-8")
        self.assertEqual(read_memory(4245, self.proc)["pss_kib"], None)

    def test_read_memory_rejects_wrong_pid_type(self):
        with self.assertRaises(MeasurementError):
            read_memory(True, self.proc)


    def test_compute_cpu_from_bounded_interval(self):
        start = {"pid": 4242, "ticks": 100, "start_time_ticks": 77}
        end = {"pid": 4242, "ticks": 160, "start_time_ticks": 77}
        result = compute_cpu([start], [end], clock_ticks_per_second=100,
                             elapsed_seconds=2.0, interval_seconds=2.0)
        self.assertEqual(result["processes"][0]["delta_ticks"], 60)
        self.assertEqual(result["processes"][0]["percent_of_one_core"], 30.0)
        self.assertEqual(result["total_percent_of_one_core"], 30.0)

    def test_compute_cpu_rejects_unbounded_interval(self):
        with self.assertRaises(MeasurementError):
            compute_cpu([], [], clock_ticks_per_second=100,
                        elapsed_seconds=MAX_INTERVAL_SECONDS + 1,
                        interval_seconds=MAX_INTERVAL_SECONDS + 1)

    def test_compute_cpu_rejects_pid_reuse(self):
        start = {"pid": 4242, "ticks": 10, "start_time_ticks": 77}
        end = {"pid": 4242, "ticks": 20, "start_time_ticks": 88}
        with self.assertRaises(MeasurementError):
            compute_cpu([start], [end], 100, 1.0, 1.0)

    def test_read_cpu_ticks_from_stat_fixture(self):
        pid_dir = self._pid_dir(4246)
        (pid_dir / "stat").write_text(
            "4246 (canopy shell) S 1 0 0 0 -1 4194560 7 3 0 0 "
            "10 20 0 0 20 0 1 0 12345 0\n",
            encoding="utf-8",
        )
        self.assertEqual(
            read_cpu_ticks(4246, self.proc),
            {"pid": 4246, "ticks": 30, "start_time_ticks": 12345},
        )


    def test_read_wakeups_from_sched_fixture(self):
        pid_dir = self._pid_dir(4247)
        (pid_dir / "sched").write_text(
            "se.sum_exec_runtime : 1234.567\n"
            "nr_switches : 90\n"
            "nr_wakeups : 42\n",
            encoding="utf-8",
        )
        self.assertEqual(read_wakeups(4247, self.proc), 42)

    def test_build_wakeups_reports_not_available_without_relabeling(self):
        pid_dir = self._pid_dir(4248)
        (pid_dir / "status").write_text(
            "Name:\ttest\nvoluntary_ctxt_switches:\t12\n"
            "nonvoluntary_ctxt_switches:\t3\n",
            encoding="utf-8",
        )
        result = build_wakeups([4248], self.proc)
        self.assertEqual(result["status"], "NOT_AVAILABLE")
        self.assertEqual(result["processes"][0]["wakeups"], None)
        self.assertEqual(result["context_switches"][0]["voluntary"], 12)
        self.assertIn("not scheduler wakeups", result["note"])


    def test_startup_timings_from_supplied_timestamps(self):
        result = build_startup_timings({
            "launch_request": 1.0, "process_spawn": 1.05,
            "first_frame": 1.3, "ready": 1.4,
        })
        self.assertEqual(result["status"], "AVAILABLE")
        self.assertEqual(result["phases_ms"], {
            "launch_request": 0.0, "process_spawn": 50.0,
            "first_frame": 300.0, "ready": 400.0,
        })
        self.assertEqual(result["total_ready_ms"], 400.0)

    def test_startup_timings_reject_out_of_order_phases(self):
        with self.assertRaises(MeasurementError):
            build_startup_timings({
                "launch_request": 0.0, "first_frame": 2.0, "ready": 1.0,
            })

    def test_startup_timings_reject_unknown_phase(self):
        with self.assertRaises(MeasurementError):
            build_startup_timings({"launch_request": 0.0, "bogus": 1.0})

    def test_startup_timings_reject_nonfinite_value(self):
        with self.assertRaises(MeasurementError):
            build_startup_timings({"launch_request": float("inf")})

    def test_startup_timings_reject_wrong_container(self):
        with self.assertRaises(MeasurementError):
            build_startup_timings([0.0, 1.0])


    def test_validate_scope_normalizes_and_sorts(self):
        scope = validate_scope(
            [{"pid": 22, "label": "shell", "reason": "shell-owned"},
             {"pid": 11, "label": "agent", "reason": "shell-owned"}],
            [{"pid": 33, "label": "cinnamon", "reason": "system compositor"}],
        )
        self.assertEqual([p["pid"] for p in scope["included_processes"]], [11, 22])
        self.assertEqual([p["pid"] for p in scope["excluded_processes"]], [33])
        self.assertIn("not kernel-verified", scope["basis"])

    def test_validate_scope_rejects_pid_in_both_sets(self):
        with self.assertRaises(MeasurementError):
            validate_scope(
                [{"pid": 11, "label": "shell", "reason": "owned"}],
                [{"pid": 11, "label": "other", "reason": "not owned"}],
            )

    def test_validate_scope_rejects_duplicate_included_pid(self):
        entry = {"pid": 11, "label": "shell", "reason": "owned"}
        with self.assertRaises(MeasurementError):
            validate_scope([entry, dict(entry)], [])

    def test_validate_scope_rejects_control_character_label(self):
        with self.assertRaises(MeasurementError):
            validate_scope(
                [{"pid": 11, "label": "shell\ncompositor", "reason": "owned"}], []
            )

    def test_build_wakeups_rejects_unhashable_pid(self):
        with self.assertRaises(MeasurementError):
            build_wakeups([[11]], self.proc)


    def _write_stat(self, pid, ticks):
        (self.proc / str(pid) / "stat").write_text(
            f"{pid} (canopy) S 1 0 0 0 -1 0 0 0 0 0 "
            f"{ticks} 0 0 0 20 0 1 0 77 0\n",
            encoding="utf-8",
        )

    def _add_measurement_pid(self, pid, *, pss, rss, ticks, wakeups=None):
        pid_dir = self._pid_dir(pid)
        (pid_dir / "smaps_rollup").write_text(
            f"Rss: {rss} kB\nPss: {pss} kB\n", encoding="utf-8"
        )
        self._write_stat(pid, ticks)
        (pid_dir / "status").write_text(
            "voluntary_ctxt_switches:\t5\nnonvoluntary_ctxt_switches:\t1\n",
            encoding="utf-8",
        )
        if wakeups is not None:
            (pid_dir / "sched").write_text(f"nr_wakeups : {wakeups}\n", encoding="utf-8")

    def test_measure_produces_labelled_fixture_report(self):
        self._add_measurement_pid(11, pss=100, rss=200, ticks=10, wakeups=7)
        self._add_measurement_pid(22, pss=50, rss=90, ticks=20)
        clock_values = iter([10.0, 12.0])

        def fake_sleep(_interval):
            self._write_stat(11, 130)
            self._write_stat(22, 220)

        report = measure(
            [11, 22], proc_root=self.proc, source="fixture", session="fixture",
            interval_seconds=2.0, clock_ticks_per_second=100,
            clock=lambda: next(clock_values), sleep=fake_sleep,
            included=[
                {"pid": 22, "label": "agent", "reason": "shell-owned"},
                {"pid": 11, "label": "shell", "reason": "shell-owned"},
            ],
            excluded=[{"pid": 99, "label": "compositor", "reason": "system service"}],
            startup_timestamps={"launch_request": 1.0, "ready": 1.4},
        )
        self.assertEqual(report["source"], "fixture")
        self.assertEqual(report["evidence_class"], "SYNTHETIC")
        self.assertFalse(report["environment_attested"])
        self.assertEqual(report["cpu"]["total_percent_of_one_core"], 160.0)
        self.assertEqual(report["memory"]["totals"]["pss_kib_peak"], 150)
        self.assertEqual(report["wakeups"]["status"], "AVAILABLE")
        self.assertEqual(report["startup"]["total_ready_ms"], 400.0)
        self.assertEqual(
            [item["pid"] for item in report["scope"]["included_processes"]], [11, 22]
        )
        self.assertEqual(report["acceptance"]["linux_mint"], "NOT_RUN")
        self.assertEqual(report["acceptance"]["screen_reader"], "NOT_RUN")
        self.assertFalse(report["acceptance"]["release_ready"])
        self.assertEqual(report["targets"]["status"], "TARGETS_NOT_ACHIEVEMENTS")
        self.assertEqual(report["targets"]["windows_working_set_substitution"], "NOT_USED")
        self.assertNotIn("WorkingSet", __import__("json").dumps(report))

    def test_measure_rejects_pid_missing_from_included_scope(self):
        self._add_measurement_pid(11, pss=100, rss=200, ticks=10)
        with self.assertRaises(MeasurementError):
            measure(
                [11], proc_root=self.proc, source="fixture", clock_ticks_per_second=100,
                clock=lambda: 1.0, sleep=lambda _: None, included=[], excluded=[],
            )

    def test_measure_proc_source_is_scoped_not_mint_acceptance(self):
        self._add_measurement_pid(11, pss=100, rss=200, ticks=10)
        clock_values = iter([1.0, 2.0])
        report = measure(
            [11], proc_root=self.proc, source="proc",
            session="linux-mint-guest-unverified", clock_ticks_per_second=100,
            clock=lambda: next(clock_values), sleep=lambda _: None,
            included=[{"pid": 11, "label": "shell", "reason": "owned"}], excluded=[],
        )
        self.assertEqual(report["evidence_class"], "LINUX_PROC_SCOPED")
        self.assertFalse(report["environment_attested"])
        self.assertEqual(report["acceptance"]["linux_mint"], "NOT_RUN")

    def test_measure_rejects_unknown_source(self):
        with self.assertRaises(MeasurementError):
            measure([], proc_root=self.proc, source="windows-working-set")

    def test_measure_reports_startup_not_run_when_absent(self):
        clock_values = iter([1.0, 2.0])
        report = measure(
            [], proc_root=self.proc, source="fixture", session="fixture",
            clock_ticks_per_second=100, clock=lambda: next(clock_values),
            sleep=lambda _: None, included=[], excluded=[],
        )
        self.assertEqual(report["startup"]["status"], "NOT_RUN")

    def test_cli_writes_labelled_report_without_mutating_fixture(self):
        self._add_measurement_pid(11, pss=100, rss=200, ticks=10, wakeups=7)
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        scope = work.name + "/scope.json"
        startup = work.name + "/startup.json"
        output = work.name + "/report.json"
        Path(scope).write_text(
            '{"included_processes":[{"pid":11,"label":"shell","reason":"owned"}],'
            '"excluded_processes":[]}\n', encoding="utf-8"
        )
        Path(startup).write_text(
            '{"launch_request":0.0,"ready":0.25}\n', encoding="utf-8"
        )
        before = {
            path: (path.read_bytes(), path.stat().st_mtime_ns)
            for path in self.proc.rglob("*") if path.is_file()
        }
        code = main([
            "--pid", "11", "--proc-root", str(self.proc), "--source", "fixture",
            "--session", "fixture", "--interval", "0.01",
            "--clock-ticks-per-second", "100", "--scope", scope,
            "--startup", startup, "--output", output,
        ])
        after = {
            path: (path.read_bytes(), path.stat().st_mtime_ns)
            for path in self.proc.rglob("*") if path.is_file()
        }
        self.assertEqual(code, 0)
        self.assertEqual(before, after)
        import json
        report = json.loads(Path(output).read_text(encoding="utf-8"))
        self.assertEqual(report["evidence_class"], "SYNTHETIC")
        self.assertEqual(report["startup"]["total_ready_ms"], 250.0)

    def test_cli_rejects_duplicate_scope_json_keys(self):
        scope = self.temp.name + "/dup-scope.json"
        Path(scope).write_text(
            '{"included_processes":[],"included_processes":[],'
            '"excluded_processes":[]}\n', encoding="utf-8"
        )
        code = main(["--pid", "11", "--proc-root", str(self.proc),
                     "--source", "fixture", "--scope", scope])
        self.assertEqual(code, 2)

    def test_cli_refuses_output_inside_proc_root(self):
        self._add_measurement_pid(11, pss=100, rss=200, ticks=10)
        scope = self.temp.name + "/scope.json"
        Path(scope).write_text(
            '{"included_processes":[{"pid":11,"label":"shell","reason":"owned"}],'
            '"excluded_processes":[]}\n', encoding="utf-8"
        )
        output = self.proc / "11" / "report.json"
        code = main(["--pid", "11", "--proc-root", str(self.proc),
                     "--source", "fixture", "--scope", scope,
                     "--output", str(output)])
        self.assertEqual(code, 2)
        self.assertFalse(output.exists())


    # Regression: a modern smaps_rollup carries unitless non-memory fields
    # (THPEligible on some kernels, ProtectionKey and VmFlags on all of them).
    # These are not "N kB" lines and must not make --source proc fail closed.
    _REALISTIC_ROLLUP = (
        "Rss:                8192 kB\n"
        "Pss:                4096 kB\n"
        "Pss_Anon:           3072 kB\n"
        "Pss_File:            896 kB\n"
        "Pss_Shmem:           128 kB\n"
        "Shared_Clean:        512 kB\n"
        "Shared_Dirty:        256 kB\n"
        "Private_Clean:       768 kB\n"
        "Private_Dirty:      6656 kB\n"
        "Referenced:         7808 kB\n"
        "Anonymous:          6144 kB\n"
        "KSM:                   0 kB\n"
        "LazyFree:              0 kB\n"
        "AnonHugePages:         0 kB\n"
        "ShmemPmdMapped:        0 kB\n"
        "FilePmdMapped:         0 kB\n"
        "Shared_Hugetlb:        0 kB\n"
        "Private_Hugetlb:       0 kB\n"
        "Swap:                  0 kB\n"
        "SwapPss:               0 kB\n"
        "Locked:                0 kB\n"
        "THPEligible:          12\n"
        "ProtectionKey:         0\n"
        "VmFlags: rd ex wr mr mp\n"
    )

    def test_read_memory_accepts_realistic_rollup_unitless_fields(self):
        pid_dir = self._pid_dir(4300)
        (pid_dir / "smaps_rollup").write_text(
            self._REALISTIC_ROLLUP, encoding="utf-8", newline="\n"
        )
        self.assertEqual(
            read_memory(4300, self.proc),
            {"pid": 4300, "pss_kib": 4096, "rss_kib": 8192,
             "source": "smaps_rollup"},
        )

    def test_measure_proc_source_accepts_realistic_rollup(self):
        self._pid_dir(4301)
        (self.proc / "4301" / "smaps_rollup").write_text(
            self._REALISTIC_ROLLUP, encoding="utf-8", newline="\n"
        )
        self._write_stat(4301, 10)
        clock_values = iter([1.0, 2.0])
        report = measure(
            [4301], proc_root=self.proc, source="proc", session="linux-host",
            clock_ticks_per_second=100, clock=lambda: next(clock_values),
            sleep=lambda _: None,
            included=[{"pid": 4301, "label": "shell", "reason": "owned"}],
            excluded=[],
        )
        self.assertEqual(report["evidence_class"], "LINUX_PROC_SCOPED")
        sample = report["memory"]["samples"]["start"][0]
        self.assertEqual(sample["source"], "smaps_rollup")
        self.assertEqual(sample["pss_kib"], 4096)
        self.assertEqual(sample["rss_kib"], 8192)

    # Negative controls: relaxing the rollup parser must not relax the
    # strict "N kB" contract for real memory fields or their bounds.
    def test_read_memory_rejects_malformed_kib_line_beside_unitless_fields(self):
        pid_dir = self._pid_dir(4302)
        (pid_dir / "smaps_rollup").write_text(
            "Rss: 10 kB\nPss: not-a-number kB\nVmFlags: rd ex\n",
            encoding="utf-8", newline="\n",
        )
        with self.assertRaises(MeasurementError):
            read_memory(4302, self.proc)

    def test_read_memory_rejects_out_of_range_kib_value(self):
        pid_dir = self._pid_dir(4303)
        (pid_dir / "smaps_rollup").write_text(
            f"Rss: {1 << 21} kB\nPss: 5 kB\nTHPEligible: 12\n",
            encoding="utf-8", newline="\n",
        )
        with self.assertRaises(MeasurementError):
            read_memory(4303, self.proc)

    def test_read_memory_rejects_unknown_unitless_line(self):
        pid_dir = self._pid_dir(4304)
        (pid_dir / "smaps_rollup").write_text(
            "Rss: 10 kB\nPss: 5 kB\nUnexpectedUnitless: 7\n",
            encoding="utf-8", newline="\n",
        )
        with self.assertRaises(MeasurementError):
            read_memory(4304, self.proc)

    # Path containment: only the final component was checked before, so a
    # symlinked parent could redirect a proc read outside proc_root.
    def test_read_memory_rejects_symlinked_parent_under_proc_root(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        real_pid = outside / "4305"
        real_pid.mkdir()
        (real_pid / "smaps_rollup").write_text(
            "Rss: 10 kB\nPss: 5 kB\n", encoding="utf-8", newline="\n"
        )
        (self.proc / "4305").symlink_to(real_pid, target_is_directory=True)
        with self.assertRaises(MeasurementError):
            read_memory(4305, self.proc)

    def test_read_memory_rejects_symlinked_smaps_rollup_file(self):
        pid_dir = self._pid_dir(4306)
        target = Path(self.temp.name) / "rollup-target"
        target.write_text("Rss: 10 kB\nPss: 5 kB\n", encoding="utf-8", newline="\n")
        (pid_dir / "smaps_rollup").symlink_to(target)
        with self.assertRaises(MeasurementError):
            read_memory(4306, self.proc)

    # Invalid UTF-8 must surface as the module's fail-closed domain error,
    # never as a raw UnicodeDecodeError from bytes.decode().
    def test_read_memory_translates_invalid_utf8_to_measurement_error(self):
        pid_dir = self._pid_dir(4307)
        (pid_dir / "smaps_rollup").write_bytes(b"Rss: 10 kB\nPss: \xff\xfe kB\n")
        with self.assertRaises(MeasurementError):
            read_memory(4307, self.proc)


if __name__ == "__main__":
    unittest.main()
