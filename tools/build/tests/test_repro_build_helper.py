#!/usr/bin/env python3
"""Targeted regression tests for the Classic UCRT64 reproducibility helper.

All fixtures are synthetic scratch trees: no network, no repository binaries,
no credentials and no edit to tracked source. Run with:

    python -m unittest tools.build.tests.test_repro_build_helper -v
    python -m unittest tests.test_repro_build_helper -v
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.build import repro_build_helper as helper  # noqa: E402


class EolContractTests(unittest.TestCase):
    def test_normalize_eol_converts_crlf_and_lone_cr_for_text(self):
        self.assertEqual(helper.normalize_eol(b"a\r\nb\rc\n"),
                         (b"a\nb\nc\n", True))

    def test_normalize_eol_is_noop_for_lf_text(self):
        self.assertEqual(helper.normalize_eol(b"a\nb\n"),
                         (b"a\nb\n", False))

    def test_normalize_eol_leaves_binary_bytes_untouched(self):
        payload = b"\x89PNG\r\n\x1a\n\x00\r\n"
        self.assertEqual(helper.normalize_eol(payload), (payload, False))

    def test_normalize_eol_rejects_non_bytes(self):
        with self.assertRaises(TypeError):
            helper.normalize_eol("a\r\nb")

    def test_only_compiled_source_paths_are_eol_normalized(self):
        for path in ("src/main.cpp", "src/widget.qml", "CMakeLists.txt",
                     "prototype/classic/CMakeLists.txt", "x/App.qrc"):
            with self.subTest(path=path):
                self.assertTrue(helper.is_compiled_source(path))
        for path in ("docs/evidence/sha256.txt", "assets/icon.png",
                     "docs/evidence/evidence.md", "tools/build/.gitattributes"):
            with self.subTest(path=path):
                self.assertFalse(helper.is_compiled_source(path))
        self.assertEqual(helper.staged_bytes(b"a\r\nb", "src/main.cpp"),
                         (b"a\nb", True))
        self.assertEqual(helper.staged_bytes(b"a\r\nb", "docs/sha256.txt"),
                         (b"a\r\nb", False))

    def test_autocrlf_classification_is_case_insensitive_and_fails_closed(self):
        self.assertEqual(helper.canonical_autocrlf(" TRUE "), "true")
        self.assertEqual(helper.canonical_autocrlf("Input"), "input")
        self.assertEqual(helper.canonical_autocrlf(None), "false")
        self.assertIsNone(helper.canonical_autocrlf("maybe"))
        self.assertIsNone(helper.canonical_autocrlf(1))

    def test_only_false_and_input_autocrlf_are_safe(self):
        self.assertTrue(helper.autocrlf_is_safe("false"))
        self.assertTrue(helper.autocrlf_is_safe("input"))
        self.assertFalse(helper.autocrlf_is_safe("true"))
        self.assertFalse(helper.autocrlf_is_safe("maybe"))
        self.assertFalse(helper.autocrlf_is_safe(True))


class TimestampInputTests(unittest.TestCase):
    def test_stable_env_pins_epoch_without_mutating_caller(self):
        base = {"PATH": "/bin", "SOURCE_DATE_EPOCH": "123", "TZ": "local"}
        env = helper.stable_env(base, epoch=7)
        self.assertEqual(env["SOURCE_DATE_EPOCH"], "7")
        self.assertEqual(env["TZ"], "UTC")
        self.assertEqual(env["LANG"], "C")
        self.assertEqual(env["PATH"], "/bin")
        self.assertEqual(base["SOURCE_DATE_EPOCH"], "123")
        self.assertEqual(base["TZ"], "local")

    def test_stable_env_rejects_invalid_epochs(self):
        for bad in (-1, True, 1.5, "0", None):
            with self.subTest(epoch=bad), self.assertRaises(ValueError):
                helper.stable_env({}, epoch=bad)

    def test_normalize_mtimes_pins_every_regular_file(self):
        root = Path(tempfile.mkdtemp(prefix="ri011-mtimes-"))
        first = root / "a.txt"
        second = root / "nested" / "b.cpp"
        second.parent.mkdir()
        first.write_bytes(b"a\n")
        second.write_bytes(b"b\n")
        os.utime(first, (123, 123))
        os.utime(second, (456, 456))
        self.assertEqual(helper.normalize_mtimes(root, epoch=0), 2)
        self.assertEqual(os.stat(first).st_mtime_ns, 0)
        self.assertEqual(os.stat(second).st_mtime_ns, 0)

    def test_generated_qmldir_mtimes_are_pinned_alone(self):
        root = Path(tempfile.mkdtemp(prefix="ri011-qmldir-"))
        build = root / "build"
        (build / "nested").mkdir(parents=True)
        qmldir = build / "nested" / "qmldir"
        other = build / "other.txt"
        qmldir.write_bytes(b"module X\n")
        other.write_bytes(b"keep\n")
        os.utime(qmldir, (999, 999))
        os.utime(other, (888, 888))
        self.assertEqual(helper.normalize_generated_mtimes(build, epoch=0), 1)
        self.assertEqual(os.stat(qmldir).st_mtime_ns, 0)
        self.assertEqual(os.stat(other).st_mtime_ns, 888 * 1_000_000_000)


class StageContractTests(unittest.TestCase):
    """Real git fixtures: blob bytes, not worktree EOL, drive the stage."""

    @staticmethod
    def git(repo, *args):
        return subprocess.run(["git", "-C", str(repo), *args],
                              capture_output=True, timeout=120)

    def make_repo(self):
        root = Path(tempfile.mkdtemp(prefix="ri011-repo-"))
        repo = root / "source"
        repo.mkdir()
        self.git(repo, "init", "-q")
        self.git(repo, "config", "user.email", "ri011@example.invalid")
        self.git(repo, "config", "user.name", "RI011")
        self.git(repo, "config", "core.autocrlf", "false")
        (repo / ".gitattributes").write_bytes(b"*.qml -text\n")
        (repo / "src").mkdir()
        (repo / "src" / "main.cpp").write_bytes(b"int main() { return 0; }\n")
        (repo / "src" / "widget.qml").write_bytes(b"Item {\r\n}\r\n")
        (repo / "assets").mkdir()
        (repo / "assets" / "blob.bin").write_bytes(b"\x89PNG\r\n\x1a\n\x00\r\n")
        (repo / "docs").mkdir()
        (repo / "docs" / "sha256.txt").write_bytes(b"abc  docs/evidence/x.png\r\n")
        self.assertEqual(self.git(repo, "add", "-A").returncode, 0)
        self.assertEqual(self.git(repo, "commit", "-qm", "fixture").returncode, 0)
        sha = self.git(repo, "rev-parse", "HEAD").stdout.decode().strip()
        # A checkout that rewrites LF to CRLF is exactly the RI-003 condition.
        self.git(repo, "config", "core.autocrlf", "true")
        (repo / "src" / "main.cpp").unlink()
        self.assertEqual(self.git(repo, "checkout", "--", "src/main.cpp").returncode, 0)
        self.assertIn(b"\r\n", (repo / "src" / "main.cpp").read_bytes())
        return root, repo, sha

    def run_helper(self, *args):
        script = Path(helper.__file__).resolve()
        return subprocess.run([sys.executable, str(script), *map(str, args)],
                              capture_output=True, text=True, timeout=180)

    def test_prepare_stages_blob_bytes_eol_and_stable_mtimes(self):
        root, repo, sha = self.make_repo()
        out = root / "stage"
        result = self.run_helper("prepare", "--source", repo,
                                 "--source-sha", sha, "--out", out)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("HELPER_PASS", result.stdout)
        self.assertIn("AUTOCRLF observed=true canonical=true safe=False", result.stdout)
        self.assertIn("STAGE files=5 byte_identical=4 eol_normalized=1", result.stdout)
        self.assertIn("MTIME normalized=6 epoch=0", result.stdout)  # 5 inputs + report
        self.assertIn("ENV SOURCE_DATE_EPOCH=0 TZ=UTC", result.stdout)

        report = json.loads((out / "repro_stage_report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["source_sha"], sha)
        self.assertTrue(report["source_worktree_tracked_clean"])
        files = {entry["path"]: entry for entry in report["files"]}
        self.assertTrue(files["src/main.cpp"]["byte_identical"])
        self.assertFalse(files["src/main.cpp"]["eol_normalized"])
        self.assertTrue(files["src/widget.qml"]["eol_normalized"])
        self.assertFalse(files["src/widget.qml"]["byte_identical"])
        self.assertTrue(files["assets/blob.bin"]["byte_identical"])
        self.assertTrue(files["docs/sha256.txt"]["byte_identical"])
        self.assertFalse(files["docs/sha256.txt"]["eol_normalized"])
        self.assertEqual(files["src/widget.qml"]["stage_sha256"],
                         hashlib.sha256(b"Item {\n}\n").hexdigest())
        self.assertEqual((out / "src" / "main.cpp").read_bytes(),
                         b"int main() { return 0; }\n")
        self.assertEqual((out / "assets" / "blob.bin").read_bytes(),
                         b"\x89PNG\r\n\x1a\n\x00\r\n")
        self.assertEqual((out / "docs" / "sha256.txt").read_bytes(),
                         b"abc  docs/evidence/x.png\r\n")
        for path in out.rglob("*"):
            if path.is_file():
                self.assertEqual(path.stat().st_mtime_ns, 0, str(path))
        # The worktree itself is never rewritten: CRLF stays, git stays clean.
        self.assertIn(b"\r\n", (repo / "src" / "main.cpp").read_bytes())
        self.assertEqual(self.git(repo, "status", "--porcelain").stdout, b"")

    def test_verify_detects_staged_byte_tampering(self):
        root, repo, sha = self.make_repo()
        out = root / "stage"
        prepared = self.run_helper("prepare", "--source", repo,
                                   "--source-sha", sha, "--out", out)
        self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
        good = self.run_helper("verify", "--source", repo, "--stage", out,
                               "--source-sha", sha, "--epoch", 0)
        self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
        self.assertIn("VERIFY files=5 pass=5", good.stdout)
        (out / "src" / "main.cpp").write_bytes(b"tampered\n")
        bad = self.run_helper("verify", "--source", repo, "--stage", out,
                              "--source-sha", sha, "--epoch", 0)
        self.assertEqual(bad.returncode, 1, bad.stdout + bad.stderr)
        self.assertIn("VERIFY_FAIL: src/main.cpp", bad.stdout)

    def test_prepare_fails_closed_on_wrong_pin_dirty_tree_and_scratch_escape(self):
        root, repo, sha = self.make_repo()
        wrong = self.run_helper("prepare", "--source", repo,
                                "--source-sha", "1" * 40, "--out", root / "bad-pin")
        self.assertEqual(wrong.returncode, 1, wrong.stdout + wrong.stderr)
        self.assertIn("HELPER_FAIL: source HEAD", wrong.stdout)
        self.assertFalse((root / "bad-pin").exists())

        (repo / "src" / "main.cpp").write_bytes(b"int main() { return 1; }\r\n")
        dirty = self.run_helper("prepare", "--source", repo,
                                "--source-sha", sha, "--out", root / "bad-dirty")
        self.assertEqual(dirty.returncode, 1, dirty.stdout + dirty.stderr)
        self.assertIn("HELPER_FAIL: source worktree dirty", dirty.stdout)
        self.assertFalse((root / "bad-dirty").exists())
        self.assertEqual(self.git(repo, "checkout", "--", "src/main.cpp").returncode, 0)

        inside = self.run_helper("prepare", "--source", repo,
                                 "--source-sha", sha, "--out", repo / "inside")
        self.assertEqual(inside.returncode, 1, inside.stdout + inside.stderr)
        self.assertIn("HELPER_FAIL: out must be scratch", inside.stdout)
        self.assertFalse((repo / "inside").exists())


if __name__ == "__main__":
    unittest.main()
