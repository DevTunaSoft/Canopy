import unittest
from datetime import datetime
from canopy.classic_model import DEFAULT_DOCK, clock_label, visible_apps

class FakeApp:
    def __init__(self, id_, name, show=True):
        self.id_, self.name, self.show = id_, name, show
    def should_show(self): return self.show
    def get_id(self): return self.id_
    def get_name(self): return self.name

class ClassicTests(unittest.TestCase):
    def test_clock(self):
        self.assertEqual(clock_label(datetime(2026, 11, 17, 9, 7)), 'Tue 09:07')

    def test_filtered_sorted_deduped(self):
        apps = [FakeApp('z.desktop', 'zebra'), FakeApp('h.desktop', 'Hidden', False),
                FakeApp('a.desktop', 'Alpha'), FakeApp('a.desktop', 'Alpha')]
        self.assertEqual([app.get_id() for app in visible_apps(apps)], ['a.desktop', 'z.desktop'])

    def test_dock_ids_are_unique(self):
        self.assertEqual(len(DEFAULT_DOCK), len(set(item.desktop_id for item in DEFAULT_DOCK)))

if __name__ == '__main__': unittest.main()
