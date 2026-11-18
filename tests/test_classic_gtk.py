"""GTK launcher smoke test. Run with system Python on a graphical display."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from canopy.classic_gtk import run, select_dock_pins, show_app_launcher
from canopy.preferences import Preferences, load, save

from test_classic_model import FakeApp


class PrivilegeTests(unittest.TestCase):
    def test_root_is_rejected_before_initializing_gtk(self):
        with patch('canopy.classic_gtk.os.geteuid', return_value=0):
            with self.assertRaisesRegex(SystemExit, 'ordinary user session'):
                run()


class ClassicGtkSmokeTests(unittest.TestCase):
    def setUp(self):
        try:
            import gi

            gi.require_version('Gtk', '3.0')
            gi.require_version('Gdk', '3.0')
            from gi.repository import Gdk, GLib, Gtk
        except (ImportError, ValueError) as error:
            self.skipTest(str(error))
        if not Gtk.init_check()[0]:
            self.skipTest('No graphical GTK display is available')
        self.Gdk, self.GLib, self.Gtk = Gdk, GLib, Gtk

    def test_search_beyond_old_limit_and_activate_with_keyboard(self):
        Gtk, Gdk = self.Gtk, self.Gdk
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

    def test_search_enter_and_escape(self):
        Gtk, Gdk = self.Gtk, self.Gdk
        parent = Gtk.Window()
        self.addCleanup(parent.destroy)
        parent.show()
        app = FakeApp('writer.desktop', 'Writer')
        launched = []

        show_app_launcher(Gtk, Gdk, parent, [app], launched.append)
        dialog = next(window for window in Gtk.Window.list_toplevels()
                      if window.get_transient_for() == parent)
        search = next(child for child in dialog.get_content_area().get_children()
                      if isinstance(child, Gtk.SearchEntry))
        search.set_text('missing')
        enter = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
        enter.keyval = Gdk.KEY_Return
        self.assertTrue(search.emit('key-press-event', enter))
        self.assertTrue(dialog.get_visible())
        self.assertEqual(launched, [])

        search.set_text('writer')
        self.assertTrue(search.emit('key-press-event', enter))
        self.assertEqual(launched, [app])

        self.assertFalse(dialog.get_visible())

        show_app_launcher(Gtk, Gdk, parent, [app], launched.append)
        dialog = next(window for window in Gtk.Window.list_toplevels()
                      if window.get_transient_for() == parent and window.get_visible())
        search = next(child for child in dialog.get_content_area().get_children()
                      if isinstance(child, Gtk.SearchEntry))
        escape = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
        escape.keyval = Gdk.KEY_Escape
        self.assertTrue(search.emit('key-press-event', escape))
        self.assertFalse(dialog.get_visible())
        self.assertEqual(launched, [app])

    def test_edit_dock_preserves_missing_pins_and_appends_selection(self):
        Gtk, GLib = self.Gtk, self.GLib
        parent = Gtk.Window()
        self.addCleanup(parent.destroy)
        parent.show()
        observed = []
        errors = []

        def select_writer():
            dialog = next(window for window in Gtk.Window.list_toplevels()
                          if window.get_title() == 'Edit dock')
            try:
                scroller = next(child for child in dialog.get_content_area().get_children()
                                if isinstance(child, Gtk.ScrolledWindow))
                boxes = scroller.get_child().get_child().get_children()
                checks = {box.get_tooltip_text(): box for box in boxes}
                observed.append(checks['missing.desktop'].get_active())
                checks['writer.desktop'].set_active(True)
            except Exception as error:
                errors.append(error)
                dialog.response(Gtk.ResponseType.CANCEL)
            else:
                dialog.response(Gtk.ResponseType.OK)
            return GLib.SOURCE_REMOVE

        GLib.idle_add(select_writer)
        selected = select_dock_pins(
            Gtk, parent, [FakeApp('writer.desktop', 'Writer')], ['missing.desktop']
        )
        self.assertEqual(errors, [])
        self.assertEqual(observed, [True])
        self.assertEqual(selected, ['missing.desktop', 'writer.desktop'])

    def test_preview_places_compact_dock_without_default_apps(self):
        from gi.repository import Gio
        Gtk, Gdk, GLib = self.Gtk, self.Gdk, self.GLib
        snapshots = []
        menu_images = []

        def inspect_windows():
            windows = [window for window in Gtk.Window.list_toplevels()
                       if window.get_title() == 'Canopy Classic preview' and window.get_visible()]
            snapshots.extend((window.get_size(), window.get_position()) for window in windows)
            for window in windows:
                for widget in window.get_child().get_children():
                    if widget.get_accessible().get_name() == 'Canopy menu':
                        image = widget.get_image()
                        if image is not None and image.get_storage_type() == Gtk.ImageType.PIXBUF:
                            menu_images.append(image.get_pixbuf().get_width())
            Gtk.main_quit()
            return GLib.SOURCE_REMOVE

        with tempfile.TemporaryDirectory() as config:
            settings = Path(config) / 'canopy/settings.json'
            settings.parent.mkdir()
            settings.write_bytes(b'{broken')
            with patch.dict('os.environ', {'XDG_CONFIG_HOME': config}), \
                    patch.object(Gio, 'app_info_get_all', return_value=[]):
                with self.assertRaisesRegex(SystemExit, '--safe-defaults'):
                    run()
                GLib.idle_add(inspect_windows)
                run(safe_defaults=True)
                self.assertEqual(settings.read_bytes(), b'{broken')
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        area = monitor.get_workarea()
        self.assertFalse(any(window.get_title() == 'Canopy Classic preview'
                             for window in Gtk.Window.list_toplevels()))
        self.assertEqual(menu_images, [20])
        self.assertEqual(len(snapshots), 2)
        (dock_width, dock_height), (x, y) = min(snapshots)
        self.assertLess(dock_width, area.width)
        self.assertLess(abs(x + dock_width / 2 - (area.x + area.width / 2)), 2)
        self.assertEqual(y + dock_height, area.y + area.height - 12)

    def test_startup_failure_disposes_windows(self):
        from gi.repository import Gio

        with patch.object(Gio, 'app_info_get_all', side_effect=RuntimeError('discovery failed')):
            with self.assertRaisesRegex(RuntimeError, 'discovery failed'):
                run(safe_defaults=True)
        self.assertFalse(any(window.get_title() == 'Canopy Classic preview'
                             for window in self.Gtk.Window.list_toplevels()))

    def test_many_pins_stay_within_monitor_width(self):
        from gi.repository import Gio

        Gtk, Gdk, GLib = self.Gtk, self.Gdk, self.GLib
        pins = [f'app{i}.desktop' for i in range(64)]
        apps = [FakeApp(desktop_id, f'Long application name {index}')
                for index, desktop_id in enumerate(pins)]
        widths = []
        apps_visible = []
        scrolling = []

        def inspect():
            windows = [window for window in Gtk.Window.list_toplevels()
                       if window.get_title() == 'Canopy Classic preview' and window.get_visible()]
            for window in windows:
                dock_box = window.get_child()
                if not dock_box.get_style_context().has_class('canopy-dock'):
                    continue
                widths.append(window.get_size()[0])
                for child in dock_box.get_children():
                    if isinstance(child, Gtk.Button) and child.get_label() == 'Apps ▾':
                        apps_visible.append(child.get_mapped() and child.get_allocation().width > 0)
                    if isinstance(child, Gtk.ScrolledWindow):
                        adjustment = child.get_hadjustment()
                        scrolling.append(adjustment.get_upper() > adjustment.get_page_size())
            Gtk.main_quit()
            return GLib.SOURCE_REMOVE

        with tempfile.TemporaryDirectory() as config:
            path = Path(config) / 'canopy/settings.json'
            save(path, Preferences(classic_pins=pins))
            with patch.dict('os.environ', {'XDG_CONFIG_HOME': config}), \
                    patch.object(Gio, 'app_info_get_all', return_value=apps):
                GLib.idle_add(inspect)
                run()

        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        self.assertEqual(len(widths), 1)
        self.assertLessEqual(widths[0], monitor.get_workarea().width)
        self.assertEqual(apps_visible, [True])
        self.assertEqual(scrolling, [True])

    def test_edit_menu_persists_and_refreshes_dock(self):
        from gi.repository import Gio

        Gtk, GLib = self.Gtk, self.GLib
        app = FakeApp('writer.desktop', 'Writer')
        menus, labels, errors = [], [], []

        def capture_popup(menu, *_args):
            menus.append(menu)

        def edit():
            try:
                windows = [window for window in Gtk.Window.list_toplevels()
                           if window.get_title() == 'Canopy Classic preview']
                top = next(window for window in windows
                           if window.get_child().get_style_context().has_class('canopy-panel'))
                home = next(button for button in top.get_child().get_children()
                            if button.get_accessible().get_name() == 'Canopy menu')
                home.clicked()
                action = next(item for item in menus[-1].get_children()
                              if item.get_label() == 'Edit dock')
                action.activate()
                dock = next(window for window in windows
                            if window.get_child().get_style_context().has_class('canopy-dock'))
                scroller = next(child for child in dock.get_child().get_children()
                                if isinstance(child, Gtk.ScrolledWindow))
                labels.extend(button.get_label() for button in
                              scroller.get_child().get_child().get_children())
            except Exception as error:
                errors.append(error)
            finally:
                Gtk.main_quit()
            return GLib.SOURCE_REMOVE

        with tempfile.TemporaryDirectory() as config:
            path = Path(config) / 'canopy/settings.json'
            with patch.dict('os.environ', {'XDG_CONFIG_HOME': config}), \
                    patch.object(Gio, 'app_info_get_all', return_value=[app]), \
                    patch.object(Gtk.Menu, 'popup_at_widget', capture_popup), \
                    patch('canopy.classic_gtk.select_dock_pins', return_value=['writer.desktop']):
                GLib.idle_add(edit)
                run()
            self.assertEqual(load(path).classic_pins, ['writer.desktop'])
        self.assertEqual(errors, [])
        self.assertEqual(labels, ['Writer'])
