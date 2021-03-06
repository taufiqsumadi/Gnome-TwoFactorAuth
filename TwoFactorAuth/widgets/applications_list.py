# -*- coding: utf-8 -*-
"""
 Copyright © 2016 Bilal Elmoussaoui <bil.elmoussaoui@gmail.com>

 This file is part of Gnome-TwoFactorAuth.

 Gnome-TwoFactorAuth is free software: you can redistribute it and/or
 modify it under the terms of the GNU General Public License as published
 by the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 TwoFactorAuth is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU General Public License for more details.

 You should have received a copy of the GNU General Public License
 along with Gnome-TwoFactorAuth. If not, see <http://www.gnu.org/licenses/>.
"""
from gi import require_version
require_version("Gtk", "3.0")
from gi.repository import Gtk, GObject, Gio, Gdk, GLib
from TwoFactorAuth.widgets.search_bar import SearchBar
from TwoFactorAuth.widgets.application_row import ApplicationRow
from os import path, environ as env
from gettext import gettext as _
import yaml
from glob import glob
from threading import Thread
import logging


class ApplicationChooserWindow(Gtk.Window, Thread, GObject.GObject):
    __gsignals__ = {
        'db_updated': (GObject.SignalFlags.RUN_LAST, None, (bool,))
    }

    def __init__(self, window):
        Thread.__init__(self)
        GObject.GObject.__init__(self)
        self.nom = "applications-db-reader"
        Gtk.Window.__init__(self, type=Gtk.WindowType.TOPLEVEL, modal=True,
                            destroy_with_parent=True)
        self.parent = window
        self.db = []
        self.spinner = Gtk.Spinner()
        self.search_button = Gtk.ToggleButton()
        self.listbox = Gtk.ListBox()
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.generate_window()
        self.generate_search_bar()
        self.generate_components()
        self.generate_header_bar()
        self.start()

    def emit(self, *args):
        GLib.idle_add(GObject.GObject.emit, self, *args)

    def run(self):
        # Load applications list using a Thread
        self.read_database()
        self.add_apps()
        self.emit("db_updated", True)

    def generate_window(self):
        """
            Generate the main window
        """
        self.connect("destroy", self.close_window)
        self.resize(410, 550)
        self.set_size_request(410, 550)
        x, y = self.parent.parent.get_position()
        self.move(x, y)
        self.set_resizable(False)
        self.set_transient_for(self.parent.parent)
        self.connect("key_press_event", self.on_key_press)
        self.add(self.main_box)

    def generate_components(self):
        """
            Generate window compenents
        """
        box_outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        # Create a ScrolledWindow
        self.scrolled_win = Gtk.ScrolledWindow()
        self.scrolled_win.add_with_viewport(box_outer)
        self.scrolled_win.hide()
        self.main_box.pack_start(self.scrolled_win, True, True, 0)

        self.listbox.get_style_context().add_class("applications-list")
        self.listbox.set_adjustment()
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        box_outer.pack_start(self.listbox, True, True, 0)

        self.spinner_box_outer = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL)
        spinner_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.spinner.start()
        self.spinner.show()
        spinner_box.pack_start(self.spinner, False, False, 6)
        self.spinner_box_outer.pack_start(spinner_box, True, True, 6)
        self.main_box.pack_start(self.spinner_box_outer, True, True, 0)

    def generate_header_bar(self):
        """
            Generate header bar box
        """
        self.hb = Gtk.HeaderBar()
        self.hb.props.title = _("Select an application")

        left_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        right_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

        cancel_button = Gtk.Button.new_with_label(_("Cancel"))
        cancel_button.connect("clicked", self.close_window)
        left_box.add(cancel_button)

        search_icon = Gio.ThemedIcon(name="system-search-symbolic")
        search_image = Gtk.Image.new_from_gicon(
            search_icon, Gtk.IconSize.BUTTON)
        self.search_button.set_tooltip_text(_("Search"))
        self.search_button.set_image(search_image)

        next_button = Gtk.Button.new_with_label(_("Next"))
        next_button.get_style_context().add_class("suggested-action")
        next_button.connect("clicked", self.select_application)

        right_box.pack_start(self.search_button, False, False, 6)
        right_box.pack_start(next_button, False, False, 6)

        self.hb.pack_end(right_box)
        self.hb.pack_start(left_box)
        self.set_titlebar(self.hb)

    def generate_search_bar(self):
        """
            Generate the search bar
        """
        self.search_bar = SearchBar(self.listbox, self, self.search_button)
        self.main_box.pack_start(self.search_bar, False, True, 0)

    def is_valid_app(self, app):
        """
            Check if the application supports tfa
        """
        if set(["tfa", "software"]).issubset(app.keys()):
            return app["tfa"] and app["software"]
        else:
            return False

    def on_key_press(self, label, key_event):
        """
            Keyboard listener handling
        """
        keyname = Gdk.keyval_name(key_event.keyval).lower()

        if keyname == "escape":
            if not self.search_bar.is_visible():
                self.close_window()
                return True

        if keyname == "up" or keyname == "down":
            dx = -1 if keyname == "up" else 1
            index = self.listbox.get_selected_row().get_index()
            index = (index + dx) % len(self.db)
            selected_row = self.listbox.get_row_at_index(index)
            self.listbox.select_row(selected_row)
            return True

        if keyname == "return":
            self.select_application()
            return True
        return False

    def do_db_updated(self, *args):
        """
            Hide and stop the spinner and show the scrolled window
        """
        self.spinner.stop()
        self.spinner_box_outer.hide()
        self.scrolled_win.show()
        self.listbox.hide()
        if len(self.listbox.get_children()) != 0:
            self.listbox.show_all()
        logging.debug("UI updated")

    def read_database(self):
        """
            Read .yml database files provided by 2factorauth guys!
        """
        db_dir = path.join(env.get("DATA_DIR"), "applications") + "/data/*.yml"
        db_files = glob(db_dir)
        logging.debug("Reading database files started")
        for db_file in db_files:
            with open(db_file, 'r') as data:
                try:
                    websites = yaml.load(data)["websites"]
                    for app in websites:
                        if self.is_valid_app(app):
                            self.db.append(app)
                except yaml.YAMLError as error:
                    logging.error("Error loading yml file : %s " % str(error))
        logging.debug("Reading database files finished")

    def add_apps(self):
        """
            Add database applications to the Gtk.ListBox
        """
        self.db = sorted(self.db, key=lambda k: k['name'].lower())
        logging.debug("Application list was ordered alphabetically")

        for app in self.db:
            img_path = app["img"]
            app_name = app["name"]
            self.listbox.add(ApplicationRow(app_name, img_path))

        if len(self.db) != 0:
            self.listbox.select_row(self.listbox.get_row_at_index(0))

    def select_application(self, *args):
        """
            Select a logo and return its path to the add application window
        """
        selected_row = self.listbox.get_selected_row()
        if selected_row:
            img_path = selected_row.get_icon_name()
            app_name = selected_row.get_name()
            logging.debug("%s was selected" % app_name)
            self.parent.update_logo(img_path)
            self.parent.name_entry.set_text(app_name)
            self.parent.show_window()
            self.parent.present()
            self.close_window()

    def show_window(self):
        self.show_all()

    def close_window(self, *args):
        """
            Close the window
        """
        logging.debug("Closing ApplicationChooserWindow")
        self.destroy()
