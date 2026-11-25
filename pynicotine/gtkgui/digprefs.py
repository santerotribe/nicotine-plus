# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Preferences -> Digging page."""

from __future__ import annotations

from gi.repository import Gtk

from pynicotine.digging.settings import DiggingSettings, renderer_available


class DiggingPage:

    def __init__(self, application) -> None:

        self.application = application
        self.settings = DiggingSettings.load()

        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18, visible=True)
        container.set_margin_start(18)
        container.set_margin_end(18)
        container.set_margin_top(18)
        container.set_margin_bottom(18)

        title = Gtk.Label(label="Digging", xalign=0, visible=True)
        title.add_css_class("title-2")
        container.append(title)

        description = Gtk.Label(
            label=("Audition tracks from Browse, keep the ones worth sampling, "
                   "and turn them into stems and an Ableton Live set."),
            xalign=0, wrap=True, visible=True
        )
        description.add_css_class("dim-label")
        container.append(description)

        # Separation
        separation_title = Gtk.Label(label="Stem separation", xalign=0, visible=True)
        separation_title.add_css_class("title-4")
        container.append(separation_title)

        self.separation_button = Gtk.Button(label="Separation setup…", visible=True)
        self.separation_button.set_halign(Gtk.Align.START)
        self.separation_button.connect("clicked", self._on_setup_clicked)
        container.append(self.separation_button)

        self.separation_status = Gtk.Label(label="", xalign=0, wrap=True, visible=True)
        self.separation_status.add_css_class("dim-label")
        container.append(self.separation_status)

        # Preview cache
        cache_title = Gtk.Label(label="Preview cache", xalign=0, visible=True)
        cache_title.add_css_class("title-4")
        container.append(cache_title)

        cache_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, visible=True)
        cache_label = Gtk.Label(label="Keep at most", xalign=0, visible=True)
        self.cache_spinner = Gtk.SpinButton.new_with_range(0, 20, 1)
        self.cache_spinner.set_visible(True)
        self.cache_spinner.set_value(self.settings.preview_cache_mb / 1024)
        gb_label = Gtk.Label(label="GB of previews and exports", xalign=0, visible=True)
        cache_row.append(cache_label)
        cache_row.append(self.cache_spinner)
        cache_row.append(gb_label)
        container.append(cache_row)

        self.clear_button = Gtk.Button(label="Clear previews now", visible=True)
        self.clear_button.set_halign(Gtk.Align.START)
        self.clear_button.connect("clicked", self._on_clear_clicked)
        container.append(self.clear_button)

        self.cache_status = Gtk.Label(label="", xalign=0, wrap=True, visible=True)
        self.cache_status.add_css_class("dim-label")
        container.append(self.cache_status)

        self.container = container
        self.widgets = (container,)

    # -- preferences interface -------------------------------------------

    def set_settings(self) -> None:

        self.settings = DiggingSettings.load()
        self.cache_spinner.set_value(self.settings.preview_cache_mb / 1024)
        self._refresh_status()

    def get_settings(self) -> dict:

        self.settings.preview_cache_mb = int(self.cache_spinner.get_value() * 1024)
        self.settings.save()
        self._refresh_status()
        return {}

    def destroy(self) -> None:
        pass

    # -- helpers ----------------------------------------------------------

    def _refresh_status(self) -> None:

        ready, reason = renderer_available(self.settings.renderer, self.settings)

        if ready:
            self.separation_status.set_text(f"Ready — using {self.settings.renderer}.")
        else:
            self.separation_status.set_text(f"Not set up — {reason}")

        from pynicotine.digging.cache import PreviewCache

        usage = PreviewCache(self.settings.work_path / "exports", self.settings.preview_cache_bytes).usage()
        self.cache_status.set_text(f"{usage.total_mb:.0f} MB in use now.")

    def _on_setup_clicked(self, *_args) -> None:

        from pynicotine.gtkgui.digsetup import SeparationSetup

        def saved(settings):

            self.settings = settings
            self._refresh_status()

        SeparationSetup(self.application, on_saved=saved).present()

    def _on_clear_clicked(self, *_args) -> None:

        from pynicotine.digging.maintenance import wipe

        report = wipe(self.settings)
        self.cache_status.set_text(f"Removed {report.files_removed} files ({report.bytes_freed / (1024 * 1024):.1f} MB).")
