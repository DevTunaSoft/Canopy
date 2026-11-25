"""Offline tests for the cold/warm startup-run summarizer.

Runs here are synthetic recorded observations. They do not prove a real Linux
Mint guest, a compiled Qt launch, or any release claim. Tests run on the
Windows host with no process, /proc, network or privileged access.
"""
import ast
import inspect
import unittest

from canopy_features.performance import cold_warm_benchmark as bm

SOURCE = "a" * 40
BINARY = "b" * 64
OTHER_BINARY = "c" * 64
METHOD = "qelapsedtimer-to-window-ready"


def environment(**overrides):
    env = {
        "distro": "linuxmint",
        "kernel": "6.5.0-generic",
        "session_type": "x11",
        "qt_version": "6.4.2",
        "backend": "software",
        "cpu": "x86_64-4c",
        "gpu": "llvmpipe",
        "driver": "mesa-23.2",
    }
    env.update(overrides)
    return env


def run(kind, startup_ms, *, binary=BINARY, env=None, method=METHOD):
    return {
        "schema": 1,
        "kind": kind,
        "startup_ms": startup_ms,
        "environment": env if env is not None else environment(),
        "source_sha": SOURCE,
        "binary_sha256": binary,
        "measurement_method": method,
    }


class ColdWarmBenchmarkTests(unittest.TestCase):
    def test_paired_runs_summarize_with_environment_metadata(self):
        result = bm.summarize([
            run("cold", 1200.0),
            run("cold", 1000.0),
            run("warm", 400.0),
            run("warm", 600.0),
        ])
        self.assertEqual(result["run_count"], 4)
        self.assertEqual(result["environment_count"], 1)
        self.assertEqual(result["paired_environment_count"], 1)
        self.assertEqual(result["unpaired_environment_count"], 0)
        self.assertEqual(result["unpaired_run_count"], 0)
        entry = result["environments"][0]
        self.assertTrue(entry["paired"])
        self.assertIsNone(entry["unpaired_reason"])
        self.assertEqual(entry["cold"]["count"], 2)
        self.assertEqual(entry["cold"]["min_ms"], 1000.0)
        self.assertEqual(entry["cold"]["median_ms"], 1100.0)
        self.assertEqual(entry["warm"]["median_ms"], 500.0)
        self.assertEqual(entry["comparison"]["warm_faster"], True)
        self.assertEqual(entry["comparison"]["warm_minus_cold_ms"], -600.0)
        self.assertEqual(entry["environment"]["distro"], "linuxmint")
        self.assertEqual(entry["environment"]["session_type"], "x11")
        self.assertEqual(entry["environment"]["backend"], "software")
        self.assertEqual(entry["binary_sha256"], BINARY)

    def test_unpaired_cold_only_is_reported_not_compared(self):
        result = bm.summarize([run("cold", 900), run("cold", 1100)])
        entry = result["environments"][0]
        self.assertFalse(entry["paired"])
        self.assertEqual(entry["unpaired_reason"], "no_warm_run")
        self.assertIsNone(entry["warm"])
        self.assertIsNone(entry["comparison"])
        self.assertEqual(entry["cold"]["count"], 2)
        self.assertEqual(result["unpaired_run_count"], 2)
        self.assertEqual(result["paired_environment_count"], 0)

    def test_unpaired_warm_only_is_reported_not_compared(self):
        result = bm.summarize([run("warm", 300)])
        entry = result["environments"][0]
        self.assertFalse(entry["paired"])
        self.assertEqual(entry["unpaired_reason"], "no_cold_run")
        self.assertIsNone(entry["cold"])
        self.assertIsNone(entry["comparison"])
        self.assertEqual(result["unpaired_run_count"], 1)

    def test_different_builds_are_not_falsely_paired(self):
        result = bm.summarize([
            run("cold", 1000, binary=BINARY),
            run("warm", 200, binary=OTHER_BINARY),
        ])
        self.assertEqual(result["environment_count"], 2)
        self.assertEqual(result["paired_environment_count"], 0)
        self.assertEqual(result["unpaired_run_count"], 2)
        self.assertTrue(all(not e["paired"] for e in result["environments"]))

    def test_environments_group_and_sort_deterministically(self):
        wayland = environment(session_type="wayland", backend="opengl")
        result = bm.summarize([
            run("warm", 300, env=wayland),
            run("cold", 900, env=wayland),
            run("cold", 1000),
        ])
        self.assertEqual(result["environment_count"], 2)
        self.assertEqual(result["paired_environment_count"], 1)
        self.assertEqual(result["unpaired_environment_count"], 1)
        self.assertEqual(
            [e["environment"]["session_type"] for e in result["environments"]],
            ["wayland", "x11"],
        )

    def test_zero_negative_nonfinite_and_huge_startup_rejected(self):
        for value in (0, -1, float("nan"), float("inf"), -float("inf"),
                      True, bm.MAX_STARTUP_MS + 1):
            with self.subTest(value=value):
                with self.assertRaises(bm.RunError):
                    bm.summarize([run("cold", value)])

    def test_bogus_self_reported_claims_rejected(self):
        for field, value in (
            ("claim", {"startup_ms": 1}),
            ("release_approved", True),
            ("linux_mint_proven", True),
            ("meets_budget", True),
            ("warm_improvement_percent", 500),
        ):
            with self.subTest(field=field):
                record = run("cold", 1000)
                record[field] = value
                with self.assertRaisesRegex(bm.RunError, "claim"):
                    bm.summarize([record])

    def test_recorded_mint_metadata_never_becomes_guest_proof(self):
        result = bm.summarize([
            run("cold", 1000, env=environment(distro="linuxmint")),
            run("warm", 300, env=environment(distro="linuxmint")),
        ])
        self.assertFalse(result["release_approved"])
        self.assertFalse(result["linux_mint_guest_proven"])
        self.assertFalse(result["compiled_qt_proven"])
        self.assertFalse(result["visual_approval"])

    def test_fake_measurement_method_rejected(self):
        record = run("cold", 1000, method="fake-simulator")
        with self.assertRaisesRegex(bm.RunError, "measurement method"):
            bm.summarize([record])

    def test_external_sha_pins_enforced(self):
        self.assertEqual(bm.summarize([run("cold", 1000)],
                                      expected_source_sha=SOURCE,
                                      expected_binary_sha256=BINARY)["run_count"], 1)
        with self.assertRaisesRegex(bm.RunError, "external pin"):
            bm.summarize([run("cold", 1000)], expected_source_sha="d" * 40)
        with self.assertRaisesRegex(bm.RunError, "external pin"):
            bm.summarize([run("cold", 1000)], expected_binary_sha256=OTHER_BINARY)

    def test_run_count_is_bounded(self):
        many = [run("cold", 1000) for _ in range(bm.MAX_RUNS + 1)]
        with self.assertRaisesRegex(bm.RunError, "more than"):
            bm.summarize(many)

    def test_invalid_environment_metadata_rejected(self):
        missing = environment()
        del missing["driver"]
        for env in (missing, {k: 5 for k in environment()},
                    environment(distro="x" * 500)):
            with self.subTest(env=env):
                with self.assertRaises(bm.RunError):
                    bm.summarize([run("cold", 1000, env=env)])

    def test_module_has_no_process_poll_or_network_capability(self):
        tree = ast.parse(inspect.getsource(bm))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertFalse(
            imported & {"os", "sys", "subprocess", "socket", "time",
                        "requests", "urllib", "pathlib", "threading"},
        )


if __name__ == "__main__":
    unittest.main()
