"""Canopy Classic: optional GTK3 preview alongside Linux Mint Cinnamon.

This is an ordinary user-owned app, NOT a complete desktop session or compositor.
"""
import argparse
import os
from datetime import datetime
from pathlib import Path

from canopy.applications import matches_app, visible_apps
from canopy.classic_model import DEFAULT_DOCK, clock_label, dock_position
from canopy.preferences import Layout, Preferences, load, user_settings_path


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

    def search_key_press(_search, event):
        if event.keyval == Gdk.KEY_Escape:
            dialog.destroy()
            return True
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            for row in results.get_children():
                if row.get_child_visible():
                    activate_app(results, row)
                    break
            return True
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

    def close_on_escape(_dialog, event):
        if event.keyval == Gdk.KEY_Escape:
            dialog.destroy()
            return True
        return False

    search.connect('changed', update_results)
    search.connect('key-press-event', search_key_press)
    results.connect('row-activated', activate_app)
    dialog.connect('key-press-event', close_on_escape)
    dialog.connect('response', lambda window, _response: window.destroy())
    dialog.show_all()
    search.grab_focus()


def run(*, safe_defaults=False):
    if os.geteuid() == 0:
        raise SystemExit('Run Canopy Classic from an ordinary user session')

    if safe_defaults:
        prefs = Preferences()
    else:
        path = user_settings_path()
        try:
            prefs = load(path)
        except (OSError, ValueError) as error:
            raise SystemExit(
                f'Cannot read Canopy settings at {path}: {error}. '
                'Run with --safe-defaults to open the preview without loading settings.'
            ) from None
    if prefs.layout is not Layout.CLASSIC:
        raise SystemExit('Choose Classic in Canopy preferences to launch this preview')

    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('Gdk', '3.0')
    from gi.repository import Gdk, Gio, GLib, Gtk

    if not Gtk.init_check()[0]:
        raise RuntimeError('No graphical GTK display is available')

    css = Gtk.CssProvider()
    css.load_from_data(b'''
      .canopy-panel { background: #1f302b; color: #fff; padding: 5px 10px; }
      .canopy-dock { background: #263f38; border-radius: 16px; padding: 8px; }
      .canopy-dock-opaque { background: #263f38; }
      .canopy-dock-transparent { background: transparent; }
      .canopy-panel button, .canopy-dock button { color: white; background: transparent; border: 0; }
      .canopy-panel button:hover, .canopy-dock button:hover { background: #476357; }
    ''')
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css,
                                               Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def create_window(css_class):
        window = Gtk.Window()
        windows.append(window)
        if css_class == 'canopy-dock':
            screen = window.get_screen()
            visual = screen.get_rgba_visual() if screen.is_composited() else None
            if visual is not None:
                window.set_visual(visual)
                window.get_style_context().add_class('canopy-dock-transparent')
            else:
                window.get_style_context().add_class('canopy-dock-opaque')
        window.set_title('Canopy Classic preview')
        window.set_decorated(False)
        window.set_resizable(False)
        window.set_keep_above(True)
        window.set_type_hint(Gdk.WindowTypeHint.DOCK)
        window.set_skip_taskbar_hint(True)
        container = Gtk.Box(spacing=8)
        container.get_style_context().add_class(css_class)
        window.add(container)
        return window, container

    display = Gdk.Display.get_default()
    monitor = display.get_primary_monitor() or display.get_monitor(0)
    workarea = monitor.get_workarea()
    windows = []
    clock_source = None
    handlers = []
    try:
        top, top_box = create_window('canopy-panel')
        top.set_default_size(workarea.width, -1)
        top.move(workarea.x, workarea.y)

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

        home_button = Gtk.Button()
        emblem_path = Path(__file__).with_name('assets') / 'classic-penguin.svg'
        emblem = Gtk.Image.new_from_file(str(emblem_path))
        if emblem.get_storage_type() == Gtk.ImageType.PIXBUF:
            home_button.set_image(emblem)
        else:
            home_button.set_label('Canopy ▾')
        home_button.set_tooltip_text('Canopy menu')
        home_button.get_accessible().set_name('Canopy menu')
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

        dock, dock_box = create_window('canopy-dock')
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

        installed_apps = {app.get_id(): app for app in Gio.app_info_get_all()}
        for item in DEFAULT_DOCK:
            app = installed_apps.get(item.desktop_id)
            if app is not None:
                add_app_button(item.title, app)

        apps_button = Gtk.Button(label='Apps ▾')
        apps_button.connect(
            'clicked', lambda _button: show_app_launcher(Gtk, Gdk, dock, Gio.app_info_get_all(), launch)
        )
        dock_box.pack_start(apps_button, False, False, 0)

        dock_box.show_all()
        _, natural_size = dock_box.get_preferred_size()
        dock.move(*dock_position(
            workarea.x, workarea.y, workarea.width, workarea.height,
            natural_size.width, natural_size.height,
        ))
        top.show_all()
        dock.show()
        for window in windows:
            handlers.append((window, window.connect('destroy', Gtk.main_quit)))
        clock_source = GLib.timeout_add_seconds(30, refresh_clock)
        Gtk.main()
    finally:
        if clock_source is not None:
            GLib.source_remove(clock_source)
        for window, handler in handlers:
            if window.handler_is_connected(handler):
                window.disconnect(handler)
        for window in windows:
            window.destroy()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run the Canopy Classic preview')
    parser.add_argument('--safe-defaults', action='store_true',
                        help='open with built-in settings without modifying the settings file')
    run(safe_defaults=parser.parse_args().safe_defaults)
