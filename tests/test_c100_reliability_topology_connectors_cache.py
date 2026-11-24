"""RED/GREEN identity regression: cached Topology.connectors frozenset."""
from dataclasses import FrozenInstanceError
import unittest

from canopy_features.reliability import screen_topology_change as t


def _topology():
    return t.Topology([
        t.Monitor("eDP-1", 1920, 1080, True),
        t.Monitor("HDMI-1", 2560, 1440, False),
    ])


class ConnectorsCacheTests(unittest.TestCase):
    def test_repeated_reads_return_same_object(self):
        topo = _topology()
        first = topo.connectors
        self.assertIsInstance(first, frozenset)
        self.assertTrue(first)
        self.assertIs(first, topo.connectors)

    def test_content_unchanged(self):
        topo = _topology()
        self.assertEqual(topo.connectors, frozenset({"eDP-1", "HDMI-1"}))

    def test_distinct_instances_do_not_share(self):
        self.assertIsNot(_topology().connectors, _topology().connectors)

    def test_topology_stays_frozen(self):
        topo = _topology()
        before = topo.connectors
        with self.assertRaises(FrozenInstanceError):
            topo.monitors = ()
        self.assertIs(topo.connectors, before)

    def test_empty_topology_returns_empty_frozenset(self):
        self.assertEqual(t.Topology().connectors, frozenset())


if __name__ == "__main__":
    unittest.main()
