import unittest
from datetime import datetime
from canopy.applications import matches_app, visible_apps
from canopy.classic_model import DEFAULT_DOCK, clock_label, configured_dock_ids, dock_position
from canopy.preferences import Preferences

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

    def test_explicit_empty_pins_do_not_restore_defaults(self):
        self.assertEqual(configured_dock_ids(Preferences()),
                         [item.desktop_id for item in DEFAULT_DOCK])
        self.assertEqual(configured_dock_ids(Preferences(classic_pins=[])), [])

    def test_dock_uses_workarea_origin_and_actual_size(self):
        self.assertEqual(dock_position(-1280, 40, 1280, 740, 240, 52), (-760, 716))
        self.assertEqual(dock_position(50, 30, 100, 40, 120, 60), (50, 30))

    def test_search_matches_casefolded_terms_across_name_and_id(self):
        app = FakeApp('org.example.Reader.desktop', 'Straße Reader')

        for query in ('', '   ', 'STRASSE', 'example reader', 'reader STRASSE'):
            with self.subTest(query=query):
                self.assertTrue(matches_app(app, query))

        self.assertFalse(matches_app(app, 'reader editor'))

if __name__ == '__main__': unittest.main()
