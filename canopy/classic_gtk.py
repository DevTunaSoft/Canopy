"""Canopy Classic: optional GTK3 preview alongside Linux Mint Cinnamon.

This is an ordinary user-owned app, NOT a complete desktop session or compositor.
"""
import os
from datetime import datetime
from pathlib import Path

from canopy.classic_model import DEFAULT_DOCK, clock_label, visible_apps
from canopy.preferences import load


def run():
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gdk, Gio, GLib, Gtk

    if not Gtk.init_check()[0]:
        raise RuntimeError('No graphical GTK display is available')

    cfg = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'canopy' / 'settings.json'
    prefs = load(cfg)
    if prefs.layout.value != 'classic':
        raise RuntimeError('Choose Classic in Canopy preferences to launch this preview')

    css = Gtk.CssProvider()
    css.load_from_data(b'''
      .canopy-panel { background: #1f302b; color: #fff; padding: 5px 10px; }
      .canopy-dock { background: #263f38; border-radius: 16px; padding: 8px; }
      .canopy-panel button, .canopy-dock button { color: white; background: transparent; border: 0; }
      .canopy-panel button:hover, .canopy-dock button:hover { background: #476357; }
    ''')
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css,
                                               Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def window_at(y, width, css_class):
        window = Gtk.Window()
        window.set_title('Canopy Classic preview')
        window.set_decorated(False)
        window.set_resizable(False)
        window.set_keep_above(True)
        window.set_type_hint(Gdk.WindowTypeHint.DOCK)
        window.set_skip_taskbar_hint(True)
        window.set_default_size(width, -1)
        window.move(max(0, (screen_width - width) // 2), y)
        container = Gtk.Box(spacing=8)
        container.get_style_context().add_class(css_class)
        window.add(container)
        return window, container

    screen = Gdk.Screen.get_default()
    monitor = screen.get_primary_monitor()
    if monitor < 0:
        monitor = 0
    rect = screen.get_monitor_geometry(monitor)
    screen_width = rect.width
    # Position relative to the primary monitor; avoid hardcoded monitor origin.
    def set_position(window, x, y):
        window.move(rect.x + x, rect.y + y)

    top, top_box = window_at(0, rect.width, 'canopy-panel')
    def open_menu(button):
        menu = Gtk.Menu()
        for label, callback in (('About Canopy Classic', show_about), ('Quit preview', Gtk.main_quit)):
            item = Gtk.MenuItem(label=label)
            item.connect('activate', lambda _item, func=callback: func())
            menu.append(item)
        menu.show_all()
        menu.popup_at_widget(button, Gdk.Gravity.SOUTH_WEST, Gdk.Gravity.NORTH_WEST, None)

    def show_about():
        dialog = Gtk.MessageDialog(transient_for=top, modal=True,
                                   message_type=Gtk.MessageType.INFO,
                                   buttons=Gtk.ButtonsType.CLOSE,
                                   text='Canopy Classic — preview')
        dialog.format_secondary_text('The Familiar Feel. The Freedom of Linux.\nCinnamon remains available.')
        dialog.run()
        dialog.destroy()

    home_button = Gtk.Button(label='Canopy ▾')  # Original Tux art will replace this placeholder.
    home_button.connect('clicked', open_menu)
    top_box.pack_start(home_button, False, False, 0)
    top_box.pack_start(Gtk.Label(label='Classic'), False, False, 0)
    top_box.pack_end(Gtk.Label(label='Preview'), False, False, 0)
    clock = Gtk.Label()
    top_box.pack_end(clock, False, False, 10)

    def refresh_clock():
        clock.set_text(clock_label(datetime.now()))
        return True
    refresh_clock()
    GLib.timeout_add_seconds(30, refresh_clock)

    dock, dock_box = window_at(rect.height - 88, 400, 'canopy-dock')
    def launch(app):
        try:
            app.launch([], None)  # Gio uses the desktop file; never interpolate shell commands.
        except GLib.Error as error:
            dialog = Gtk.MessageDialog(transient_for=dock, modal=True,
                                       message_type=Gtk.MessageType.ERROR,
                                       buttons=Gtk.ButtonsType.CLOSE,
                                       text='Could not open application')
            dialog.format_secondary_text(str(error))
            dialog.run()
            dialog.destroy()

    def add_app_button(label, app):
        button = Gtk.Button(label=label)
        button.connect('clicked', lambda _button: launch(app))
        dock_box.pack_start(button, False, False, 0)

    for item in DEFAULT_DOCK:
        app = Gio.DesktopAppInfo.new(item.desktop_id)
        if app is not None:
            add_app_button(item.title, app)

    apps_button = Gtk.Button(label='Apps ▾')
    def open_apps(button):
        menu = Gtk.Menu()
        for app in visible_apps(Gio.app_info_get_all())[:40]:
            item = Gtk.MenuItem(label=app.get_name())
            item.connect('activate', lambda _item, current=app: launch(current))
            menu.append(item)
        menu.show_all()
        menu.popup_at_widget(button, Gdk.Gravity.NORTH_WEST, Gdk.Gravity.SOUTH_WEST, None)
    apps_button.connect('clicked', open_apps)
    dock_box.pack_start(apps_button, False, False, 0)

    top.connect('destroy', Gtk.main_quit)
    dock.connect('destroy', Gtk.main_quit)
    top.show_all()
    dock.show_all()
    set_position(top, 0, 0)
    set_position(dock, max(0, (rect.width - 400) // 2), max(0, rect.height - 88))
    Gtk.main()


if __name__ == '__main__':
    run()
