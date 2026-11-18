"""GTK launcher smoke test. Run with system Python on a graphical display."""
import unittest
from unittest.mock import patch

from canopy.classic_gtk import run, show_app_launcher

from test_classic_model import FakeApp


class PrivilegeTests(unittest.TestCase):
    def test_root_is_rejected_before_initializing_gtk(self):
        with patch('canopy.classic_gtk.os.geteuid', return_value=0):
            with self.assertRaisesRegex(SystemExit, 'ordinary user session'):
                run()


class LauncherSmokeTests(unittest.TestCase):
    def test_search_beyond_old_limit_and_activate_with_keyboard(self):
        try:
            import gi

            gi.require_version('Gtk', '3.0')
            gi.require_version('Gdk', '3.0')
            from gi.repository import Gdk, Gtk
        except (ImportError, ValueError) as error:
            self.skipTest(str(error))
        if not Gtk.init_check()[0]:
            self.skipTest('No graphical GTK display is available')

        parent = Gtk.Window()
        self.addCleanup(parent.destroy)
        parent.show()
        apps = [FakeApp(f'app{i}.desktop', f'App {i:02}') for i in range(45)]
        target = FakeApp('writer.desktop', 'Writer')
        apps.append(target)
        launched = []
        show_app_launcher(Gtk, Gdk, parent, apps, launched.append)
        dialog = next(window for window in Gtk.Window.list_toplevels()
                      if window.get_transient_for() == parent)
        self.addCleanup(dialog.destroy)
        children = dialog.get_content_area().get_children()
        search = next(child for child in children if isinstance(child, Gtk.SearchEntry))
        scroller = next(child for child in children if isinstance(child, Gtk.ScrolledWindow))
        results = scroller.get_child().get_child()
        self.assertEqual(len(results.get_children()), 46)
        self.assertIs(dialog.get_focus(), search)

        search.set_text('missing')
        self.assertFalse(any(row.get_child_visible() for row in results.get_children()))
        search.set_text('WRITER')
        visible = [row for row in results.get_children() if row.get_child_visible()]
        self.assertEqual(len(visible), 1)

        down = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
        down.keyval = Gdk.KEY_Down
        self.assertTrue(search.emit('key-press-event', down))
        self.assertIs(results.get_selected_row(), visible[0])
        self.assertIs(dialog.get_focus(), visible[0])
        visible[0].activate()
        self.assertEqual(launched, [target])
        self.assertFalse(dialog.get_visible())
