# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""One-time separation setup: pick MVSEP, a studio PC, or this machine."""

from __future__ import annotations

from gi.repository import Gtk

from pynicotine.digging.settings import DiggingSettings, renderer_available


class SeparationSetup:

    def __init__(self, application, on_saved=None) -> None:

        self.application = application
        self.on_saved = on_saved
        self.settings = DiggingSettings.load()

        window_kwargs = {
            "title": "Separation setup",
            "default_width": 460,
            "default_height": 320,
            "resizable": False,
            "modal": True,
        }
        gtk_app = getattr(application, "_instance", None)

        if isinstance(gtk_app, Gtk.Application):
            window_kwargs["application"] = gtk_app

        self.window = Gtk.Window(**window_kwargs)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, visible=True)
        box.set_margin_top(18)
        box.set_margin_bottom(18)
        box.set_margin_start(18)
        box.set_margin_end(18)

        title = Gtk.Label(label="Where should stems be separated?", xalign=0, visible=True)
        title.add_css_class("title-4")
        box.append(title)

        self.mvsep_radio = Gtk.CheckButton(label="MVSEP (cloud, pay per minute)", visible=True)
        self.pc_radio = Gtk.CheckButton(label="Studio PC (your agent)", visible=True)
        self.pc_radio.set_group(self.mvsep_radio)
        self.local_radio = Gtk.CheckButton(label="This Mac (local Demucs)", visible=True)
        self.local_radio.set_group(self.mvsep_radio)

        box.append(self.mvsep_radio)

        self.mvsep_token = Gtk.Entry(placeholder_text="MVSEP API token", visible=True)
        self.mvsep_type = Gtk.Entry(placeholder_text="separation type id (see: digging types)", visible=True)
        box.append(self.mvsep_token)
        box.append(self.mvsep_type)

        box.append(self.pc_radio)

        self.pc_url = Gtk.Entry(placeholder_text="http://studio-pc.local:8765", visible=True)
        self.pc_token = Gtk.Entry(placeholder_text="agent token", visible=True)
        box.append(self.pc_url)
        box.append(self.pc_token)

        box.append(self.local_radio)

        local_ok, local_reason = renderer_available("local", self.settings)
        self.local_note = Gtk.Label(label=("Demucs found on this machine" if local_ok else local_reason),
                                    xalign=0, visible=True)
        self.local_note.add_css_class("dim-label")
        box.append(self.local_note)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, visible=True)
        buttons.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel", visible=True)
        cancel.connect("clicked", lambda *_args: self.window.close())
        save = Gtk.Button(label="Save", visible=True)
        save.add_css_class("suggested-action")
        save.connect("clicked", self._on_save)
        buttons.append(cancel)
        buttons.append(save)
        box.append(buttons)

        self.window.set_child(box)
        self._load_current()

    def _load_current(self) -> None:

        settings = self.settings
        self.mvsep_token.set_text(settings.mvsep_token)
        self.mvsep_type.set_text(settings.mvsep_sep_type)
        self.pc_url.set_text(settings.pc_url)
        self.pc_token.set_text(settings.pc_token)

        if settings.renderer == "pc":
            self.pc_radio.set_active(True)
        elif settings.renderer == "local":
            self.local_radio.set_active(True)
        else:
            self.mvsep_radio.set_active(True)

    def _on_save(self, *_args) -> None:

        settings = self.settings
        settings.mvsep_token = self.mvsep_token.get_text().strip()
        settings.mvsep_sep_type = self.mvsep_type.get_text().strip()
        settings.pc_url = self.pc_url.get_text().strip()
        settings.pc_token = self.pc_token.get_text().strip()

        if self.pc_radio.get_active():
            settings.renderer = "pc"
        elif self.local_radio.get_active():
            settings.renderer = "local"
        else:
            settings.renderer = "mvsep"

        settings.save()
        self.window.close()

        if self.on_saved:
            self.on_saved(settings)

    def present(self) -> None:
        self.window.present()
