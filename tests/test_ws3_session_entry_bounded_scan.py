"""RED regression: session-entry directory scan must not buffer unlimited entries."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from canopy_features.installer import session_entry_validation as sev


class BoundedSessionEntryScanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def _counted_iterdir(self):
        original = Path.iterdir
        state = {"count": 0}

        def counted(self_path):
            for item in original(self_path):
                state["count"] += 1
                yield item

        return counted, state

    def test_oversized_scan_stops_before_buffering_all_candidates(self):
        for i in range(sev.MAX_ENTRIES + 8):
            (self.root / f"entry-{i:03d}.desktop").write_text("ignored")
        counted, state = self._counted_iterdir()
        with patch.object(Path, "iterdir", autospec=True, side_effect=counted):
            with self.assertRaisesRegex(sev.SessionEntryError, "exceeds 32 files"):
                sev.scan_session_entries(self.root)
        self.assertLessEqual(
            state["count"], sev.MAX_ENTRIES + 1,
            "scan consumed %d directory entries; bound is %d"
            % (state["count"], sev.MAX_ENTRIES + 1),
        )

    def test_exact_cap_scans_all_entries_and_sorts_deterministically(self):
        for i in reversed(range(sev.MAX_ENTRIES)):
            (self.root / f"entry-{i:03d}.desktop").write_text("ignored")
        counted, state = self._counted_iterdir()
        with patch.object(Path, "iterdir", autospec=True, side_effect=counted):
            result = sev.scan_session_entries(self.root)
        self.assertEqual(state["count"], sev.MAX_ENTRIES)
        self.assertEqual(result.checked_files, sev.MAX_ENTRIES)
        self.assertEqual(len(result.problems), sev.MAX_ENTRIES)
        self.assertEqual(
            [p.location for p in result.problems],
            sorted(p.location for p in result.problems),
        )

    def test_non_desktop_files_do_not_count_toward_cap(self):
        for i in range(sev.MAX_ENTRIES):
            (self.root / f"entry-{i:03d}.desktop").write_text("ignored")
        for i in range(12):
            (self.root / f"unrelated-{i:03d}.txt").write_text("ignored")
        counted, state = self._counted_iterdir()
        with patch.object(Path, "iterdir", autospec=True, side_effect=counted):
            result = sev.scan_session_entries(self.root)
        self.assertEqual(state["count"], sev.MAX_ENTRIES + 12)
        self.assertEqual(result.checked_files, sev.MAX_ENTRIES)


if __name__ == "__main__":
    unittest.main()
