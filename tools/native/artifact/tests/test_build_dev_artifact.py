"""Pure and pinned-source tests for the native dev-artifact builder.

Run with: PYTHONPATH=<worktree> python -m unittest discover -s tools/native/artifact/tests -v
No desktop, VM, network or repository mutation is performed.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.native.artifact import build_dev_artifact as bda
import baseline_common as bc  # importable after bda adds the native tools dir to sys.path

WORKTREE = Path(bda.__file__).resolve().parents[3]


class DevArtifactTests(unittest.TestCase):
    def test_pins_are_well_formed(self):
        self.assertTrue(bc.is_hex40(bda.SOURCE_COMMIT))
        self.assertTrue(bc.is_hex40(bda.BASELINE_COMMIT))
        for value in (bda.BINARY_SHA256, "4950fd793d067aa722a64ea8b09f0c1c65a55263b7f96c8fd418bf579e9f4a32"):
            self.assertEqual(bc.canonical_sha256(value), value)
        self.assertIn("NO_RELEASE", bda.SCOPE)
        self.assertIn("NO_MERGE", bda.SCOPE)

    def test_canonical_json_is_byte_stable_and_sorted(self):
        one = bda.canonical_json({"b": 1, "a": {"z": 2, "y": 3}})
        two = bda.canonical_json({"a": {"y": 3, "z": 2}, "b": 1})
        self.assertEqual(one, two)
        self.assertTrue(one.endswith(b"\n"))
        self.assertNotIn(b"\r", one)

    def test_doc_include_selector_is_fail_closed(self):
        self.assertTrue(bda.DOC_INCLUDE.match("docs/NATIVE_DEV_ARTIFACT.md"))
        self.assertTrue(bda.DOC_INCLUDE.match("docs/NATIVE_ROLLBACK.md"))
        self.assertFalse(bda.DOC_INCLUDE.match("docs/NOT_NATIVE_NOTES.md"))
        self.assertTrue("tools/native/build_baseline.py".startswith(bda.SOURCE_PREFIXES))

    def test_pinned_binary_and_manifest_agree_at_exact_commit(self):
        commit, tree = bda.resolve_commit(WORKTREE, bda.SOURCE_COMMIT)
        self.assertEqual(commit, bda.SOURCE_COMMIT)
        self.assertEqual(tree, "1b962fd2ab9f319409de895765d7b5c5f3261294")
        entries = bda.list_tree(WORKTREE, commit)
        paths = {item["path"]: item["oid"] for item in entries}
        self.assertIn(bda.BINARY_REL, paths)
        self.assertIn(bda.MANIFEST_REL, paths)
        oids = [paths[bda.BINARY_REL], paths[bda.MANIFEST_REL]]
        blobs = bda.hash_blobs(WORKTREE, oids, frozenset(oids))
        binary = blobs[paths[bda.BINARY_REL]][1]
        manifest = blobs[paths[bda.MANIFEST_REL]][1]
        self.assertEqual(len(binary), bda.BINARY_BYTES)
        self.assertEqual(bc.sha256_bytes(binary), bda.BINARY_SHA256)
        digest, claimed = bda.verify_binary(binary, manifest)
        self.assertEqual(digest, claimed)

    def test_verify_binary_rejects_tampered_bytes(self):
        entries = bda.list_tree(WORKTREE, bda.SOURCE_COMMIT)
        paths = {item["path"]: item["oid"] for item in entries}
        manifest_oid = paths[bda.MANIFEST_REL]
        manifest = bda.hash_blobs(WORKTREE, [manifest_oid], frozenset({manifest_oid}))[manifest_oid][1]
        with self.assertRaises(bda.ArtifactError):
            bda.verify_binary(b"tampered", manifest)
        with self.assertRaises(bda.ArtifactError):
            bda.verify_binary(b"\0" * bda.BINARY_BYTES, manifest)

    def test_stage_is_deterministic_and_inner_sums_exclude_self(self):
        source_id = {"schema": bda.SCHEMA_SOURCE_ID, "commit": bda.SOURCE_COMMIT,
                     "tree": "1b962fd2ab9f319409de895765d7b5c5f3261294",
                     "file_count": 1, "files": {"a.txt": "a" * 64}, "note": "test"}
        manifest = {"binary": {"sha256": "4950fd793d067aa722a64ea8b09f0c1c65a55263b7f96c8fd418bf579e9f4a32"}}
        doc = b"NO RELEASE\n# test document\n"
        selected = {"prototype/classic/a.txt": b"alpha\n"}
        archive_shas = []
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("one", "two"):
                root = Path(tmp) / name / bda.STAGE_NAME
                bda.stage_bundle(root, doc, source_id, selected, list(selected), b"binary", manifest)
                sums = bc.parse_sha256sums((root / "SHA256SUMS").read_text(encoding="utf-8"))
                self.assertNotIn("SHA256SUMS", sums)
                self.assertEqual(sorted(sums), ["ARTIFACT_ID.json", "README.md",
                                                "SOURCE_ID.json", bda.BINARY_STAGE_REL,
                                                "source/prototype/classic/a.txt"])
                identity = json.loads((root / "ARTIFACT_ID.json").read_text(encoding="utf-8"))
                self.assertTrue(identity["scope"].startswith("DEVELOPMENT_ARTIFACT_ONLY"))
                self.assertEqual(identity["verdict"], "PASS")
                archive_shas.append(bc.write_deterministic_tarball(
                    root, Path(tmp) / (name + ".tar.gz")))
        self.assertEqual(archive_shas[0], archive_shas[1])

    def test_delivery_doc_contains_required_boundaries(self):
        text = (WORKTREE / bda.DOC_REL).read_text(encoding="utf-8")
        for token in ("NO RELEASE", "NO_RELEASE", "NO_MERGE", "NO_APPROVAL",
                      "## Install", "## Uninstall", "## Rollback to known-good",
                      "## Smoke checklist", bda.SOURCE_COMMIT, bda.BINARY_SHA256):
            self.assertIn(token, text, token)

    def test_verify_only_accepts_built_artifact(self):
        out = bda.WORKTREE_DEFAULT / "scratch" / "native_dev_artifact"
        sums_path = out / "SHA256SUMS.txt"
        if not sums_path.is_file():
            self.skipTest("artifact not built yet")
        manifest = bc.parse_sha256sums(sums_path.read_text(encoding="utf-8"))
        with self.assertRaises(bda.ArtifactError):
            bda.verify_only(out, "0" * 64)
        self.assertEqual(len(manifest), 1)
        result = bda.verify_only(out, manifest[bda.ARCHIVE_NAME])
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["sha256"], manifest[bda.ARCHIVE_NAME])
        self.assertEqual(result["embedded_binary_sha256"], bda.BINARY_SHA256)


if __name__ == "__main__":
    unittest.main()
