"""Canopy Classic: optional GTK3 preview alongside Linux Mint Cinnamon.

This is an ordinary user-owned app, NOT a complete desktop session or compositor.
"""
import os
from datetime import datetime
from pathlib import Path

from canopy.applications import matches_app, visible_apps
from canopy.classic_model import DEFAULT_DOCK, clock_label
from canopy.preferences import load


def show_app_launcher(Gtk, Gdk, parent, apps, launch):
    dialog = Gtk.Dialog(title='Applications', transient_for=parent, modal=True)
    dialog.set_default_size(420, 480)
    dialog.add_button('Close', Gtk.ResponseType.CLOSE)

    content = dialog.get_content_area()
    content.set_border_width(12)
    content.set_spacing(8)
    search = Gtk.SearchEntry()
    search.set_placeholder_text('Search applications')
    search.get_accessible().set_name('Search applications')
    content.pack_start(search, False, False, 0)

    scroller = Gtk.ScrolledWindow()
    scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    content.pack_start(scroller, True, True, 0)
    results = Gtk.ListBox()
    results.get_accessible().set_name('Applications')
    results.set_placeholder(Gtk.Label(label='No applications found'))
    scroller.add(results)
    results.set_adjustment(scroller.get_vadjustment())

    applications = {}
    for app in visible_apps(apps):
        row = Gtk.ListBoxRow()
        label = Gtk.Label(label=app.get_name(), xalign=0)
        label.set_margin_start(8)
        label.set_margin_top(6)
        label.set_margin_bottom(6)
        row.add(label)
        applications[row] = app
        results.add(row)

    results.set_filter_func(lambda row: matches_app(applications[row], search.get_text()))

    def update_results(_search):
        results.unselect_all()
        results.invalidate_filter()

    def focus_results(_search, event):
        if event.keyval != Gdk.KEY_Down:
            return False
        for row in results.get_children():
            if row.get_child_visible():
                results.select_row(row)
                row.grab_focus()
                return True
        return False

    def activate_app(_results, row):
        dialog.destroy()
        launch(applications[row])

    search.connect('changed', update_results)
    search.connect('key-press-event', focus_results)
    results.connect('row-activated', activate_app)
    dialog.connect('response', lambda window, _response: window.destroy())
    dialog.show_all()
    search.grab_focus()


def run():
    if os.geteuid() == 0:
        raise SystemExit('Run Canopy Classic from an ordinary user session')

    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('Gdk', '3.0')
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
    apps_button.connect(
        'clicked', lambda _button: show_app_launcher(Gtk, Gdk, dock, Gio.app_info_get_all(), launch)
    )
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
