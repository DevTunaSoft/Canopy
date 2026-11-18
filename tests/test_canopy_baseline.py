"""Unit tests for the stdlib read-only Canopy Linux baseline helper."""
import tempfile
import unittest
from pathlib import Path
from tools.canopy_baseline import parse_meminfo, parse_stat, sample


class BaselineTests(unittest.TestCase):
    def test_meminfo(self):
        self.assertEqual(
            parse_meminfo('MemTotal: 4096 kB\nMemAvailable: 128 kB\n'),
            {'MemTotal': 4194304, 'MemAvailable': 131072}
        )

    def test_stat_with_parentheses_in_name(self):
        parts = ['S'] + ['0'] * 50
        parts[11], parts[12], parts[21] = '12', '13', '22'
        self.assertEqual(parse_stat('45 (strange) name) ' + ' '.join(parts)), (25, 22))

    def test_scope_excludes_unrelated_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for pid, name in [('101', 'plasmashell'), ('102', 'browser')]:
                proc = root / pid
                proc.mkdir()
                (proc / 'comm').write_text(name + '\n')
                parts = ['S'] + ['0'] * 50
                parts[21] = '2'
                (proc / 'stat').write_text(pid + ' (' + name + ') ' + ' '.join(parts))
                (proc / 'smaps_rollup').write_text('Pss: 42 kB\n')
            actual = sample(root)
            self.assertEqual(list(actual), ['101'])
            self.assertEqual(actual['101'][3], 42 * 1024)


if __name__ == '__main__':
    unittest.main()
