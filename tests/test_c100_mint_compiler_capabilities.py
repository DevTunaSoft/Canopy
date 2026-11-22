"""Offline unit tests for compiler-probe normalization.

These tests use evidence strings only. They do not run cmake, ninja, qmake,
pkg-config, compile Qt, use a Linux Mint guest or claim visual acceptance.
"""
import json
import unittest

from canopy_features.mint import compiler_capabilities as caps


def probe(path, output, exit_code=0, source=None):
    record = {"path": path, "exit_code": exit_code, "version_output": output}
    if source is not None:
        record["source"] = source
    return record


class CompilerCapabilitiesTests(unittest.TestCase):
    def setUp(self):
        # Linux-Mint-style paths and real tool banner shapes.
        self.mint = {
            "cmake": probe("/usr/bin/cmake", "cmake version 3.25.1\n\n"),
            "ninja": probe("/usr/bin/ninja", "1.11.1\n"),
            "qt6": probe(
                "/usr/bin/qmake",
                "QMake version 3.1\nUsing Qt version 6.4.2 in /usr/lib/x86_64-linux-gnu\n",
            ),
        }

    def report(self, **overrides):
        evidence = dict(self.mint)
        for tool, value in overrides.items():
            if value is None:
                evidence.pop(tool, None)
            else:
                evidence[tool] = value
        return caps.normalize_capabilities(evidence)

    def test_all_toolchains_present_normalize_versions(self):
        report = self.report()
        self.assertEqual(report["status"], "READY")
        self.assertEqual(report["blockers"], [])
        self.assertEqual(
            {name: row["version"] for name, row in report["tools"].items()},
            {"cmake": "3.25.1", "ninja": "1.11.1", "qt6": "6.4.2"},
        )
        self.assertTrue(all(row["state"] == "present" for row in report["tools"].values()))

    def test_windows_host_paths_normalize_without_leaking_directories(self):
        report = self.report(
            cmake=probe(r"C:\Users\secret\tools\cmake.exe", "cmake version 3.21\r\n"),
            ninja=probe(r"C:\tools\ninja.EXE", "1.12.1\r\n"),
            qt6=probe(
                r"C:\Qt\6.4.2\bin\qmake.exe",
                "QMake version 3.1\r\nUsing Qt version 6.4.2\r\n",
            ),
        )
        self.assertEqual(report["status"], "READY")
        serialized = json.dumps(report)
        self.assertNotIn("secret", serialized)
        self.assertNotIn("C:", serialized)
        self.assertEqual(report["tools"]["cmake"]["binary_name"], "cmake.exe")
        self.assertEqual(report["tools"]["ninja"]["binary_name"], "ninja.exe")

    def test_missing_each_toolchain_blocks(self):
        for tool in caps.TOOL_RULES:
            with self.subTest(tool=tool):
                report = self.report(**{tool: None})
                self.assertEqual(report["status"], "BLOCKED")
                self.assertEqual(report["tools"][tool]["state"], "missing")
                self.assertTrue(any(tool in item for item in report["blockers"]))

    def test_no_probe_evidence_reports_all_missing(self):
        report = caps.normalize_capabilities({})
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(
            [row["state"] for row in report["tools"].values()],
            ["missing", "missing", "missing"],
        )
        self.assertEqual(len(report["blockers"]), 3)

    def test_misleading_name_claiming_another_tool_is_rejected(self):
        # A stub called cmake that actually answers like ninja.
        report = self.report(
            cmake=probe("/usr/bin/cmake", "1.11.1\n"),
        )
        self.assertEqual(report["status"], "BLOCKED")
        cmake = report["tools"]["cmake"]
        self.assertEqual(cmake["state"], "misleading")
        self.assertIsNone(cmake["version"])
        self.assertIn("does not identify cmake", cmake["reason"])

    def test_misleading_path_basename_is_rejected(self):
        # shutil.which hit alone would pass this; normalize must not.
        for path in (r"C:\tools\fake-cmake.exe", "/usr/local/bin/cmake-stub"):
            with self.subTest(path=path):
                report = self.report(cmake=probe(path, "cmake version 3.25.1\n"))
                self.assertEqual(report["tools"]["cmake"]["state"], "misleading")
                self.assertEqual(report["status"], "BLOCKED")

    def test_misleading_qmake_banner_from_another_tool_is_rejected(self):
        report = self.report(qt6=probe("/usr/bin/qmake", "cmake version 3.25.1\n"))
        self.assertEqual(report["tools"]["qt6"]["state"], "misleading")
        self.assertEqual(report["status"], "BLOCKED")

    def test_qmake_version_not_embedded_in_library_path(self):
        # Version must follow the banner, not come from /usr/lib/x86_64.
        evidence = probe("/usr/bin/qmake", "Using Qt version in /usr/lib/x86_64-linux-gnu\n")
        record = caps.normalize_probe("qt6", evidence)
        self.assertEqual(record["state"], "unusable")
        self.assertIsNone(record["version"])

    def test_qt_pkg_config_bare_version_is_normalized(self):
        evidence = probe(
            "/usr/bin/pkg-config", "6.4.2\n", source="pkg-config",
        )
        record = caps.normalize_probe("qt6", evidence)
        self.assertEqual(record["state"], "present")
        self.assertEqual(record["version"], "6.4.2")

    def test_pkg_config_non_version_output_is_rejected(self):
        for output in ("not a version", "6.4.2 extra", "", "6.4.2; echo pwned"):
            with self.subTest(output=output):
                record = caps.normalize_probe(
                    "qt6", probe("/usr/bin/pkg-config", output, source="pkg-config"),
                )
                self.assertEqual(record["state"], "unusable")
                self.assertIsNone(record["version"])

    def test_below_minimum_versions_are_not_ready(self):
        report = self.report(
            cmake=probe("/usr/bin/cmake", "cmake version 3.19.8\n"),
            qt6=probe("/usr/bin/qmake", "Using Qt version 5.15.2\n"),
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["tools"]["cmake"]["state"], "below_minimum")
        self.assertEqual(report["tools"]["qt6"]["state"], "below_minimum")
        self.assertEqual(report["tools"]["cmake"]["version"], "3.19.8")

    def test_exact_minimum_is_accepted(self):
        report = self.report(
            cmake=probe("/usr/bin/cmake", "cmake version 3.21\n"),
            qt6=probe("/usr/bin/qmake", "Using Qt version 6.4\n"),
        )
        self.assertEqual(report["status"], "READY")

    def test_nonzero_exit_code_is_never_present(self):
        for code in (1, 2, -1, True):
            with self.subTest(code=code):
                record = caps.normalize_probe(
                    "ninja", probe("/usr/bin/ninja", "1.11.1\n", exit_code=code),
                )
                self.assertEqual(record["state"], "unusable")

    def test_empty_malformed_and_oversized_output_is_bounded(self):
        cases = [
            "", "   ", None, 12345, "cmake version 3.25.1\n" + "x" * caps.MAX_OUTPUT_CHARS,
            "cmake version 3.25.1\0",
        ]
        for output in cases:
            with self.subTest(output=str(output)[:30]):
                record = caps.normalize_probe(
                    "cmake", probe("/usr/bin/cmake", output),
                )
                self.assertIn(record["state"], ("unusable", "misleading", "missing"))
                self.assertIsNone(record["version"])

    def test_unknown_source_and_malformed_evidence_are_rejected(self):
        self.assertEqual(
            caps.normalize_probe("qt6", probe("/usr/bin/qmake", "6.4.2", source="ninja"))["state"],
            "misleading",
        )
        self.assertEqual(caps.normalize_probe("cmake", None)["state"], "missing")
        self.assertEqual(caps.normalize_probe("cmake", "cmake version 3.25.1")["state"], "missing")

    def test_report_never_claims_build_runtime_mint_or_visual_acceptance(self):
        for report in (self.report(), caps.normalize_capabilities({})):
            self.assertTrue(report["probe_only"])
            self.assertEqual(report["qt_compiled_acceptance"], "NOT_RUN")
            self.assertEqual(report["mint_guest_acceptance"], "NOT_RUN")
            self.assertEqual(report["runtime_functional_test"], "NOT_RUN")
            self.assertEqual(report["visual_acceptance"], "NOT_RUN")

    def test_report_is_deterministic_and_ordered(self):
        first = self.report(cmake=probe("/usr/bin/cmake", "cmake version 3.19.8\n"))
        second = self.report(cmake=probe("/usr/bin/cmake", "cmake version 3.19.8\n"))
        self.assertEqual(first, second)
        self.assertEqual(list(first["tools"]), ["cmake", "ninja", "qt6"])
        self.assertEqual(len(first["blockers"]), len(set(first["blockers"])))

    def test_non_mapping_input_is_rejected(self):
        with self.assertRaises(TypeError):
            caps.normalize_capabilities(["cmake", "ninja"])


if __name__ == "__main__":
    unittest.main()
