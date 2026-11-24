"""Contract tests: protocol v2 topic set and v1-topic backward compatibility.

docs/HOST_EVENT_CONTRACT.md defines v2 as the four-topic successor to v1;
the three original topics remain valid under v2 with unchanged scalar rules.
"""
import unittest

import canopy_core.host_events as events
from canopy_core.host_events import HostEventError, HostEvents

V1_TOPICS = frozenset({
    "app.catalog.changed", "window.state.changed", "session.state.changed",
})
V2_TOPICS = V1_TOPICS | {"capabilities.report"}


class V2ContractTests(unittest.TestCase):
    def test_protocol_version_and_topic_set(self):
        self.assertEqual(events.PROTOCOL_VERSION, 2)
        self.assertEqual(events.TOPICS, V2_TOPICS)
        self.assertEqual(events.CAPABILITIES_TOPIC, "capabilities.report")

    def test_v1_topics_remain_accepted_with_scalar_payload(self):
        for topic in sorted(V1_TOPICS):
            with self.subTest(topic=topic):
                seen = []
                callback = seen.append
                bus = HostEvents({topic: [callback]})
                bus.subscribe(topic, callback)
                result = bus.emit(topic, {"count": 1, "ready": True})
                self.assertEqual((result.delivered, result.callback_failures),
                                 (1, 0))
                self.assertEqual(seen[0].version, 2)
                self.assertEqual(seen[0].topic, topic)
                self.assertEqual(dict(seen[0].payload),
                                 {"count": 1, "ready": True})
                bus.close()

    def test_capabilities_topic_accepted(self):
        seen = []
        callback = seen.append
        bus = HostEvents({"capabilities.report": [callback]})
        bus.subscribe("capabilities.report", callback)
        result = bus.emit("capabilities.report", {"status": "CAPABILITY_REPORT"})
        self.assertEqual(result.delivered, 1)
        self.assertEqual(seen[0].payload["status"], "CAPABILITY_REPORT")
        bus.close()

    def test_old_version_and_fifth_topic_rejected(self):
        with self.assertRaises(HostEventError):
            HostEvents({}, version=1)
        bus = HostEvents({})
        with self.assertRaises(HostEventError):
            bus.emit("capabilities.report.echo", {"status": "X"})
        self.assertEqual(bus._sequence, 0)


if __name__ == "__main__":
    unittest.main()
