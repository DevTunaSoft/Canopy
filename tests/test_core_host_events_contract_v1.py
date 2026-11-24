"""Regression tests: protocol v1 topic allowlist matches HOST_EVENT_CONTRACT.md.

The contract (docs/HOST_EVENT_CONTRACT.md, live integration tip) states that
protocol version 1 accepts exactly three event topics. capabilities.report
cannot be added to TOPICS until the contract is updated by its owner.
"""
import unittest

import canopy_core.host_events as events
from canopy_core.host_events import HostEventError, HostEvents
from canopy_core.shell_host import ShellHost

DOCUMENTED_V1_TOPICS = frozenset({
    "app.catalog.changed", "window.state.changed", "session.state.changed",
})


class V1ContractTests(unittest.TestCase):
    def test_protocol_version_and_topic_set_match_contract(self):
        self.assertEqual(events.PROTOCOL_VERSION, 1)
        self.assertEqual(events.TOPICS, DOCUMENTED_V1_TOPICS)

    def test_capabilities_report_topic_is_rejected(self):
        with self.assertRaises(HostEventError):
            HostEvents({"capabilities.report": [lambda event: None]})
        bus = HostEvents({"app.catalog.changed": [lambda event: None]})
        with self.assertRaises(HostEventError):
            bus.emit("capabilities.report", {"status": "CAPABILITY_REPORT"})
        self.assertEqual(bus._sequence, 0)

    def test_no_undocumented_publish_api(self):
        self.assertFalse(hasattr(events, "CAPABILITIES_TOPIC"))
        self.assertFalse(hasattr(ShellHost, "publish_capability_report"))


if __name__ == "__main__":
    unittest.main()
