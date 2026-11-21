"""Regression tests for informational process resource sampling."""
import unittest
from unittest.mock import patch

from tools.measure_qt import read_cpu_ticks, read_pss_kib


class ResourceSamplerTests(unittest.TestCase):
    def test_pss_is_read_in_kib(self):
        with patch("tools.measure_qt.Path.read_text", return_value="Rss: 100 kB\nPss: 42 kB\n"):
            self.assertEqual(read_pss_kib(1234), 42)

    def test_missing_pss_fails(self):
        with patch("tools.measure_qt.Path.read_text", return_value="Rss: 100 kB\n"):
            with self.assertRaisesRegex(ValueError, "Pss field missing"):
                read_pss_kib(1234)

    def test_cpu_stat_handles_spaces_in_process_name(self):
        fields = ["S"] + ["0"] * 40
        fields[11] = "120"
        fields[12] = "35"
        text = "1234 (canopy classic preview) " + " ".join(fields)
        with patch("tools.measure_qt.Path.read_text", return_value=text):
            self.assertEqual(read_cpu_ticks(1234), 155)

    def test_missing_stat_closing_parenthesis_fails(self):
        with patch("tools.measure_qt.Path.read_text", return_value="bad stat"):
            with self.assertRaisesRegex(ValueError, "Malformed"):
                read_cpu_ticks(1234)


if __name__ == "__main__":
    unittest.main()
